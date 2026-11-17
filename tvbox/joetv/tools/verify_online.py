#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""线上成品验收：健康、逐源、搜索排序、详情线路、六类覆盖。"""
import json
import time
import urllib.parse
import urllib.request

BASE = "https://joetv-joe.pages.dev"
API = BASE + "/api.php/provide/vod/"


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 JoeTV-verify"})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    started = time.time()
    with op.open(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body.decode("utf-8")), int((time.time() - started) * 1000)


def bust(url):
    return url + ("&" if "?" in url else "?") + "_=%.3f" % time.time()


health, ms = get(bust(BASE + "/"))
print("health %dms %s" % (ms, json.dumps(health, ensure_ascii=False)))

diag, ms = get(bust(BASE + "/diag?wd=" + urllib.parse.quote("繁花")))
print("\ndiag %dms ok=%d/%d" % (ms, diag["ok"], len(diag["sources"])))
for s in diag["sources"]:
    print("  %-4s %-12s %-7s items=%-3s %5sms %s"
          % (s["id"], s["label"], "browse" if s["no_search"] else "search",
             s["items"], s["elapsed_ms"], s["error"][:24]))

print("\n搜索：")
for kw in ["繁花", "庆余年", "狂飙", "三体", "甄嬛传", "漫长的季节", "熊出没", "流浪地球"]:
    data, ms = get(bust(API + "?ac=videolist&wd=" + urllib.parse.quote(kw)))
    names = [x["vod_name"] for x in data.get("list") or []]
    first = names[0] if names else ""
    hit = first.startswith(kw)
    labels = {}
    lines = verified = 0
    if names:
        d, _ = get(bust(API + "?ac=detail&ids=" + urllib.parse.quote(data["list"][0]["vod_id"])))
        if d.get("code") == 1:
            item = d["list"][0]
            lines = len(item["vod_play_url"].split("$$$"))
            verified = d.get("msg", "").count("verified")
    print("  %-6s n=%-2d %5dms 首条=%-22s 命中=%-5s 线路=%-2d %s"
          % (kw, len(names), ms, first, hit, lines, "详情" + ("ok" if lines else "fail")))

print("\n分类：")
classes, _ = get(bust(API + "?ac=list"))
print("  " + ",".join(c["type_name"] for c in classes["class"]))
for c in classes["class"]:
    data, ms = get(bust(API + "?ac=detail&t=%s&pg=1" % c["type_id"]))
    names = [x["vod_name"] for x in data.get("list") or []]
    print("  %-4s n=%-2d %5dms 示例=%s" % (c["type_name"], len(names), ms, " / ".join(names[:3])))
