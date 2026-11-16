#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从既有 TVBox 全量仓生成 JoeTV 候选上游。

只选普通 CMS（type=1、http/https），排除已经是稳定精选的 9 个 key，
按 API 归一化去重，再结合搜索实测、CMS 探活和播放体检选择入口。
输出：
  data/catalog.json   给 Worker/测试读取的完整目录
  data/candidates.json 给 tools/probe_play.py 做真实播放抽检
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

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
BAD_HOSTS = {
    # 网盘搜索/分享页不是可直接播放的媒体地址
    "so.yinpai.xyz",
}
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]+", re.UNICODE
)
UA = "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 JoeTV/1.0"


def load_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def clean_name(name: str, fallback: str) -> str:
    raw = html.unescape(str(name or ""))
    raw = EMOJI_RE.sub("", raw)
    parts = re.split(r"[·|｜]", raw)
    prefixes = {"分享", "拾光", "探针", "老刘", "小马", "OK", "小盒仓", "小盒4K"}
    chosen = []
    for part in parts:
        s = part.replace("┃", " ").strip(" ·-—_")
        s = re.sub(r"[（(]\s*\d+(?:\.\d+)?\s*万\s*[)）]", "", s)
        s = re.sub(r"\b\d+(?:\.\d+)?\s*ms\s*~?", "", s, flags=re.I)
        s = re.sub(r"\s+", " ", s).strip(" ~-—_")
        if not s or s in prefixes or re.fullmatch(r"[\d.~ms]+", s, re.I):
            continue
        if re.fullmatch(r"(采集|资源|影视)", s):
            continue
        chosen.append(s)
    s = chosen[0] if chosen else raw
    s = re.sub(r"\s*(采集|线路)$", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    return (s or fallback)[:18]


def play_rank(rec: dict) -> int:
    if not rec:
        return 0
    if rec.get("verdict") in ("ok", "direct") and int(rec.get("ok_streak") or 0) >= 2:
        return 6
    if rec.get("verdict") in ("ok", "direct"):
        return 5
    if rec.get("verdict") == "ok_secondary":
        return 4
    if rec.get("verdict") in build.PLAY_STRUCTURAL:
        return -1
    if rec.get("verdict") in build.PLAY_FLAKY:
        return 1
    return 2


def alive_ms(rec: dict) -> int:
    try:
        return int(rec.get("ms") or 999999)
    except (TypeError, ValueError):
        return 999999


def endpoint_base(api: str) -> str:
    u = urllib.parse.urlsplit(api)
    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True)
        if k.lower() not in {"ac", "wd", "ids", "t", "pg", "at"}
    ]
    return urllib.parse.urlunsplit(
        (u.scheme, u.netloc, u.path, urllib.parse.urlencode(query), "")
    )


