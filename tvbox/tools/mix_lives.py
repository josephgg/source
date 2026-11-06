#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把各影视仓配置里的直播频道汇总、去重、探活后并入仓库根目录的 iptv_filtered.m3u。

用法：
    python tools/mix_lives.py            # 只统计，不改文件
    python tools/mix_lives.py --write    # 写入（自动备份 .bak）

规则：
1. 现有 iptv_filtered.m3u 的条目不删不改，新频道只追加到末尾；
2. 频道名规范化后与现有重合的跳过，避免同一个台重复出现；
3. 每条线路真请求一次，只保留连得上的（IPTV 源死链率极高，不探活等于灌垃圾）；
4. 央视 > 卫视 > 港澳台 > 地方台，每台最多 2 条线路；同一路流的
   ?id=/token= 变体不算新线路（去重键忽略 query）。
"""
import argparse
import collections
import concurrent.futures
import json
import os
import re
import shutil
import ssl
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TVBOX = os.path.dirname(HERE)
REPO = os.path.dirname(TVBOX)
M3U = os.path.join(REPO, "iptv_filtered.m3u")
DUMP = os.path.join(HERE, "lives_dump.json")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

CORE = re.compile(r"(cctv|央视|中央|卫视|凤凰|翡翠|明珠|tvb|珠江|澳门|香港|台湾|中天|东森|三立|民视|台视|华视|中视)")
LOCAL = re.compile(r"(北京|上海|天津|重庆|河北|山西|辽宁|吉林|黑龙江|江苏|浙江|安徽|福建|江西|山东|"
                   r"河南|湖北|湖南|广东|广西|海南|四川|贵州|云南|陕西|甘肃|青海|宁夏|新疆|西藏|"
                   r"内蒙古|深圳|厦门|苏州|无锡|常州|南京|杭州|宁波|青岛|大连|济南|沈阳|长沙|武汉|"
                   r"成都|西安|郑州|昆明|福州|南昌|合肥|石家庄|太原|兰州|乌鲁木齐|呼和浩特|拉萨|"
                   r"南宁|贵阳|海口|银川|西宁|长春|哈尔滨|鞍山|淄博|烟台|洛阳|绵阳)")
JUNK = re.compile(r"(mtv|music|音乐|电台|广播|radio|测试|test|广告|备用|线路|p2p|蜜桃|福利)")
RANK = {"央视": 0, "卫视": 1, "港澳台": 2, "地方台": 3, "其他": 4}


def norm(s):
    s = re.sub(r"[（(\[【].*?[)）\]】]", "", s)
    s = re.sub(r"(?i)\b(hd|fhd|uhd|4k|8k|sd)\b", "", s)
    for w in ("高清", "超清", "标清", "蓝光", "hevc", "H265", "h265"):
        s = s.replace(w, "")
    return re.sub(r"[\s\-_·|]+", "", s).lower()


def group_of(name):
    n = norm(name)
    if re.search(r"(cctv|央视|中央)", n):
        return "央视"
    if re.search(r"(凤凰|翡翠|明珠|tvb|澳门|香港|台湾|中天|东森|三立|民视|台视|华视|中视)", n):
        return "港澳台"
    if "卫视" in n:
        return "卫视"
    if LOCAL.search(n):
        return "地方台"
    return "其他"


def probe(url, timeout=8):
    req = urllib.request.Request(url.split("|")[0], headers={
        "User-Agent": "okhttp/3.15", "Range": "bytes=0-2047"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status in (200, 206) and len(r.read(64)) > 0
    except Exception:  # noqa: BLE001
        return False


def key_of(u):
    try:
        p = urllib.parse.urlsplit(u.split("|")[0])
        return (p.scheme, p.netloc.lower(), p.path)
    except Exception:  # noqa: BLE001
        return (u, "", "")


# ---------------------------------------------------------------- 采集


def collect():
    """从 sources.json 抓各仓的 lives，展开成频道清单并缓存到 lives_dump.json"""
    import sys
    sys.path.insert(0, TVBOX)
    sys.path.insert(0, HERE)
    import build as B

    conf = json.load(open(os.path.join(TVBOX, "sources.json"), encoding="utf-8"))
    sources = [s for s in conf["sources"] if s.get("enabled")]

    def get_cfg(src):
        try:
            cfg = B.parse_cfg(B.fetch(src["url"], src.get("timeout") or 30))
            return B.deep_abs(cfg, src["url"]) if isinstance(cfg, dict) else None
        except Exception:  # noqa: BLE001
            return None

    lives = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        for cfg in ex.map(get_cfg, sources):
            if not cfg:
                continue
            for it in B.as_list(cfg.get("lives")):
                if not isinstance(it, dict):
                    continue
                u = (it.get("url") or "").strip()
                if u.startswith("http"):
                    lives.setdefault(B.unwrap_mirror(u), (it.get("name") or "未命名").strip())
    print("直播清单去重后：%d 个" % len(lives))

    def one(item):
        url, name = item
        try:
            return url, name, B.fetch(url, 25)
        except Exception:  # noqa: BLE001
            return url, name, ""

    chans = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        for url, name, txt in ex.map(one, list(lives.items())):
            if txt:
                chans.extend(parse_channels(name, txt))

    # 只保留现有 m3u 里没有的候选
    cur_names, cur_urls = set(), set()
    for s in (l.strip() for l in open(M3U, encoding="utf-8", errors="replace")):
        if s.startswith("#EXTINF"):
            cur_names.add(norm(s.rsplit(",", 1)[-1].strip()))
        elif s and not s.startswith("#"):
            cur_urls.add(s)
    new = [c for c in chans if c[1] not in cur_urls and norm(c[0]) not in cur_names]
    json.dump({"lives": list(lives.items()), "new": new},
              open(DUMP, "w", encoding="utf-8"), ensure_ascii=False)
    print("解析出 %d 条频道，其中不在现有 m3u 的 %d 条 -> %s" % (len(chans), len(new), DUMP))
    return new


def parse_channels(name, txt):
    out = []
    if "#EXTINF" in txt or txt.lstrip().startswith("#EXTM3U"):
        group, title = "", ""
        for line in (l.strip() for l in txt.splitlines()):
            if line.startswith("#EXTINF"):
                g = re.search(r'group-title="([^"]*)"', line)
                group = g.group(1) if g else ""
                title = line.rsplit(",", 1)[-1].strip()
            elif line.startswith("#EXTGRP:"):
                group = line.split(":", 1)[1].strip()
            elif line and not line.startswith("#"):
                if title:
                    out.append((title, line, group or name))
                title = ""
    else:
        group = name
        for line in (l.strip() for l in txt.splitlines()):
            if not line or line.startswith("#") or "," not in line:
                continue
            title = line.split(",")[0].strip()
            u = line.split(",")[-1].strip()
            if title.endswith("#genre#"):
                group = title.replace("#genre#", "").strip() or name
                continue
            if u.startswith("http"):
                out.append((title, u, group))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="写入 m3u（默认只统计）")
    ap.add_argument("--refresh", action="store_true", help="重新抓取各仓直播清单")
    ap.add_argument("--max-names", type=int, default=600)
    ap.add_argument("--max-urls", type=int, default=900)
    args = ap.parse_args()

    if args.refresh or not os.path.exists(DUMP):
        collect()
    cand = json.load(open(DUMP, encoding="utf-8"))["new"]

    lines = open(M3U, encoding="utf-8", errors="replace").read().splitlines()
    cur_names, cur_urls = set(), set()
    for s in (l.strip() for l in lines):
        if s.startswith("#EXTINF"):
            cur_names.add(norm(s.rsplit(",", 1)[-1].strip()))
        elif s and not s.startswith("#"):
            cur_urls.add(s)
    print("现有 m3u：%d 行 / %d 个频道名 / %d 条 URL" % (len(lines), len(cur_names), len(cur_urls)))

    by_name = collections.OrderedDict()
    for title, url, _g in cand:
        n = norm(title)
        if not n or n in cur_names or JUNK.search(n):
            continue
        if not (CORE.search(n) or LOCAL.search(n)):
            continue
        item = by_name.setdefault(n, {"name": title.strip(), "urls": [], "seen": 0})
        item["seen"] += 1
        if url not in item["urls"] and url not in cur_urls:
            item["urls"].append(url)

    ordered = sorted(by_name.values(),
                     key=lambda x: (RANK[group_of(x["name"])], -x["seen"], x["name"]))[:900]
    tasks = [(i, u) for i, it in enumerate(ordered) for u in it["urls"][:3]]
    print("候选 %d 台 / 待探活 %d 条线路" % (len(ordered), len(tasks)))

    alive = collections.defaultdict(list)
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:
        for (i, u), ok in zip(tasks, ex.map(lambda t: probe(t[1]), tasks)):
            if ok:
                alive[i].append(u)

    out, added_names, added_urls, seen_key = [], 0, 0, set()
    for i, it in enumerate(ordered):
        if i not in alive or added_names >= args.max_names or added_urls >= args.max_urls:
            continue
        g, took = group_of(it["name"]), 0
        for u in alive[i]:
            if added_urls >= args.max_urls or took >= 2:
                break
            k = key_of(u)
            if k in seen_key:
                continue
            seen_key.add(k)
            out.append('#EXTINF:-1 tvg-name="%s" group-title="%s",%s' % (it["name"], g, it["name"]))
            out.append(u)
            added_urls += 1
            took += 1
        if took:
            added_names += 1

    print("可并入：%d 台 / %d 条线路（存活 %d 台）" % (added_names, added_urls, len(alive)))
    if not out or not args.write:
        if not args.write:
            print("（未写入，加 --write 生效）")
        return

    shutil.copy2(M3U, M3U + ".bak")
    body = lines[:]
    if body and not body[-1].strip():
        body.pop()
    body += ["", "# ---- 汇总自各影视仓直播源（去重 + 探活，%d 台 %d 线路）----" % (added_names, added_urls)]
    body += out
    open(M3U, "w", encoding="utf-8", newline="\n").write("\n".join(body) + "\n")
    print("已写入", M3U)


if __name__ == "__main__":
    main()
