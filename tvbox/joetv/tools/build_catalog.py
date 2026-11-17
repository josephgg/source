#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从全仓 CMS 池生成 JoeTV 上游目录（离线，只读 data/live.json）。

选源口径（2026-11-17 起）：
  1. 池 = all.json + lite.json 里全部 type=1 的 HTTP CMS 库，按「主机 + MacCMS 路径」归并
     （/api.php/provide/vod 与 /provide/vod 视为同一后端）。
  2. 可用性证据一律取自 data/live.json（本地直连实测，与 Worker 同参数）；
     CI runner 在海外，对境内采集站的 no_result / search_fail 属误判，不再作为淘汰依据。
  3. 纳入条件：搜索命中合格（searchable）或分类能真出内容（browse_total >= min_browse）。
  4. 结构性硬伤（分享页 / 裸中文地址 / 直播格式 / 域名失效）一律剔除。
  5. 搜索不生效的库标 no_search，只参与分类与详情，避免污染聚合搜索。
  6. 同内容库多入口（搜索指纹一致）保留并打上同一个 cluster，
     Worker 详情阶段按 cluster 限量取线路，避免 8 条线路全是同一部片的不同 CDN。

输出：
  data/catalog.json / data/catalog.js   Worker 与测试读取
  data/candidates.json                  播放抽检候选（tools/probe_play.py）
