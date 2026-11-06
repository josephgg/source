#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产物验收：校验 docs/api/all.json 是否符合 FongMi 的加载约束，并抽样探活。

只做静态校验 + 抽样网络探测，不执行爬虫。
退出码 0 = 通过（抽样探活失败只告警），1 = 结构性错误。
"""
import json
import os
import random
import re
import ssl
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "api", "all.json")

if os.environ.get("TVBOX_USE_PROXY") != "1":
    for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(_k, None)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

errors, warns = [], []


def err(msg):
    errors.append(msg)


def warn(msg):
    warns.append(msg)


def encode_url(u):
    """中文与空格必须转百分号，否则 urllib 直接报 InvalidURL"""
    if not isinstance(u, str) or "://" not in u:
        return u
    p = urllib.parse.urlsplit(u)
    netloc = p.netloc
    try:
        netloc.encode("ascii")
    except UnicodeEncodeError:
        netloc = (p.hostname or "").encode("idna").decode("ascii") + ((":%d" % p.port) if p.port else "")
    path = urllib.parse.quote(urllib.parse.unquote(p.path), safe="/%:@&=+$,;~()!*'")
    query = urllib.parse.quote(urllib.parse.unquote(p.query), safe="=&%:@+$,;~/?()!*'")
    return urllib.parse.urlunsplit((p.scheme, netloc, path, query, ""))


def probe(url, timeout=15):
    url = encode_url(url.split(";md5;")[0])
    req = urllib.request.Request(url, headers={
        "User-Agent": "okhttp/3.15",
        "Range": "bytes=0-2047",
        "Accept-Encoding": "identity",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            body = r.read(64)
            return True, r.status, len(body)
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__, str(e)[:80]


def main():
    if not os.path.exists(TARGET):
        print("缺少产物：%s" % TARGET)
        return 1
    with open(TARGET, encoding="utf-8") as f:
        cfg = json.load(f)

    sites = cfg.get("sites") or []
    print("加载 %s：站点 %d / 解析 %d / 直播 %d" % (
        os.path.basename(TARGET), len(sites),
        len(cfg.get("parses") or []), len(cfg.get("lives") or [])))

    # 1. 结构
    if not sites:
        err("sites 为空")
    for field in ("parses",):
        if field not in cfg:
            warn("缺少字段 %s（FongMi 会走空列表兜底）" % field)

    # 2. key 唯一
    keys = [s.get("key") for s in sites]
    dup = len(keys) - len(set(keys))
    if dup:
        err("key 重复 %d 个（会导致站点互相覆盖）" % dup)
    empty = sum(1 for k in keys if not k)
    if empty:
        err("%d 个站点 key 为空（Site.equals 依据 key，空 key 会被 distinct 合并）" % empty)

    # 3. 残留相对路径
    rel = 0
    for s in sites:
        for fld in ("api", "ext", "jar"):
            v = s.get(fld)
            if isinstance(v, str) and (v.startswith(("./", "../")) or v.startswith("/")):
                rel += 1
    if rel:
        err("%d 处 api/ext/jar 仍是相对路径（客户端会按本仓地址解析成 404）" % rel)

    # 4. csp 站点必须有 jar
    nojar = [s for s in sites if (s.get("api") or "").startswith("csp_") and not (s.get("jar") or "").strip()]
    if nojar:
        err("%d 个 csp_ 站点缺少 jar：%s" % (len(nojar), [s.get("name") for s in nojar[:3]]))

    jars = sorted({(s.get("jar") or "").split(";md5;")[0] for s in sites if s.get("jar")})
    apis = sorted({s.get("api") for s in sites if (s.get("api") or "").startswith("http")})
    print("依赖：jar %d 个 / 远程 js 接口 %d 个" % (len(jars), len(apis)))

    # 5. 抽样探活
    random.seed(42)
    sample_jars = random.sample(jars, min(6, len(jars)))
    sample_apis = random.sample(apis, min(6, len(apis)))
    targets = [("jar", u) for u in sample_jars] + [("api", u) for u in sample_apis]
    bad = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for (kind, url), res in zip(targets, pool.map(lambda t: probe(t[1]), targets)):
            ok, info, extra = res
            print("  [%s] %s %s" % (kind, "OK " if ok else "FAIL", url[:96]))
            if not ok:
                bad.append((kind, url, info, extra))
    if bad:
        for kind, url, info, extra in bad:
            warn("抽样失败 %s %s -> %s %s" % (kind, url[:80], info, extra))
        if len(bad) >= max(2, len(targets) // 2):
            err("抽样探活失败率过高（%d/%d），产物可能不可用" % (len(bad), len(targets)))

    # 6. parses 抽样
    parses = cfg.get("parses") or []
    purls = [p.get("url") for p in parses if isinstance(p.get("url"), str) and p["url"].startswith("http")]
    if purls:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(probe, purls[:4]))
        dead = sum(1 for r in results if not r[0])
        if dead:
            warn("解析接口抽样 %d/%d 不可达" % (dead, len(results)))

    # 7. 名称重复度（同源内重名只影响观感）
    names = [s.get("name") for s in sites]
    ndup = len(names) - len(set(names))
    if ndup > len(names) * 0.2:
        warn("站点重名 %d 个，建议开启 name_prefix" % ndup)

    print("\n--- 验收结果 ---")
    for w in warns:
        print("[WARN]", w)
    for e in errors:
        print("[ERROR]", e)
    if not errors:
        print("通过：结构性约束全部满足")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
