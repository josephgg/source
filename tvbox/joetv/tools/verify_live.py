#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对已部署的 JoeTV 做成品回放验收：搜索 -> 详情 -> HLS 首/中/尾分片。"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse

import requests

DEFAULT_BASE = "https://joetv-joe.pages.dev/api.php/provide/vod/"
UA = "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 JoeTV/1.0"


def fetch(session: requests.Session, url: str, range_bytes: bool = False):
    headers = {"User-Agent": UA}
    if range_bytes:
        headers["Range"] = "bytes=0-2047"
    return session.get(url, headers=headers, timeout=25)


def resolve_playlist(session, url):
    """返回 (kind, 媒体分片列表或字节数, 最终URL)。只递归一层 master。"""
    r = fetch(session, url)
    if r.status_code not in (200, 206) or not r.content:
        return "http_%s" % r.status_code, [], url
    # 分片列表必须用完整响应解析；只读前 4KB 会把“列表中段”误当成末片。
    text = r.content.decode("utf-8", errors="replace")
    low = text.lstrip().lower()
    if low.startswith(("<!doctype", "<html", "<head")):
        return "html", [], url
    if "#EXTM3U" not in text:
        media = r.content[:8]
        if media.startswith(b"\x1a\x45\xdf\xa3") or media[:4] in (b"fLaC", b"OggS"):
            return "direct", [len(r.content)], url
        if r.headers.get("content-type", "").startswith(("video/", "audio/")):
            return "direct", [len(r.content)], url
        return "not_media", [], url

    lines = [x.strip() for x in text.splitlines() if x.strip()]
    variants = []
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
            variants.append(lines[i + 1])
    if variants:
        child = urllib.parse.urljoin(url, variants[0])
        rr = fetch(session, child)
        if rr.status_code not in (200, 206):
            return "variant_http_%s" % rr.status_code, [], child
        lines = [x.strip() for x in rr.text.splitlines() if x.strip()]
        url = child

    segments = [
        urllib.parse.urljoin(url, x)
        for x in lines
        if x and not x.startswith("#")
    ]
    if not segments:
        return "empty_playlist", [], url
    picks = [segments[0], segments[len(segments) // 2], segments[-1]]
    ok = 0
    for seg in picks:
        passed = False
        for attempt in range(2):
            sr = fetch(session, seg, range_bytes=True)
            if sr.status_code in (200, 206) and len(sr.content) >= 32:
                passed = True
                break
            if attempt == 0:
                import time

                time.sleep(1)
        if passed:
            ok += 1
    return "ok" if ok == len(picks) else "segments_%d/%d" % (ok, len(picks)), picks, url


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--kw", default="庆余年,凡人修仙传,流浪地球,狂飙")
    ap.add_argument("--titles", type=int, default=2)
    ap.add_argument("--lines", type=int, default=2)
    args = ap.parse_args()

    session = requests.Session()
    session.trust_env = False
    keywords = [x.strip() for x in args.kw.split(",") if x.strip()]
    report = {"base": args.base, "checks": [], "summary": {}}
    total = ok = 0
    for keyword in keywords:
        try:
            sr = fetch(session, args.base + "?ac=videolist&wd=" + urllib.parse.quote(keyword))
            search = sr.json()
        except Exception as e:  # noqa: BLE001
            print("[SEARCH FAIL] %s %s: %s" % (keyword, type(e).__name__, e))
            continue
        print("\n[%s] code=%s list=%s" % (keyword, search.get("code"), len(search.get("list") or [])))
        for item in (search.get("list") or [])[: args.titles]:
            vid = item.get("vod_id")
            name = item.get("vod_name")
            dr = fetch(session, args.base + "?ac=detail&ids=" + urllib.parse.quote(str(vid)))
            try:
                detail = dr.json()
            except ValueError:
                print("  [DETAIL HTML] %s" % name)
                continue
            rows = detail.get("list") or []
            if not rows:
                print("  [DETAIL EMPTY] %s %s" % (name, detail.get("msg")))
                continue
            row = rows[0]
            seps = "$" * 3
            froms = str(row.get("vod_play_from") or "").split(seps)
            groups = str(row.get("vod_play_url") or "").split(seps)
            print("  %s | %d lines | %s" % (name, len(groups), " / ".join(froms[: args.lines])))
            for label, group in list(zip(froms, groups))[: args.lines]:
                first = next((x for x in group.split("#") if x), "")
                if "$" not in first:
                    print("    %-8s invalid episode" % label)
                    total += 1
                    continue
                url = first.split("$", 1)[1]
                if not re.match(r"^https?://[\x21-\x7e]+$", url):
                    print("    %-8s invalid url" % label)
                    total += 1
                    continue
                kind, picks, final = resolve_playlist(session, url)
                total += 1
                if kind == "ok":
                    ok += 1
                print("    %-8s %-14s %s" % (label, kind, final[:110]))
                report["checks"].append(
                    {"keyword": keyword, "title": name, "line": label, "kind": kind, "url": final}
                )
    report["summary"] = {"lines": total, "ok": ok, "failed": total - ok}
    print("\nSUMMARY %s" % json.dumps(report["summary"], ensure_ascii=False))
    out = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "live_verify.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