def http_text(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json,text/xml,application/xml,text/plain,*/*",
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        raw = r.read()
        ctype = r.headers.get("Content-Type", "")
    m = re.search(r"charset=([\w-]+)", ctype, re.I)
    enc = m.group(1) if m else "utf-8"
    try:
        return raw.decode(enc, errors="replace").lstrip("\ufeff")
    except LookupError:
        return raw.decode("utf-8", errors="replace").lstrip("\ufeff")


def parse_classes(text: str) -> list[dict]:
    text = text.strip()
    if not text:
        return []
    if text[0] in "[{":
        try:
            data = json.loads(text)
        except ValueError:
            return []
        raw = data.get("class") or data.get("classes") or []
        if isinstance(raw, dict):
            raw = list(raw.values())
        return [x for x in raw if isinstance(x, dict)]
    out = []
    for block in re.findall(r"<class>([\s\S]*?)</class>", text, re.I):
        out.append(
            {
                "type_id": xml_tag(block, "ty_id") or xml_tag(block, "type_id") or xml_tag(block, "id"),
                "type_name": xml_tag(block, "ty") or xml_tag(block, "type_name") or xml_tag(block, "name"),
                "type_pid": xml_tag(block, "type_pid") or "0",
            }
        )
    return [x for x in out if x.get("type_id") and x.get("type_name")]


def xml_tag(block: str, tag: str) -> str:
    m = re.search(r"<%s[^>]*>([\s\S]*?)</%s>" % (re.escape(tag), re.escape(tag)), block, re.I)
    if not m:
        return ""
    val = m.group(1)
    c = re.search(r"<!\[CDATA\[([\s\S]*?)\]\]>", val)
    return html.unescape((c.group(1) if c else val).strip())


def category_map(classes: list[dict]) -> dict[str, list[str]]:
    """把上游一级分类及其子分类合并成客户端可用的一组 type_id。

    MacCMS 的 t=一级ID 往往只返回该分类自身的一条占位记录，真正内容在
    子分类里（如电影 1 -> 动作片 6、喜剧片 7...）。所以优先使用全部
    子分类 ID；没有子分类时才退回一级 ID。
    """
    children: dict[str, list[str]] = {}
    roots: list[dict] = []
    for c in classes:
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


def fetch_categories(api: str) -> tuple[dict[str, list[str]], str]:
    url = endpoint_base(api)
    sep = "&" if "?" in url else "?"
    try:
        text = http_text(url + sep + "ac=list", timeout=12)
        classes = parse_classes(text)
        if not classes:
            # 少数 CMS 把分类放在普通详情响应里，再试一次详情首页
            text = http_text(url + sep + "ac=detail&pg=1", timeout=12)
            classes = parse_classes(text)
        return category_map(classes), ""
    except Exception as e:  # noqa: BLE001
        return {}, "%s: %s" % (type(e).__name__, e)


def build_rows() -> list[dict]:
    allconf = load_json(TVBOX / "api/all.json")
    liteconf = load_json(TVBOX / "api/lite.json")
    sources = load_json(TVBOX / "sources.json")
    bconf = sources.get("build") or {}
    block_hosts = {str(h).lower() for h in bconf.get("block_hosts") or []}
    lite_sites = liteconf.get("sites") or []
    lite_keys = {s.get("key") for s in lite_sites}
    lite_norms = {build.api_norm(s) for s in lite_sites}
    sites = allconf.get("sites") or []
    ph = build.load_play_health()
    sq = build.load_search_quality()
    sq_idx = build.index_search_quality(sq)
    alive = build.current_alive(sites, build.load_alive())

    groups: dict[str, list[dict]] = {}
    for s in sites:
        api = str(s.get("api") or "")
        key = s.get("key")
        if (
            key in lite_keys
            or build.api_norm(s) in lite_norms
            or s.get("type") != 1
            or not api.startswith(("http://", "https://"))
        ):
            continue
        if build.api_kind(s) != "http":
            continue
        host = urllib.parse.urlsplit(api).hostname or ""
        if host in BAD_HOSTS or any(h in host for h in block_hosts):
            continue
        if any(x in api for x in ("127.0.0.1", "localhost", "0.0.0.0", "[::1]")):
            continue
        groups.setdefault(build.api_norm(s), []).append(s)

    rows = []
    for norm, aliases in groups.items():
        best = None
        for s in aliases:
            pr = build.play_record(s, ph) or {}
            qr = build.search_record(s, sq, sq_idx) or {}
            ar = alive.get(s.get("key")) or {}
            score = (
                1 if qr.get("action") == "keep" else 0,
                play_rank(pr),
                1 if ar.get("code") == "ok" else 0,
                -alive_ms(ar),
            )
            if best is None or score > best[0]:
                best = (score, s, pr, qr, ar)
        assert best
        score, s, pr, qr, ar = best
        if qr.get("action") != "keep" or ar.get("code") != "ok":
            continue
        api = str(s.get("api") or "")
        verdict = pr.get("verdict") or ""
        verified = (
            verdict in ("ok", "ok_secondary", "direct")
            and not pr.get("requires_referer")
            and not pr.get("codec_unsafe")
        )
        rows.append(
            {
                "key": s.get("key"),
                "name": s.get("name"),
                "api": api,
                "aliases": len(aliases),
                "alive_ms": alive_ms(ar),
                "search_action": qr.get("action"),
                "play_verdict": verdict,
                "play_streak": int(pr.get("ok_streak") or 0),
                "requires_referer": bool(pr.get("requires_referer")),
                "codec_unsafe": bool(pr.get("codec_unsafe")),
                "skip_first_line": verdict == "ok_secondary",
                "verified": verified,
                "_score": score,
            }
        )
    rows.sort(key=lambda r: r["_score"], reverse=True)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-categories", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = build_rows()
    if args.limit:
        rows = rows[: args.limit]
    cats: Counter = Counter()
    for i, row in enumerate(rows, 1):
        if args.no_categories:
            row["categories"] = {}
        else:
            row["categories"], err = fetch_categories(row["api"])
            if err:
                print("[cat] %-24s %s" % (row["name"], err))
            cats["with_cats" if row["categories"] else "no_cats"] += 1
        row["id"] = "s%02d" % i
        row["label"] = clean_name(row["name"], "源%02d" % i)
        row.pop("_score", None)
        print(
            "[%02d/%02d] %-5s %-22s %-13s alive=%sms cats=%s"
            % (
                i,
                len(rows),
                "ACTIVE" if row["verified"] else "skip",
                row["label"],
                row["play_verdict"] or "-",
                row["alive_ms"],
                ",".join(row["categories"]),
            )
        )

    # 只用启用中的上游参与重名编号，避免被跳过的源把序号顶到“创享3”。
    used: Counter = Counter()
    for row in rows:
        if not row["verified"]:
            continue
        base = row["label"]
        used[base] += 1
        if used[base] > 1:
            row["label"] = "%s%d" % (base, used[base])

    active = [row for row in rows if row["verified"]]
    lite_keys = [
        s.get("key") for s in (load_json(TVBOX / "api/lite.json").get("sites") or []) if s.get("key")
    ]
    data = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "excluded_lite_keys": sorted(lite_keys),
        "source_count": len(active),
        "candidate_count": len(rows),
        "classes": [{"type_id": k, "type_name": name} for k, name, _rx in CANONICAL],
        "sources": active,
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

    candidates = {
        "_comment": "JoeTV 候选播放抽检，不属于最终 TVBox 配置",
        "sites": [
            {
                "key": row["id"],
                "name": row["label"],
                "type": 1,
                "api": row["api"],
                "searchable": 1,
                "quickSearch": 1,
            }
            for row in rows
        ],
    }
    with (outdir / "candidates.json").open("w", encoding="utf-8", newline="\n") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("active=%d candidates=%d %s" % (len(active), len(rows), dict(cats)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
