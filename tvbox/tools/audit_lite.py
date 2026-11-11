#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精选仓内容验收：数量、类目、重复库、搜索质量与首页覆盖。

字段类型由 verify_schema.py 负责；本脚本专查「字段合法但成品不好用」。
默认只读，不修改任何产物；发现问题退出码为 1，CI 不应提交该轮产物。
"""
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import build  # noqa: E402


def load(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return json.load(f)


def main():
    allconf = load("api/all.json")
    liteconf = load("api/lite.json")
    sources = load("sources.json")
    sq = build.load_search_quality()
    alive = build.current_alive(allconf["sites"], build.load_alive())
    sites = liteconf.get("sites") or []
    errors, warns = [], []
    bconf = sources.get("build") or {}
    expected = int(bconf.get("lite_size") or 72)

    if len(sites) != expected:
        errors.append("精选数量 %d，期望 %d" % (len(sites), expected))
    keys = [s.get("key") for s in sites]
    if len(keys) != len(set(keys)):
        errors.append("精选 key 重复")
    allkeys = {s.get("key") for s in allconf.get("sites") or []}
    missing = set(keys) - allkeys
    if missing:
        errors.append("精选有 %d 个 key 不在全量仓：%s" % (len(missing), sorted(missing)[:5]))
    names = [s.get("name") for s in sites]
    dup_names = [name for name, count in Counter(names).items() if count > 1]
    if dup_names:
        errors.append("精选显示名重复：%s" % dup_names)

    cats = Counter((s.get("name") or "").split("·")[0] for s in sites)
    minimums = {"影视": 24, "动漫": 10, "4K": 8}
    for cat, minimum in minimums.items():
        if cats.get(cat, 0) < minimum:
            errors.append("%s 类仅 %d 个，低于高质量覆盖下限 %d" % (cat, cats.get(cat, 0), minimum))

    libs = defaultdict(list)
    sigs = defaultdict(list)
    sq_by_norm = build.index_search_quality(sq)
    quality = Counter()
    for s in sites:
        libs[build.lib_of(s)].append(s["name"])
        if not build.is_searchable(s):
            errors.append("精选站被客户端排除在搜索之外：%s" % s.get("name"))
        rec = build.search_record(s, sq, sq_by_norm)
        if rec:
            quality[rec.get("action") or "unknown"] += 1
            if rec.get("action") in ("disable", "adult"):
                errors.append("禁用/成人站进入精选：%s" % s.get("name"))
            titles = rec.get("titles1") or []
            if len(titles) >= 5:
                sig = hashlib.md5("\n".join(sorted(titles)).encode("utf-8")).hexdigest()
                sigs[sig].append(s["name"])
        else:
            quality["untested"] += 1
        api = str(s.get("api") or "")
        if any(h in api for h in ("127.0.0.1", "localhost", "0.0.0.0", "[::1]")):
            errors.append("本机代理站进入精选：%s" % s.get("name"))
        if any(h in api for h in (bconf.get("block_hosts") or [])):
            errors.append("黑名单站进入精选：%s" % s.get("name"))

    for lib, names_in_lib in libs.items():
        if len(names_in_lib) > 1:
            errors.append("同资源库多入口：%s -> %s" % (lib, names_in_lib))
    for sig, names_in_sig in sigs.items():
        if len(names_in_sig) > 1:
            errors.append("搜索结果完全重复：%s" % names_in_sig)

    if sites:
        home = sites[0]
        rec = alive.get(home["key"]) or {}
        cls = " ".join(str(x) for x in (rec.get("cls") or []))
        core = {
            "电影": any(w in cls for w in ("电影", "电影片")),
            "电视剧": any(w in cls for w in ("电视剧", "连续剧", "剧集")),
            "动漫": any(w in cls for w in ("动漫", "动画")),
        }
        if not all(core.values()):
            errors.append("首页未经验证同时覆盖电影/电视剧/动漫：%s，分类证据=%s" %
                          (home.get("name"), core))
        sr = build.search_record(home, sq, sq_by_norm) or {}
        if not (sr.get("action") == "keep" and sr.get("verdict") in ("good", "ok")
                and isinstance(sr.get("hit_rate"), (int, float)) and sr["hit_rate"] >= 0.70):
            errors.append("首页搜索未实测合格：%s，质检=%s/%s" %
                          (home.get("name"), sr.get("action"), sr.get("hit_rate")))
        print("首页：%s｜核心分类=%s｜搜索命中=%s｜CMS=%s" %
              (home.get("name"), core, sr.get("hit_rate"), rec.get("code")))

    print("精选：%d 站｜类目=%s" % (len(sites), dict(cats)))
    print("搜索证据：%s（untested 主要是必须 Android 执行的 jar 站）" % dict(quality))
    for msg in warns:
        print("[WARN]", msg)
    for msg in errors:
        print("[ERROR]", msg)
    if errors:
        print("内容验收失败：%d 项" % len(errors))
        return 1
    print("内容验收通过：核心类目足量、无已知重复库，首页覆盖与搜索均合格")
    return 0


if __name__ == "__main__":
    sys.exit(main())
