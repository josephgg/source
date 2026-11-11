#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测量站点的搜索质量：返回条数 / 标题命中率 / wd 参数是否被忽略。

为什么需要这个工具
----------------
聚合搜索会把所有可搜站点并发发出去，结果按站点分组交给用户。只要其中有
几个站「不认 wd 参数、直接吐整库热播列表」，用户看到的就是「搜什么都一堆
不相关」。靠站名和类目猜不出来，必须实测。

测法：用两个语义上毫无交集的词（庆余年 / 熊出没）各搜一次。
  · 命中率低 + 两次结果高度重合  → wd 被忽略，返回的是固定列表（最糟）
  · 命中率高                     → 搜索正常
  · 返回 0 条                    → 搜索接口关闭或不支持

输出 tvbox/search_quality.json，供 build.py 决定哪些站退出聚合搜索。

用法：
    python tools/probe_search.py                  # 测 api/lite.json 里的 HTTP 站
    python tools/probe_search.py --file api/all.json --workers 16
    python tools/probe_search.py --kw 庆余年 --kw2 熊出没
"""
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from build import api_norm, ascii_url  # noqa: E402

OUT = os.path.join(ROOT, "search_quality.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 用来判定「wd 被忽略」的阈值：两次结果 top20 的重合度
OVERLAP_BAD = 0.5
# 标题命中率分档
HIT_GOOD = 0.55
HIT_OK = 0.25


def search_url(api, kw, page=1):
    u = api.strip()
    if re.search(r"[?&]ac=", u):
        u = re.sub(r"([?&]ac=)[^&]*", r"\1videolist", u)
    else:
        u += ("&" if "?" in u else "?") + "ac=videolist"
    u += "&wd=" + urllib.parse.quote(kw) + "&pg=%d" % page
    return u


def parse_names(txt):
    """把 CMS 搜索响应解成标题列表；支持 JSON 与 type=0 的 MacCMS XML。"""
    txt = txt.strip()
    if txt.startswith("<"):
        try:
            root = ET.fromstring(re.sub(r"^\s*<\?xml[^>]*\?>", "", txt))
            videos = root.findall(".//video")
            if not videos:
                return None
            names = []
            for video in videos:
                name = video.findtext("name") or video.findtext("title")
                if name:
                    names.append(name.strip())
            return names
        except (ET.ParseError, ValueError):
            return None
    if not txt.startswith(("{", "[")):
        return None
    try:
        d = json.loads(txt)
    except Exception:  # noqa: BLE001
        return None
    if isinstance(d, list):
        lst = d
    elif isinstance(d, dict):
        data = d.get("data")
        lst = d.get("list") or (data.get("list") if isinstance(data, dict) else []) or []
    else:
        return None
    if not isinstance(lst, list):
        return None
    out = []
    for it in lst:
        if isinstance(it, dict):
            n = it.get("vod_name") or it.get("name") or it.get("title")
            if n:
                out.append(str(n).strip())
    return out


def fetch(api, kw, timeout):
    u = search_url(api, kw)
    t0 = time.time()
    try:
        req = urllib.request.Request(ascii_url(u), headers={
            "User-Agent": UA, "Accept-Encoding": "identity"})
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            body = r.read(1024 * 1024)
        ms = int((time.time() - t0) * 1000)
        names = parse_names(body.decode("utf-8", "replace"))
        if names is None:
            return {"ms": ms, "names": None, "err": "not-json"}
        return {"ms": ms, "names": names}
    except urllib.error.HTTPError as e:
        return {"ms": int((time.time() - t0) * 1000), "names": None, "err": "http%d" % e.code}
    except Exception as e:  # noqa: BLE001
        return {"ms": int((time.time() - t0) * 1000), "names": None,
                "err": type(e).__name__}


def overlap(a, b, n=20):
    sa, sb = set(a[:n]), set(b[:n])
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# 成人内容特征词。正规片库偶尔会有「伦理片」分类（港台老片），
# 但搜索结果标题里同时出现两个以上这类词，基本可以确定是成人站。
ADULT_WORDS = (
    "无码", "步兵", "骑兵", "赤裸", "裸体", "啪啪", "性爱", "三级片",
    "成人", "诱惑", "偷拍", "自慰", "口交", "乱伦", "幼齿", "porn",
    "av女", "女优", "里番", "h漫", "约炮", "情色",
)


def adult_hits(names):
    """返回命中的特征词与条数。"""
    hit = set()
    n = 0
    for t in names:
        low = t.lower()
        for w in ADULT_WORDS:
            if w in low:
                hit.add(w)
                n += 1
                break
    return sorted(hit), n


def judge(ra, rb, kw1, kw2):
    """返回 (verdict, 说明)。verdict: good / ok / weak / ignored / empty / unknown"""
    na = ra.get("names")
    nb = rb.get("names")
    if na is None and nb is None:
        return "unknown", "两次都没拿到 JSON（%s/%s）" % (ra.get("err"), rb.get("err"))
    if na is None or nb is None:
        # 只有一个词能拿到结果，无法比对重合度，只按命中率判
        names = na if na is not None else nb
        kw = kw1 if na is not None else kw2
        if not names:
            return "empty", "搜索返回 0 条"
        rate = sum(1 for x in names if kw in x) / len(names)
        if rate >= HIT_GOOD:
            return "good", "命中率 %.0f%%（仅一次成功）" % (rate * 100)
        if rate >= HIT_OK:
            return "ok", "命中率 %.0f%%（仅一次成功）" % (rate * 100)
        return "weak", "命中率 %.0f%%（仅一次成功）" % (rate * 100)

    if not na and not nb:
        return "empty", "两个词都返回 0 条"
    ha = sum(1 for x in na if kw1 in x) / len(na) if na else 0.0
    hb = sum(1 for x in nb if kw2 in x) / len(nb) if nb else 0.0
    jac = overlap(na, nb)
    if jac >= OVERLAP_BAD and max(ha, hb) < HIT_GOOD:
        return "ignored", "两次结果重合 %.0f%%，wd 被忽略（回固定列表）" % (jac * 100)
    rate = (ha + hb) / 2
    if rate >= HIT_GOOD:
        return "good", "命中率 %.0f%% / %.0f%%，重合 %.0f%%" % (ha * 100, hb * 100, jac * 100)
    if rate >= HIT_OK:
        return "ok", "命中率 %.0f%% / %.0f%%，重合 %.0f%%" % (ha * 100, hb * 100, jac * 100)
    return "weak", "命中率 %.0f%% / %.0f%%，重合 %.0f%%" % (ha * 100, hb * 100, jac * 100)


def suggest(verdict, why, adult, hit_rate):
    """把测量结果翻成构建时可执行的动作。

    keep     : 不动
    quick_off: 退出首页快速搜索（返回一堆但相关性差），完整搜索仍保留
    disable  : 退出聚合搜索（接口不支持/返回非 JSON/wd 无效），浏览仍可用
    adult    : 成人内容，整站剔除
    """
    if adult:
        return "adult"
    if verdict in ("ignored", "empty"):
        return "disable"
    if verdict == "unknown":
        # 「返回非 JSON」= 客户端拿到的也是 HTML/脚本，搜索必然失败 → 关
        # URL 错误/超时 = 我这边网络问题，不能误杀
        if "not-json" in why:
            return "disable"
        return "keep"
    if verdict == "weak":
        return "quick_off"
    if hit_rate < 0.7:
        return "quick_off"
    return "keep"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="api/lite.json")
    ap.add_argument("--kw", default="庆余年")
    ap.add_argument("--kw2", default="熊出没")
    ap.add_argument("--timeout", type=int, default=12)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--merge", action="store_true",
                    help="保留当前接口的有效历史记录，移除已下线的站点")
    ap.add_argument("--max-age", type=int, default=0,
                    help="配合 --merge：记录多少秒内无需重测；0 表示全部重测")
    ap.add_argument("--refresh", action="store_true", help="忽略缓存有效期，强制重测")
    args = ap.parse_args()

    path = args.file if os.path.isabs(args.file) else os.path.join(ROOT, args.file)
    conf = json.load(open(path, encoding="utf-8"))
    sites = conf["sites"]

    # 只有 type=0/1 的 HTTP CMS 能直接套 ac=videolist。旧版会把 type=3 的
    # drpy/js 脚本也当搜索接口请求，既浪费数千请求，又产生一堆假 unknown。
    # 同一后端的 from/at 与 ac 写法只测一个入口，结论由 build.py 按 api_norm 继承。
    testable, skipped, seen_api = [], [], set()
    for s in sites:
        api = str(s.get("api") or "")
        if not api.startswith("http") or s.get("type") not in (0, 1):
            skipped.append(s)
            continue
        norm = api_norm(s)
        if norm in seen_api:
            continue
        seen_api.add(norm)
        testable.append(s)

    old = {}
    if args.merge:
        try:
            with open(args.out, encoding="utf-8") as f:
                old = {k: v for k, v in json.load(f).items()
                       if not k.startswith("_") and isinstance(v, dict)}
        except (OSError, ValueError):
            old = {}
    now = int(time.time())
    active_keys = {s["key"] for s in testable}
    res = {k: old[k] for k in active_keys if k in old}
    pending = []
    for s in testable:
        rec = old.get(s["key"]) or {}
        fresh = (args.max_age > 0 and not args.refresh and rec.get("tested_at") and
                 now - int(rec["tested_at"]) <= args.max_age)
        if not fresh:
            pending.append(s)

    print("[probe] CMS 后端 %d 个：本轮实测 %d，缓存命中 %d；跳过 %d 个非 CMS 站"
          % (len(testable), len(pending), len(testable) - len(pending), len(skipped)))

    def one(s):
        api = s["api"]
        ra = fetch(api, args.kw, args.timeout)
        rb = fetch(api, args.kw2, args.timeout)
        verdict, why = judge(ra, rb, args.kw, args.kw2)
        titles1 = (ra["names"] or [])[:60]
        titles2 = (rb["names"] or [])[:60]
        awords, acnt = adult_hits(titles1 + titles2)

        # 相关性：只统计「返回 ≥3 条」的那次搜索，取较低值。
        # 某站没有某部片是正常的（返回 0 条），不能当成「搜不准」。
        rates = []
        for names, kw in ((titles1, args.kw), (titles2, args.kw2)):
            if len(names) >= 3:
                rates.append(sum(1 for x in names if kw in x) / len(names))
        rate = min(rates) if rates else 1.0

        # 单个标题偶然命中特征词不应整站剔除；多条且达到明显占比才判成人站。
        total_titles = max(1, len(titles1) + len(titles2))
        adult_confident = acnt >= 2 and (acnt >= 4 or acnt / total_titles >= 0.10)

        return s["key"], {
            "name": s.get("name"),
            "api": api,
            "verdict": verdict,
            "why": why,
            "action": suggest(verdict, why, adult_confident, rate),
            "hit_rate": round(rate, 3),
            "n1": len(ra["names"] or []),
            "n2": len(rb["names"] or []),
            "ms": ra.get("ms"),
            "adult": awords,
            "adult_n": acnt,
            "titles1": titles1,
            "titles2": titles2,
            "tested_at": int(time.time()),
        }

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for key, rec in pool.map(one, pending):
            res[key] = rec

    order = ["ignored", "empty", "weak", "unknown", "ok", "good"]
    for key in sorted(res, key=lambda k: (order.index(res[k]["verdict"]),
                                          -(res[k]["n1"] or 0))):
        r = res[key]
        flag = "  ⚠成人(%s)" % "/".join(r["adult"][:3]) if r["adult"] else ""
        print("  %-9s %-10s %-18s n=%-4s %s%s"
              % (r["action"], r["verdict"], (r["name"] or "")[:18],
                 r["n1"], r["why"], flag))

    from collections import Counter
    print("\n[probe] 判定分布:", dict(Counter(r["verdict"] for r in res.values()
                                              if not r.get("name") is None)))
    print("[probe] 处置分布:",
          dict(Counter(r["action"] for r in res.values() if "action" in r)))

    # 成人内容站点：搜索结果里成片出现特征词
    bad_adult = [r for r in res.values() if r["adult"]]
    if bad_adult:
        print("[probe] 疑似成人内容站点 %d 个:" % len(bad_adult))
        for r in bad_adult:
            print("   - %-18s 命中 %d 条 / 特征词 %s"
                  % ((r["name"] or "")[:18], r["adult_n"], "/".join(r["adult"][:4])))

    # 站间重复：同一关键词下标题集合高度重合 → 同一个内容库的不同外壳
    keys = [k for k in res if len(res[k]["titles1"]) >= 5]
    pairs = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = set(res[keys[i]]["titles1"]), set(res[keys[j]]["titles1"])
            jac = len(a & b) / len(a | b) if (a | b) else 0
            if jac >= 0.6:
                pairs.append((jac, keys[i], keys[j]))
    pairs.sort(reverse=True)
    if pairs:
        print("\n[probe] 搜索结果显示为同一内容库（Jaccard ≥ 0.6）:")
        for jac, ka, kb in pairs:
            print("   %.0f%%  %s  ==  %s" % (jac * 100,
                                             (res[ka]["name"] or "")[:16],
                                             (res[kb]["name"] or "")[:16]))
    res["_dups"] = [{"jaccard": round(j, 2), "a": ka, "b": kb} for j, ka, kb in pairs]
    if skipped:
        print("[probe] 跳过（需 jar 执行，无法直测）:",
              ", ".join((s.get("name") or "")[:14] for s in skipped[:12]),
              "..." if len(skipped) > 12 else "")

    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(res, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print("[probe] 已写 %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