"""
from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from paths import PROJECT, find_tvbox  # noqa: E402

TVBOX = find_tvbox()
sys.path.insert(0, str(TVBOX))

import build  # noqa: E402

CANONICAL = [
    ("movie", "电影", re.compile(r"(^电影$|电影片|4K电影)")),
    ("tv", "电视剧", re.compile(r"(^电视剧$|连续剧|剧集|大陆剧|欧美剧|日韩剧|港台剧|海外剧)")),
    ("anime", "动漫", re.compile(r"(动漫|动画片|动画)")),
    ("variety", "综艺", re.compile(r"综艺")),
    ("short", "短剧", re.compile(r"短剧")),
    ("documentary", "纪录片", re.compile(r"(纪录|记录)")),
]
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]+", re.UNICODE)
MIN_BROWSE = 8
BAD_HOSTS = {
    # 网盘搜索/分享页不是可直接播放的媒体地址
    "so.yinpai.xyz",
}
STRIP_PARAMS = {"ac", "wd", "ids", "t", "pg", "at"}
# 搜索被上游按 IP 限流的库：CF 边缘拿到 200 但 list 为空，本机连打几次直接 403。
# 它们的分类浏览正常，且内容与 cluster c-1ceb…（速播/极速/新浪/红牛/火狐）完全相同，
# 搜索交给同库其他入口即可，保留它们只用于分类与详情。
SEARCH_UNSTABLE = {
    "jyzyapi.com",       # 金鹰：2026-11-17 实测
    "huyaapi.com",       # 虎牙
    "api.guangsuapi.com",  # 光速
}


def load_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def endpoint_base(api: str) -> str:
    """剥掉查询参数里的业务动作（ac/wd/t/pg/at），留下干净的接口地址。"""
    u = urllib.parse.urlsplit(api)
    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True)
        if k.lower() not in STRIP_PARAMS
    ]
    return urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, urllib.parse.urlencode(query), ""))


TAG_WORDS = {
    "分享", "拾光", "探针", "老刘", "老刘备", "小马", "云镜", "欧歌", "天微", "香雅",
    "菜妮丝", "摸鱼儿", "潇洒", "小盒4K", "小盒仓", "PG", "OK",
}
TYPE_WORDS = {"影视", "动漫", "采集", "资源", "4K", "高清"}


def clean_name(name: str, fallback: str) -> str:
    """把「仓标签·品牌┃分类」压成用户看得懂的站名：去掉来源前缀与营销词。"""
    raw = html.unescape(str(name or ""))
    raw = EMOJI_RE.sub("", raw)
    # 全角/半角竖线、方点、双竖线都当分隔符，不同仓写法不一致
    raw = re.sub("[\u00b7\u2022\u2027\u30fb\uff5c|/\u2502\u2503\u2016\u3010\u3011]", "\u00b7", raw)
    parts = [p.strip() for p in raw.split("·")]
    chosen = []
    for part in parts:
        s = re.sub(r"[（(]\s*\d+(?:\.\d+)?\s*万\s*[)）]", "", part)
        s = re.sub(r"\b\d+(?:\.\d+)?\s*ms\s*~?", "", s, flags=re.I)
        s = re.sub(r"\s+", " ", s).strip(" -—_~")
        # 「分享魔都」「分享猫眼」这类段内还残留来源前缀，逐个剥掉
        changed = True
        while changed:
            changed = False
            for tag in TAG_WORDS:
                if s.startswith(tag) and len(s) > len(tag) + 1:
                    s = s[len(tag):].strip(" -—_~")
                    changed = True
                    break
        if not s or len(s) <= 1 or s in TAG_WORDS:
            continue
        if s in TYPE_WORDS:
            continue
        chosen.append(s)
    s = chosen[0] if chosen else raw
    s = re.sub(r"\s*(采集|线路|资源)$", "", s).strip(" -—_~·")
    s = re.sub(r"\s+", " ", s)
    return (s or fallback)[:18]


def category_map(classes: list[dict]) -> dict[str, list[str]]:
    """把上游一级分类及其子分类合并成客户端可用的一组 type_id。

    MacCMS 的 t=一级ID 往往只返回该分类自身的一条占位记录，真正内容在
    子分类里（如电影 1 -> 动作片 6、喜剧片 7...）。所以优先使用全部
    子分类 ID；没有子分类时才退回一级 ID。
    """
    children: dict[str, list[str]] = {}
    roots: list[dict] = []
    for c in classes or []:
        tid = str(c.get("type_id") or "").strip()
        pid = str(c.get("type_pid") or "0").strip()
        if not tid:
            continue
        if pid not in ("0", "", "None"):
            children.setdefault(pid, []).append(tid)
        else:
            roots.append(c)

    out: dict[str, list[str]] = {}
    for key, _label, rx in CANONICAL:
        ids: list[str] = []
        for c in roots:
            name = str(c.get("type_name") or "").strip()
            if not name or not rx.search(name):
                continue
            tid = str(c.get("type_id") or "").strip()
            if not tid:
                continue
            picks = []
            stack = [tid]
            while stack:
                cur = stack.pop()
                for child in children.get(cur, []):
                    if child not in picks:
                        picks.append(child)
                        stack.append(child)
            if not picks:
                picks = [tid]
            for x in picks:
                if x not in ids:
                    ids.append(x)
        if ids:
            out[key] = ids
    return out


def play_rank(rec: dict) -> int:
    """排序权重：越小越靠前。有正向播放证据的一律排在没有证据的前面，
    默认线路坏但备线可播（ok_secondary）仍优于完全没测过的库。"""
    if not rec:
        return 3
    verdict = rec.get("verdict")
    if verdict in ("ok", "direct") and int(rec.get("ok_streak") or 0) >= 2:
        return 0
    if verdict in ("ok", "direct"):
        return 1
    if verdict == "ok_secondary":
        return 2
    if verdict in build.PLAY_STRUCTURAL:
        return -1
    if verdict in build.PLAY_FLAKY:
        return 4
    return 3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-browse", type=int, default=MIN_BROWSE,
                    help="只可浏览的库至少要在电影/剧/短剧里拿到多少条内容")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--allow-stale", action="store_true", help="允许 live.json 超过 72 小时")
    args = ap.parse_args()

    live_path = PROJECT / "data/live.json"
    if not live_path.is_file():
        raise SystemExit("缺少 data/live.json，先运行 python tools/probe_live.py")
    live = load_json(live_path)
    age_h = (time.time() - float(live.get("ts") or 0)) / 3600
    # 实测数据只在有本地网络时才能刷新；CI 在海外跑，不能因为它过期就让构建失败。
    # 超过一个月才当硬错误，中间只提示。
    if age_h > 720 and not args.allow_stale:
        raise SystemExit(
            "data/live.json 已过期 %.0f 小时，先跑 tools/probe_live.py，或加 --allow-stale。" % age_h
        )
    if age_h > 72:
        print("[warn] data/live.json 已 %.0f 小时未更新，建议重跑 tools/probe_live.py" % age_h)

    libs = live.get("libs") or {}
    ph = build.load_play_health()

    rows = []
    for lib, rec in libs.items():
        if not rec.get("ok") or not rec.get("classes"):
            continue
        searchable = bool(rec.get("searchable"))
        browse_total = int(rec.get("browse_total") or 0)
        api = rec.get("api") or (rec.get("urls") or [""])[0]
        if not api:
            continue
        host = urllib.parse.urlsplit(api).hostname or ""
        host = host[4:] if host.startswith("www.") else host
        if host in SEARCH_UNSTABLE:
            searchable = False
        if not searchable and browse_total < args.min_browse:
            continue
        if not browse_total and not searchable:
            continue
        pr = build.play_record({"key": lib, "api": api}, ph) or {}
        verdict = pr.get("verdict") or ""
        if verdict in build.PLAY_STRUCTURAL:
            continue
        categories = category_map(rec.get("class_list") or [])
        if not categories:
            continue
        # 搜索指纹：同一内容库的不同入口会得到同一个 fp
        fps = [v["fp"] for v in (rec.get("search") or {}).values() if v.get("count")]
        cluster = "c-" + fps[0] if fps else "solo-" + lib
        rank = play_rank(pr)
        rows.append(
            {
                "lib": lib,
                "api": api,
                "name": rec.get("name") or lib,
                "categories": categories,
                "searchable": searchable,
                "browse_total": browse_total,
                "latency_ms": int(rec.get("latency_ms") or 9999),
                "hit_rate": rec.get("hit_rate"),
                "play_verdict": verdict,
                "play_streak": int(pr.get("ok_streak") or 0),
                "skip_first_line": verdict == "ok_secondary",
                "no_search": not searchable,
                "cluster": cluster,
                "_rank": (rank, 0 if searchable else 1, int(rec.get("latency_ms") or 9999)),
            }
        )

    rows.sort(key=lambda r: r["_rank"])
    if args.limit:
        rows = rows[: args.limit]

    used: Counter = Counter()
    for i, row in enumerate(rows, 1):
        row["id"] = "s%02d" % i
        base = clean_name(row["name"], "源%02d" % i)
        used[base] += 1
        row["label"] = base if used[base] == 1 else "%s%d" % (base, used[base])
        row["rank"] = i
        row.pop("_rank", None)
        row.pop("lib", None)

    data = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source_count": len(rows),
        "stats": {
            "searchable": sum(1 for r in rows if not r["no_search"]),
            "browse_only": sum(1 for r in rows if r["no_search"]),
            "clusters": len({r["cluster"] for r in rows}),
        },
        "classes": [{"type_id": k, "type_name": name} for k, name, _rx in CANONICAL],
        "sources": rows,
    }
    outdir = PROJECT / "data"
    outdir.mkdir(parents=True, exist_ok=True)
    with (outdir / "catalog.json").open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with (outdir / "catalog.js").open("w", encoding="utf-8", newline="\n") as f:
        f.write("// Generated by tools/build_catalog.py; do not edit by hand.\n")
        f.write("export const CATALOG = ")
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    by_cluster = defaultdict(list)
    for r in rows:
        by_cluster[r["cluster"]].append(r["label"])
    for r in rows:
        print(
            "%-4s %-16s %-8s %-13s cls=%-2d br=%-4s ms=%-5s cluster=%d"
            % (
                r["id"],
                r["label"],
                "browse" if r["no_search"] else "search",
                r["play_verdict"] or "-",
                len(r["categories"]),
                r["browse_total"],
                r["latency_ms"],
                len(by_cluster[r["cluster"]]),
            )
        )

    candidates = {
        "_comment": "JoeTV 候选播放抽检，不属于最终 TVBox 配置",
        "sites": [
            {
                "key": r["id"],
                "name": r["label"],
                "type": 1,
                "api": r["api"],
                "searchable": 0 if r["no_search"] else 1,
                "quickSearch": 0 if r["no_search"] else 1,
            }
            for r in rows
        ],
    }
    with (outdir / "candidates.json").open("w", encoding="utf-8", newline="\n") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(
        "sources=%d searchable=%d browse_only=%d clusters=%d live_age=%.0fh"
        % (data["source_count"], data["stats"]["searchable"], data["stats"]["browse_only"],
           data["stats"]["clusters"], age_h)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
