#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地直连实测 CMS 上游：分类、搜索命中、关键词是否生效、延迟。

CI runner 在海外，对境内采集站常有 DNS/线路误判（表现为 no_result / search_fail），
用它决定「谁能进 JoeTV」会把活站判死。这里给出一条与 Worker 请求参数完全一致的
本地实测路径，结果写入 data/live.json，供 build_catalog.py 离线选源。

用法：
    python tools/probe_live.py                 # 只测缺失/过期的库
    python tools/probe_live.py --force         # 全量重测
    python tools/probe_live.py --jobs 4 --delay 0.6
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from paths import PROJECT, find_tvbox  # noqa: E402

TVBOX = find_tvbox()
sys.path.insert(0, str(TVBOX))

import build  # noqa: E402
import build_catalog as bc  # noqa: E402

UA = "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 JoeTV/1.0"
KEYWORDS = ("庆余年", "繁花")
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MAX_AGE_H = 20


def load_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def http_json(url: str, timeout: float = 12.0):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "application/json,text/xml,text/plain,*/*"},
    )
    started = time.time()
    try:
        with OPENER.open(req, timeout=timeout) as r:
            raw = r.read()
            ctype = r.headers.get("Content-Type", "")
        ms = int((time.time() - started) * 1000)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "err": type(e).__name__, "ms": int((time.time() - started) * 1000)}
    m = re.search(r"charset=([\w-]+)", ctype, re.I)
    enc = (m.group(1) if m else "utf-8").lower()
    try:
        text = raw.decode("gb18030" if enc in ("gb2312", "gbk") else enc, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    text = text.lstrip("\ufeff").strip()
    if not text:
        return {"ok": False, "err": "empty", "ms": ms}
    low = text[:200].lower()
    if low.startswith("<!doctype") or low.startswith("<html"):
        return {"ok": False, "err": "html", "ms": ms}
    if text[0] == "<":
        return {"ok": True, "ms": ms, "xml": text, "items": [], "classes": []}
    try:
        data = json.loads(text)
    except ValueError:
        return {"ok": False, "err": "not_json", "ms": ms}
    if not isinstance(data, dict):
        return {"ok": False, "err": "not_object", "ms": ms}
    classes = data.get("class") or data.get("classes") or []
    if isinstance(classes, dict):
        classes = list(classes.values())
    return {
        "ok": True,
        "ms": ms,
        "items": data.get("list") or data.get("data") or [],
        "classes": [c for c in classes if isinstance(c, dict)],
    }


def with_params(api: str, **params) -> str:
    base = bc.endpoint_base(api)
    parts = urllib.parse.urlsplit(base)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query += [(k, str(v)) for k, v in params.items()]
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), "")
    )


def normalize_title(value: str) -> str:
    return re.sub(r"[\s·:：\-—_.,，。!！?？'\"“”‘’()\[\]【】《》/\\]+", "", str(value).lower())


def fingerprint(names) -> str:
    """片名集合指纹：用于识别「同一内容库的两个入口」。"""
    keys = sorted({normalize_title(n) for n in names if n})
    return hashlib.sha1("|".join(keys[:60]).encode("utf-8")).hexdigest()[:12]


def probe_entry(entry: dict, delay: float) -> dict:
    out = dict(entry)
    best = None
    for api in entry["urls"][:3]:
        probe = http_json(with_params(api, ac="list"), timeout=10)
        classes = len(probe.get("classes") or [])
        if classes or probe.get("ok"):
            best = (api, classes, probe)
            break
        time.sleep(delay)
    if not best:
        out.update({"ok": False, "classes": 0, "search": {}, "error": "unreachable"})
        return out
    api, classes, probe = best
    out["api"] = api
    out["classes"] = classes
    out["class_list"] = [
        {
            "type_id": str(c.get("type_id") or c.get("ty_id") or c.get("id") or ""),
            "type_name": html.unescape(str(c.get("type_name") or c.get("ty") or c.get("name") or "")),
            "type_pid": str(c.get("type_pid") or "0"),
        }
        for c in (probe.get("classes") or [])
    ]
    latency = [probe.get("ms", 9999)]
    search = {}
    for keyword in KEYWORDS:
        time.sleep(delay)
        res = http_json(with_params(api, ac="videolist", wd=keyword, pg=1, at="json"), timeout=12)
        latency.append(res.get("ms", 9999))
        names = [str(x.get("vod_name") or "") for x in (res.get("items") or [])]
        target = normalize_title(keyword)
        hit = sum(1 for n in names if target and target in normalize_title(n))
        search[keyword] = {
            "count": len(names),
            "hit": hit,
            "rate": round(hit / len(names), 3) if names else 0.0,
            "fp": fingerprint(names),
            "sample": names[:5],
        }
    out["search"] = search
    # 分类可浏览性：MacCMS 一级分类常只回 1 条占位，必须用展开后的子分类 ID 才能拿到真内容
    browse = {}
    categories = bc.category_map(out["class_list"])
    for key in ("movie", "tv", "short"):
        ids = categories.get(key) or []
        if not ids:
            browse[key] = 0
            continue
        time.sleep(delay)
        res = http_json(with_params(api, ac="detail", t=",".join(ids), pg=1, at="json"), timeout=12)
        browse[key] = len(res.get("items") or [])
    out["browse"] = browse
    out["browse_total"] = sum(browse.values())
    out["latency_ms"] = int(sum(latency) / len(latency))
    total = sum(v["count"] for v in search.values())
    rates = [v["rate"] for v in search.values() if v["count"]]
    out["ok"] = bool(classes or total)
    out["hit_rate"] = round(sum(rates) / len(rates), 3) if rates else 0.0
    a, b = search[KEYWORDS[0]], search[KEYWORDS[1]]
    out["kw_overlap"] = (
        round(
            len(set(a["sample"]) & set(b["sample"])) / max(1, len(set(a["sample"]) | set(b["sample"]))),
            3,
        )
        if a["count"] and b["count"]
        else None
    )
    out["searchable"] = bool(total and out["hit_rate"] >= 0.5 and (out["kw_overlap"] or 0) < 0.5)
    return out


