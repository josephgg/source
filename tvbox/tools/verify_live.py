# -*- coding: utf-8 -*-
"""线上地址核对：raw 为准，cdn 仅作参考（@main 有缓存）"""
import json
import time
import urllib.request

RAW = "https://raw.githubusercontent.com/josephgg/source/main/"
CDN = "https://cdn.jsdelivr.net/gh/josephgg/source@main/"


def get(url, timeout=30):
    t = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), int((time.time() - t) * 1000)


def j(name, url, show=None):
    try:
        body, ms = get(url)
        d = json.loads(body.decode("utf-8"))
        n = len(d.get("sites") or [])
        extra = ""
        if show:
            extra = show(d)
        print("OK  %-11s %5dms %7.1fKB  sites=%-5d%s" % (name, ms, len(body) / 1024, n, extra))
        return d
    except Exception as e:
        print("ERR %-11s %s" % (name, e))
        return None


def txt(name, url):
    try:
        body, ms = get(url)
        s = body.decode("utf-8", "replace")
        ext = sum(1 for x in s.splitlines() if x.startswith("#EXTINF"))
        print("OK  %-11s %5dms %7.1fKB  线路=%d" % (name, ms, len(body) / 1024, ext))
    except Exception as e:
        print("ERR %-11s %s" % (name, e))


print("== raw（实时） ==")
j("lite", RAW + "tvbox/api/lite.json")
j("all", RAW + "tvbox/api/all.json")
txt("m3u", RAW + "iptv_filtered.m3u")
st = j("status", RAW + "tvbox/status.json",
       lambda d: "  构建于 %s" % d.get("generated_at"))

print("\n== cdn（可能有缓存） ==")
j("lite", CDN + "tvbox/api/lite.json")
j("all", CDN + "tvbox/api/all.json")
txt("m3u", CDN + "iptv_filtered.m3u")

if st:
    print("\n== 状态 ==")
    for k in ("total_sites", "searchable_sites", "lite_sites",
              "dead_spider_files", "demoted_sites", "cms_alive_now"):
        print("  %-18s %s" % (k, st.get(k)))
    srcs = st.get("sources", [])
    print("  %-18s %d 成功 / %d 失败（含多仓子链接）" % (
        "源", sum(1 for s in srcs if s.get("ok")), sum(1 for s in srcs if not s.get("ok"))))
