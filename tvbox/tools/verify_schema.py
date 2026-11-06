#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产物字段类型自检：按客户端 Site/Parse 模型的声明校验 api/*.json。

背景：FongMi 用 Gson 严格反序列化，字段类型不对的后果不对称 ——
  · Site.objectFrom 有 try-catch，坏站点静默变成空 Site（首页源若中招即点播全白）
  · Parse.objectFrom 没有 try-catch，一个坏字段就让 initParse 抛异常，
    parseConfig 整体失败，站点列表也为空
所以产物必须保证类型字面合法。build.py 的 normalize_site / normalize_parse
负责写入侧，本脚本负责校验侧。

用法：python tvbox/tools/verify_schema.py
退出码 0 = 全部合规，1 = 存在异常
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = os.path.join(ROOT, "api")

STR = ("key", "name", "lang", "api", "ext", "jar", "click", "playUrl")
INT = ("type", "hide", "indexs", "timeout", "searchable",
       "changeable", "quickSearch", "danmaku")
OBJ = ("header", "style")


def check_site(s):
    bad = []
    for k in STR:
        v = s.get(k)
        if v is not None and not isinstance(v, str):
            bad.append("%s:%s" % (k, type(v).__name__))
    for k in INT:
        v = s.get(k)
        if v is not None and not isinstance(v, int):
            bad.append("%s:%s" % (k, type(v).__name__))
    for k in OBJ:
        v = s.get(k)
        if v is not None and not isinstance(v, dict):
            bad.append("%s:%s" % (k, type(v).__name__))
    v = s.get("categories")
    if v is not None and not isinstance(v, list):
        bad.append("categories:%s" % type(v).__name__)
    if s.get("type") not in (0, 1, 3):
        bad.append("type非法:%r" % s.get("type"))
    if not s.get("api"):
        bad.append("api为空")
    return bad


def check_parse(p):
    bad = []
    for k in ("name", "url", "click"):
        v = p.get(k)
        if v is not None and not isinstance(v, str):
            bad.append("%s:%s" % (k, type(v).__name__))
    v = p.get("type")
    if not isinstance(v, int):
        bad.append("type:%s" % type(v).__name__)
    for k in ("ext", "header"):
        v = p.get(k)
        if v is not None and not isinstance(v, dict):
            bad.append("%s:%s" % (k, type(v).__name__))
    return bad


def check_file(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    sites = d.get("sites") or []
    parses = d.get("parses") or []
    site_bad = [(i + 1, s.get("name"), check_site(s))
                for i, s in enumerate(sites)]
    site_bad = [x for x in site_bad if x[2]]
    parse_bad = [(i + 1, p.get("name"), check_parse(p))
                 for i, p in enumerate(parses)]
    parse_bad = [x for x in parse_bad if x[2]]
    return d, sites, parses, site_bad, parse_bad


def main():
    if not os.path.isdir(API):
        print("找不到产物目录：%s" % API)
        return 1
    files = sorted(f for f in os.listdir(API) if f.endswith(".json"))
    if not files:
        print("api/ 下没有 json 产物")
        return 1
    total_bad = 0
    for name in files:
        path = os.path.join(API, name)
        try:
            d, sites, parses, site_bad, parse_bad = check_file(path)
        except Exception as e:  # noqa: BLE001
            print("[FAIL] %-22s 无法解析：%s" % (name, e))
            total_bad += 1
            continue
        flag = "OK  " if not site_bad and not parse_bad else "FAIL"
        print("[%s] %-22s 站点=%-5d 解析=%-3d 首站=%s"
              % (flag, name, len(sites), len(parses),
                 (sites[0].get("name") if sites else "-")))
        for i, nm, bad in site_bad[:8]:
            print("         #%-4d %-26s %s" % (i, str(nm)[:26], ", ".join(bad)))
        if len(site_bad) > 8:
            print("         ... 另有 %d 个站点不合规" % (len(site_bad) - 8))
        for i, nm, bad in parse_bad[:8]:
            print("         parse#%-3d %-22s %s" % (i, str(nm)[:22], ", ".join(bad)))
        total_bad += len(site_bad) + len(parse_bad)
    print()
    if total_bad:
        print("总计 %d 处不合规" % total_bad)
        return 1
    print("全部合规：%d 个产物文件，字段类型与客户端模型一致" % len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