def build_entries() -> list[dict]:
    allconf = load_json(TVBOX / "api/all.json")
    liteconf = load_json(TVBOX / "api/lite.json")
    sources = load_json(TVBOX / "sources.json")
    bconf = sources.get("build") or {}
    block_hosts = {str(h).lower() for h in bconf.get("block_hosts") or []}
    sites = list(allconf.get("sites") or []) + list(liteconf.get("sites") or [])

    groups: dict[str, list[str]] = {}
    meta: dict[str, dict] = {}
    for s in sites:
        api = str(s.get("api") or "")
        if s.get("type") != 1 or not api.startswith(("http://", "https://")):
            continue
        if build.api_kind(s) != "http":
            continue
        host = urllib.parse.urlsplit(api).hostname or ""
        if host in bc.BAD_HOSTS or any(h in host for h in block_hosts):
            continue
        if any(x in api for x in ("127.0.0.1", "localhost", "0.0.0.0", "[::1]")):
            continue
        lib = build.api_norm(s)
        # MacCMS 同库多写法：/api.php/provide/vod 与 /provide/vod 是同一后端
        lib = re.sub(r"^(.*?)(?:/api\.php)?/provide/vod", r"\1/provide/vod", lib)
        url = bc.endpoint_base(api)
        groups.setdefault(lib, [])
        if url not in groups[lib]:
            groups[lib].append(url)
        meta.setdefault(lib, {"lib": lib, "names": []})
        name = str(s.get("name") or "")
        if name and name not in meta[lib]["names"]:
            meta[lib]["names"].append(name)

    entries = []
    for lib, urls in groups.items():
        entries.append(
            {
                "lib": lib,
                "urls": urls,
                "aliases": len(urls),
                "names": meta[lib]["names"][:3],
                "name": meta[lib]["names"][0] if meta[lib]["names"] else lib,
            }
        )
    entries.sort(key=lambda e: e["lib"])
    return entries


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="忽略缓存全量重测")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--delay", type=float, default=0.6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-age", type=float, default=MAX_AGE_H, help="缓存有效期（小时）")
    args = ap.parse_args()

    path = PROJECT / "data/live.json"
    old = {}
    if path.is_file():
        cached = load_json(path)
        old = {k: v for k, v in (cached.get("libs") or {}).items() if isinstance(v, dict)}
    cutoff = time.time() - args.max_age * 3600

    entries = build_entries()
    if args.limit:
        entries = entries[: args.limit]
    todo = [
        e
        for e in entries
        if args.force
        or e["lib"] not in old
        or float(old[e["lib"]].get("ts") or 0) < cutoff
        # 老记录没有分类实测（browse）字段时补测一次
        or (int(old[e["lib"]].get("classes") or 0) > 0 and "browse" not in old[e["lib"]])
    ]
    print("libraries=%d cached=%d todo=%d" % (len(entries), len(entries) - len(todo), len(todo)), flush=True)

    results = {}
    if todo:
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
            for entry in ex.map(lambda e: probe_entry(e, args.delay), todo):
                results[entry["lib"]] = entry
                flag = "SEARCH" if entry.get("searchable") else ("BROWSE" if entry["classes"] else "DEAD ")
                print(
                    "[%s] %-34s cls=%-3d hit=%-5s browse=%-4s lat=%-5s %s"
                    % (flag, entry["lib"][:34], entry["classes"], entry.get("hit_rate"),
                       entry.get("browse_total"), entry.get("latency_ms"), entry.get("error") or "")
                )
    merged = {}
    for e in entries:
        rec = results.get(e["lib"]) or old.get(e["lib"])
        if not rec:
            continue
        rec = dict(rec)
        rec.setdefault("urls", e["urls"])
        rec["names"] = e["names"]
        rec.setdefault("name", e["name"])
        if e["lib"] in results:
            rec["ts"] = int(time.time())
        merged[e["lib"]] = rec

    data = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ts": int(time.time()),
        "scope": "all.json + lite.json / type=1 CMS",
        "keywords": list(KEYWORDS),
        "libs": merged,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    searchable = sum(1 for r in merged.values() if r.get("searchable"))
    browse = sum(1 for r in merged.values() if r.get("classes") and not r.get("searchable"))
    print("wrote %s libs=%d searchable=%d browse_only=%d dead=%d"
          % (path, len(merged), searchable, browse, len(merged) - searchable - browse))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
