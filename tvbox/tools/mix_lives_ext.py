"""把外部 m3u 直播源汇总进仓库根的 iptv_filtered.m3u。

与 mix_lives.py 的分工：
  mix_lives.py  抓「各影视仓配置里的 lives 字段」
  本脚本        抓「独立分发的 m3u 文件」（如 IPTV 生成类项目）

流程：抓取 → 解析 → 与现有清单去重（URL 与频道名双向）→ 按分组限量取候选
      → 并发探活（只留真能播的）→ 追加到文件末尾

用法：
    python tools/mix_lives_ext.py            # 只统计，不写文件
    python tools/mix_lives_ext.py --write    # 写入（自动备份 .bak）
    python tools/mix_lives_ext.py --write --probe-limit 800
"""
import argparse
import concurrent.futures
import json
import os
import re
import ssl
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TVBOX = os.path.dirname(HERE)
ROOT = os.path.dirname(TVBOX)
M3U = os.path.join(ROOT, "iptv_filtered.m3u")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

UA = "okhttp/3.15"

# 外部源：只放独立分发的 m3u（影视仓配置的 lives 走 mix_lives.py）
EXT_SOURCES = [
    {
        "id": "khw934",
        "name": "khw934/TV",
        "url": "https://raw.githubusercontent.com/khw934/TV/master/output/result.m3u",
    },
    {
        "id": "hotel-tv",
        "name": "huangshaoze37-tech/hotel-tv",
        "url": "https://raw.githubusercontent.com/huangshaoze37-tech/hotel-tv/main/live_all.m3u",
    },
]

MARK = "# ---- 以下汇总自外部直播源（去重 + 探活）----"

RANK = {"央视": 0, "卫视": 1, "港澳台": 2, "地方台": 3, "其他": 4}

# 每类最多取多少条候选（探活前的上限，控制耗时）
GROUP_CAP = {"央视": 100, "卫视": 140, "港澳台": 90, "地方台": 200, "其他": 80}

LOCAL = re.compile(
    r"(北京|上海|天津|重庆|河北|山西|辽宁|吉林|黑龙江|江苏|浙江|安徽|福建|江西|山东|"
    r"河南|湖北|湖南|广东|广西|海南|四川|贵州|云南|西藏|陕西|甘肃|青海|宁夏|新疆|"
    r"内蒙古|深圳|杭州|南京|成都|武汉|广州|苏州|青岛|厦门|宁波|大连|济南|沈阳)"
)

# 明显不是电视直播的流（点播、测试图、广告轮播）
JUNK = re.compile(r"(测试|test|广告|推广|轮播|购物|彩票|epg|logo|blank|colorbar)", re.I)


def norm(s):
    """频道名归一：去掉画质后缀、括号说明、分隔符，便于跨源比对同名台"""
    s = re.sub(r"[（(\[【].*?[)）\]】]", "", s or "")
    s = re.sub(r"(?i)\b(hd|fhd|uhd|4k|8k|sd|h265|hevc)\b", "", s)
    for w in ("高清", "超清", "标清", "蓝光", "超高清"):
        s = s.replace(w, "")
    return re.sub(r"[\s\-_·|]+", "", s).lower()


def group_of(name):
    n = norm(name)
    if re.search(r"(cctv|央视|中央)", n):
        return "央视"
    if re.search(r"(凤凰|翡翠|明珠|tvb|澳门|香港|台湾|中天|东森|三立|民视|台视|华视|中视|"
                 r"tvbs|tvb|now|viu|hoy|有线|澳视)", n):
        return "港澳台"
    if "卫视" in n:
        return "卫视"
    if LOCAL.search(n):
        return "地方台"
    return "其他"


def probe(url, timeout=6):
    req = urllib.request.Request(url.split("|")[0], headers={
        "User-Agent": UA, "Range": "bytes=0-2047"})
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


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read().decode("utf-8", "replace")


def parse_channels(name, txt):
    """解析 m3u / txt 两种格式，返回 [(title, url, group)]"""
    out = []
    if "#EXTINF" in txt or txt.lstrip().startswith("#EXTM3U"):
        title = ""
        for line in (l.strip() for l in txt.splitlines()):
            if line.startswith("#EXTINF"):
                title = line.rsplit(",", 1)[-1].strip()
            elif line and not line.startswith("#"):
                if title:
                    out.append((title, line, name))
                title = ""
    return out


def load_existing():
    """读现有 m3u：返回 (所有行, 已有 url key 集合, 已有频道名集合, 行数)"""
    if not os.path.exists(M3U):
        return [], set(), set(), 0
    with open(M3U, encoding="utf-8") as f:
        lines = f.read().splitlines()
    keys, names = set(), set()
    title = ""
    for line in (l.strip() for l in lines):
        if line.startswith("#EXTINF"):
            title = line.rsplit(",", 1)[-1].strip()
            if title:
                names.add(norm(title))
        elif line and not line.startswith("#"):
            keys.add(key_of(line))
            title = ""
    return lines, keys, names, len(lines)


def strip_prev_block(lines):
    """去掉上一次本脚本写入的段，保证重复执行幂等"""
    for i, l in enumerate(lines):
        if l.strip().startswith(MARK):
            return lines[:i]
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="写入 m3u（默认只统计）")
    ap.add_argument("--probe-limit", type=int, default=600, help="探活候选上限")
    ap.add_argument("--probe-workers", type=int, default=48)
    ap.add_argument("--probe-timeout", type=int, default=6)
    args = ap.parse_args()

    lines, have_keys, have_names, _ = load_existing()
    # 增量追加：上一轮写入的频道原样保留（已在 have_* 里参与去重），
    # 本轮只追加新探到的台。想整体重建就先删掉 MARK 段再跑。
    base = list(lines)
    while base and not base[-1].strip():
        base.pop()
    print("[base] 现有清单 %d 行，%d 个频道名，%d 条线路" % (len(base), len(have_names), len(have_keys)))

    # 1. 抓取 + 解析
    all_chan = []
    for src in EXT_SOURCES:
        try:
            txt = fetch(src["url"])
            chans = parse_channels(src["name"], txt)
            print("[fetch] %-26s %d 条" % (src["name"], len(chans)))
            all_chan.extend((t, u, src["id"]) for t, u, _ in chans)
        except Exception as e:  # noqa: BLE001
            print("[fetch] %-26s ERR %s" % (src["name"], str(e)[:60]))

    # 2. 去重：URL 与频道名都排除已有的，同时做内部去重
    cand, seen_k, seen_n = [], set(), set()
    dup_url = dup_name = 0
    for title, url, sid in all_chan:
        if not url.startswith("http"):
            continue
        if JUNK.search(title) or JUNK.search(url):
            continue
        k, n = key_of(url), norm(title)
        if k in have_keys or k in seen_k:
            dup_url += 1
            continue
        if not n or n in have_names or n in seen_n:
            dup_name += 1
            continue
        seen_k.add(k)
        seen_n.add(n)
        cand.append((title, url, group_of(title), sid))
    print("[dedup] 候选 %d（URL 重复 %d，频道名重复 %d）" % (len(cand), dup_url, dup_name))

    # 3. 按分组限量（央视/卫视优先，避免地方台淹没名额）
    cand.sort(key=lambda x: (RANK[x[2]], x[0]))
    picked, cnt = [], {}
    for item in cand:
        g = item[2]
        if cnt.get(g, 0) >= GROUP_CAP.get(g, 60):
            continue
        cnt[g] = cnt.get(g, 0) + 1
        picked.append(item)
    picked = picked[: args.probe_limit]
    print("[cap ] 探活候选 %d，分组 %s" % (len(picked), cnt))

    # 4. 并发探活
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.probe_workers) as ex:
        oks = list(ex.map(lambda it: probe(it[1], args.probe_timeout), picked))
    alive = [it for it, ok in zip(picked, oks) if ok]
    print("[probe] %d/%d 可播，耗时 %.0fs" % (len(alive), len(picked), time.time() - t0))
    if not alive:
        print("没有可播线路，不写入")
        return 0

    # 5. 组织输出：同组内按名称排，组间按 RANK
    alive.sort(key=lambda x: (RANK[x[2]], x[0]))
    body = [""]
    body.append(MARK + "（%d 台）----" % len(alive))
    by_src = {}
    for title, url, g, sid in alive:
        by_src[sid] = by_src.get(sid, 0) + 1
        body.append('#EXTINF:-1 tvg-name="%s" group-title="%s",%s' % (title, g, title))
        body.append(url)
    stat = {g: sum(1 for x in alive if x[2] == g) for g in RANK}
    print("[stat] 分组 %s" % {k: v for k, v in stat.items() if v})
    print("[stat] 来源 %s" % by_src)

    if not args.write:
        print("\n（未写入，加 --write 生效）")
        return 0

    # 备份后写入
    if os.path.exists(M3U):
        import shutil
        shutil.copyfile(M3U, M3U + ".bak")
    with open(M3U, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(base + body) + "\n")
    print("[write] 已写入 %s，总行数 %d" % (M3U, len(base + body)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
