# -*- coding: utf-8 -*-
"""规则站（csp_/py_/drpy）健康度检测。

问题背景：CMS 采集站能直接用 `ac=videolist&wd=` 验活，而规则站（jar/drpy）需要客户端
执行 JS 或 DexClassLoader，构建期无法跑。但**大部分失效能不做执行就查出来**：

  1. jar 下不下来、是不是合法 ZIP、有没有 classes.dex
  2. 配置里的 md5 与实际文件是否一致（不一致时客户端缓存键错位）
  3. 规则配置能不能拉取、能不能解析（JSONC/尾逗号/BOM 都要容忍）
  4. 规则里写死的目标站还在不在（主页 / 搜索链接 200 + 选择器命中）

第 4 项是关键证据：XYQHiker/XBPQ 的规则是「URL + 选择器」，搜索链接带回
`搜索列表数组规则` 里的选择器 → 规则大概率仍然有效；页面能打开但选择器一个都不命中
→ 站点改版，规则已废（这类在客户端表现为「有分类、点进去空白」）。

用法：
    python tools/probe_rules.py                 # 只测 lite.json（默认，约 40 秒）
    python tools/probe_rules.py --all --limit 300   # 全量抽样
    python tools/probe_rules.py --write         # 结果写 rule_health.json

输出等级：
    ok            主页/搜索可达且选择器命中
    weak          主页可达，但搜索无命中（可能只影响搜索，浏览仍可用）
    dead          jar 失效 / 主页非 200 / 规则拉不到
    unverifiable  ext 为空或目标站写在 jar 内，离线无法判定（需要真机）
"""
import argparse
import collections
import hashlib
import io
import json
import os
import random
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import jsonc  # noqa: E402

UA = "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36"
MIRROR = "https://gh-proxy.com/"
TIMEOUT = 12

# 这些状态码说明「入口不对劲」，不是「站点没内容」：重定向无法收敛、
# nginx 444 静默断开、850 非标、999（领英式反爬）等，一律不判死。
AMBIG_CODES = {301, 302, 303, 307, 308, 444, 850, 999}
# 网络侧异常同理：本机能超时，不代表站点死了。
AMBIG_EXC = {"TimeoutError", "timeout", "RemoteDisconnected",
             "ConnectionResetError", "ConnectionAbortedError",
             "IncompleteRead", "BadStatusLine", "ConnectionError"}

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=_CTX))


def http(url, timeout=TIMEOUT, headers=None, data=None, limit=None):
    # 规则里的链接常直接写中文（/vodsearch/庆余年----------.html），urllib 需要 ASCII；
    # 少数站还用了中文域名，netloc 要先转 punycode 再 quote。
    p = urllib.parse.urlsplit(url)
    if p.netloc and not p.netloc.isascii():
        try:
            url = urllib.parse.urlunsplit(
                (p.scheme, p.netloc.encode("idna").decode(), p.path, p.query, p.fragment))
        except UnicodeError:
            pass
    url = urllib.parse.quote(url, safe=":/?=&%#[]!$'()*,;@~+")
    hd = {"User-Agent": UA}
    hd.update(headers or {})
    req = urllib.request.Request(url, headers=hd, data=data)
    with _OPENER.open(req, timeout=timeout) as r:
        body = r.read() if limit is None else r.read(limit)
        return r.status, body


def kind_of(site):
    api = str(site.get("api") or "")
    if api.startswith(("csp_", "py_")):
        return "csp"
    if api.startswith("http") and api.split("?")[0].endswith((".js", ".min.js")):
        return "drpy"
    return "cms"


def parse_headers(spec):
    """XYQHiker 的 `请求头参数`：User-Agent$MOBILE_UA#Referer$https://x#accept$text/html

    返回 (headers, bad)：值不是 ASCII 时 OkHttp 会抛异常，规则等于废的，
    这里丢掉该头并计数，让上层能把「配置缺陷」和「站点失效」分开。
    """
    out, bad = {}, 0
    for part in str(spec or "").split("#"):
        if "$" not in part:
            continue
        k, v = part.split("$", 1)
        k, v = k.strip(), v.strip()
        if not k or not v or v == "MOBILE_UA":
            continue
        if not v.isascii():
            bad += 1
            continue
        out[k] = v
    return out, bad


def pick(cfg, *keys):
    for k in keys:
        v = cfg.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v.strip()
    return ""


def load_cfg(site):
    """返回 (cfg|None, shape)。shape 用于区分「配置空」和「配置坏」。"""
    ext = site.get("ext")
    if not ext:
        return None, "空"
    if isinstance(ext, dict):
        return ext, "对象"
    ext = str(ext).strip()
    if ext.startswith("{"):
        obj = jsonc._loads_tolerant(ext)
        return (obj, "内联JSON") if obj else (None, "内联坏")
    if not ext.startswith("http"):
        return None, "其他"
    # ext 本身就是目标站地址（csp_Czsapp 这类把站点写进 ext）
    if not ext.split("?")[0].endswith((".json", ".js")):
        return {"_site": ext}, "站点URL"
    text = ""
    for url in (ext, MIRROR + ext):
        try:
            _, body = http(url, 15)
            text = body.decode("utf-8", "replace")
            break
        except Exception:
            continue
    if not text:
        return None, "规则取不到"
    if ext.split("?")[0].endswith(".js"):
        m = re.search(r"host\s*:\s*['\"]([^'\"]+)['\"]", text)
        return ({"_site": m.group(1)}, "规则JS") if m else (None, "规则JS坏")
    try:
        obj = jsonc.parse_cfg(text)
    except ValueError:
        return None, "规则坏"
    # 少数规则文件外面套了一层数组
    if isinstance(obj, list):
        obj = next((x for x in obj if isinstance(x, dict)), None)
        if not obj:
            return None, "规则坏"
    return obj, "规则JSON"


_JAR_CACHE = {}
_JAR_LOCK = __import__("threading").Lock()


def fetch_jar(url):
    """同一个 jar 被几十个站复用，进程内缓存一份，避免重复下载 4MB 大包。

    大 jar（4MB，含 FishGuard .so）在弱网下常超时，失败重试一次再判死，
    否则单轮构建会把好站误杀。
    """
    with _JAR_LOCK:
        if url in _JAR_CACHE:
            return _JAR_CACHE[url]
    res = ("ERR", b"")
    for _ in range(2):
        try:
            st, body = http(url, 25)
            res = (st, body) if st == 200 else (st, b"")
            if res[1][:2] == b"PK":
                break
        except Exception as e:  # noqa: BLE001
            res = (type(e).__name__, b"")
    with _JAR_LOCK:
        _JAR_CACHE[url] = res
    return res


def rule_sig(site):
    """规则配置指纹：api + jar + ext 三者归一。

    build.py 里有一份完全相同的实现，用来在 key 改名后继承体检结论；
    两边算法必须一致，改动时同步。
    """
    api = str(site.get("api") or "").split(";")[0].strip()
    jar = str(site.get("jar") or "").split(";")[0].strip()
    ext = site.get("ext")
    if isinstance(ext, (dict, list)):
        ext = json.dumps(ext, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(
        ("%s\n%s\n%s" % (api, jar, str(ext or "").strip())).encode("utf-8")
    ).hexdigest()[:16]


def site_alive(url, headers=None, timeout=8):
    """主页链接 404 时判断「站点死了」还是「规则里的固定页失效」。

    很多规则的首页推荐链接写死成 `/xxx/22.html` 这类固定页号，站点活着但该页被删，
    客户端表现是首页空白、分类仍可浏览。这种情况判 dead 会把整站误杀。
    """
    try:
        p = urllib.parse.urlsplit(url)
        if not p.scheme or not p.netloc:
            return False
        root = "%s://%s/" % (p.scheme, p.netloc)
        st, body = http(root, timeout, headers, limit=200000)
        return st == 200 and len(body) > 200
    except Exception:  # noqa: BLE001
        return False


def probe(site):
    r = {
        "key": site.get("key"),
        "name": site.get("name"),
        "api": site.get("api"),
        "sig": rule_sig(site),
        "kind": kind_of(site),
        "jar": "-", "jar_b": 0, "ext": "-", "shape": "-",
        "home": "-", "home_ms": None, "home_url": "", "search": "-", "sel": "-",
        "level": "unverifiable", "why": "",
    }
    jar = str(site.get("jar") or "")
    if jar:
        ju = jar.split(";md5;")[0]
        md5 = jar.split(";md5;")[1].lower() if ";md5;" in jar else ""
        t0 = time.time()
        try:
            st, body = fetch_jar(ju)
            ok = st == 200 and body[:2] == b"PK"
            r["jar_b"] = len(body)
            if ok:
                names = zipfile.ZipFile(io.BytesIO(body)).namelist()
                has_dex = any(n.endswith("classes.dex") for n in names)
                has_cls = any(n.endswith(".class") for n in names)
                r["jar"] = "OK" if (has_dex or has_cls) else "无dex"
                if md5:
                    r["jar"] += "/md5" + ("OK" if hashlib.md5(body).hexdigest() == md5 else "错")
            else:
                r["jar"] = "非ZIP"
        except Exception as e:  # noqa: BLE001
            r["jar"] = type(e).__name__
        r["home_ms"] = round((time.time() - t0) * 1000)

    cfg, shape = load_cfg(site)
    r["shape"] = r["ext"] = shape
    if not cfg:
        if shape in ("规则取不到", "规则坏", "内联坏", "规则JS坏"):
            if r["jar"] not in ("-",) and not r["jar"].startswith("OK"):
                r["level"], r["why"] = "dead", "jar+配置都失效"
            else:
                r["level"], r["why"] = "weak", "配置取不到/解析失败，浏览与搜索全废"
        else:
            r["level"], r["why"] = "unverifiable", "ext 为空，目标站写在 jar 内"
        return r

    home = pick(cfg, "主页", "主页url", "首页推荐链接", "homeUrl", "url", "host") or cfg.get("_site", "")
    r["home_url"] = home
    hdr, bad_hdr = parse_headers(cfg.get("请求头参数"))
    if bad_hdr:
        r["why"] = "请求头含非 ASCII 值（配置错误）"
    if home:
        try:
            st, body = http(home, 10, hdr, limit=600000)
            r["home"] = st
        except urllib.error.HTTPError as e:
            r["home"] = e.code
        except Exception as e:  # noqa: BLE001
            r["home"] = type(e).__name__

    search = pick(cfg, "搜索链接", "搜索url", "搜索URL", "searchUrl")
    if search:
        url = re.sub(r"\*\*|\{[^}]*\}|\$\(wd\)|%s", "庆余年", search)
        data = None
        if cfg.get("POST请求数据"):
            data = str(cfg["POST请求数据"]).replace("{wd}", "庆余年").encode()
        try:
            shdr, _ = parse_headers(cfg.get("搜索请求头参数"))
            st, body = http(url, 12, shdr or hdr, data=data, limit=800000)
            text = body.decode("utf-8", "replace")
            r["search"] = st
            sel = str(cfg.get("搜索列表数组规则") or "").strip()
            token = ""
            if sel:
                token = sel.split("&&")[-1].strip()
                token = re.sub(r"^[.#]", "", token).split(":")[0].strip()
            if token and token not in ("Text", "Html"):
                r["sel"] = "命中" if token in text else "未命中"
            elif "庆余年" in text:
                r["sel"] = "关键词命中"
            else:
                r["sel"] = "无证据"
        except Exception as e:  # noqa: BLE001
            r["search"] = type(e).__name__

    if r["sel"] in ("命中", "关键词命中"):
        r["level"], r["why"] = "ok", ""
    elif r["sel"] == "未命中":
        r["level"], r["why"] = "weak", "搜索页可开但选择器未命中，站点疑似改版"
    elif r["home"] == 200:
        r["level"], r["why"] = "ok", ("" if r["search"] in ("-", 200) else "仅浏览可验")
    elif isinstance(r["home"], int) and r["home"] in (401, 403, 429, 451):
        r["level"], r["why"] = "unverifiable", "目标站反爬 %d，需真机复核" % r["home"]
    elif isinstance(r["home"], int) and r["home"] in (404, 410) and home and site_alive(home, hdr):
        # 站点还在、只是规则里写死的首页链接失效（典型：/bilfun/22.html 这种固定页号）。
        # 客户端表现为「首页空白但分类能用」，不该判死，但也不能给正常分。
        r["level"], r["why"] = "weak", "首页链接 HTTP %d，站点仍在（规则过期）" % r["home"]
    elif isinstance(r["home"], int) and r["home"] in AMBIG_CODES:
        # 301/444/850 这类是重定向异常、反爬静默断开、非标状态码——
        # 站点可能只是换了入口或拦了探针，不是「没有内容」，不能判死。
        r["level"], r["why"] = "unverifiable", "非标响应 %d，无法判定" % r["home"]
    elif isinstance(r["home"], int) and r["home"] >= 400:
        r["level"], r["why"] = "dead", "主页 HTTP %d" % r["home"]
    elif isinstance(r["home"], str) and (r["home"] in AMBIG_EXC
                                        or "timeout" in r["home"].lower()):
        # 本机网络侧的失败（超时/连接被重置）不构成站点失效证据。
        # 这类站点在海外 runner 上常常是通的，判死会批量误杀。
        r["level"], r["why"] = "unverifiable", "探针异常 %s（网络侧）" % r["home"]
    elif r["home"] in ("URLError", "gaierror"):
        r["level"], r["why"] = "dead", "域名解析失败（多半已换域名）"
    elif r["home"] == "-" and r["jar"].startswith("OK"):
        r["level"], r["why"] = "unverifiable", "无可用探针目标"
    elif r["home"] != "-":
        r["level"], r["why"] = "dead", "主页不可达 %s" % r["home"]
    else:
        r["level"], r["why"] = "dead", "jar 失效且无探针目标"
    return r


def doh_lookup(host, timeout=6):
    """用公共 DoH 复核域名：本地 DNS 被污染时，能把「站点真死」和「本机解析不了」分开。"""
    for base in ("https://dns.alidns.com/resolve", "https://doh.pub/dns-query"):
        try:
            url = "%s?name=%s&type=A" % (base, urllib.parse.quote(host))
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8",
                                                       "accept": "application/dns-json"})
            with _OPENER.open(req, timeout=timeout) as r:
                j = json.loads(r.read().decode("utf-8", "replace"))
            ips = [a.get("data") for a in (j.get("Answer") or []) if a.get("type") == 1]
            return j.get("Status"), ips
        except Exception:  # noqa: BLE001
            continue
    return None, []


def refine_dns(res, jobs=10):
    """把「本机解析失败但公网有 A 记录」的判决从 dead 降级为 unverifiable。

    国内网络对影视站常做 DNS 污染，直接判死会误杀（实测抽样 41 个里 15 个属于这类）。
    """
    targets = [r for r in res if r["level"] == "dead" and "解析" in r["why"] and r.get("home_url")]

    def one(r):
        host = urllib.parse.urlsplit(r["home_url"]).netloc.split(":")[0]
        if not host:
            return r
        status, ips = doh_lookup(host)
        if ips:
            r["level"], r["why"] = "unverifiable", "本机 DNS 不可达但公网有解析（疑似污染，需 CI 复核）"
        elif status == 3:
            r["why"] = "域名 NXDOMAIN（确认已停用）"
        return r

    with ThreadPoolExecutor(max_workers=jobs) as ex:
        return list(ex.map(one, targets))


def merge_history(prev, res):
    """给本轮结果接上历史：dead_streak / ok_streak / first_dead。

    为什么需要连轮计数：单轮网络抖动太常见（4MB 大 jar、弱网超时、上游临时 502），
    一轮判死就下架等于误杀。构建侧只认 dead_streak>=2，所以这里必须把
    「连续」这件事记下来，否则那个判据永远不成立。
    """
    by_key, by_sig = {}, {}
    for r in (prev or {}).get("sites") or []:
        if not isinstance(r, dict) or not r.get("key"):
            continue
        by_key[r["key"]] = r
        by_sig.setdefault(r.get("sig") or rule_sig(r), r)

    for r in res:
        old = by_key.get(r["key"]) or by_sig.get(r.get("sig"))
        if not old:
            r["dead_streak"] = 1 if r["level"] == "dead" else 0
            r["ok_streak"] = 1 if r["level"] == "ok" else 0
            if r["level"] == "dead":
                r["first_dead"] = r["tested_at_str"]
            continue
        r["prev_level"] = old.get("level")
        r["dead_streak"] = (int(old.get("dead_streak") or 0) + 1
                            if r["level"] == "dead" else 0)
        r["ok_streak"] = (int(old.get("ok_streak") or 0) + 1
                          if r["level"] == "ok" else 0)
        if r["dead_streak"] >= 2:
            r["first_dead"] = old.get("first_dead") or r["tested_at_str"]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="测 all.json 而不是 lite.json")
    ap.add_argument("--limit", type=int, default=0, help="抽样上限（0=全测）")
    ap.add_argument("--write", action="store_true", help="写 rule_health.json")
    ap.add_argument("--jobs", type=int, default=16)
    ap.add_argument("--no-doh", action="store_true", help="跳过 DoH 复核（不降级疑似 DNS 污染）")
    ap.add_argument("--max-age", type=float, default=0,
                    help="已有 rule_health.json 未超过该小时数就跳过（CI 用来每天只跑一次）")
    a = ap.parse_args()

    out = os.path.join(ROOT, "rule_health.json")
    if a.max_age and os.path.exists(out):
        try:
            age_h = (time.time() - float(json.load(open(out, encoding="utf-8")).get("tested_at") or 0)) / 3600
        except Exception:  # noqa: BLE001
            age_h = 1e9
        if age_h < a.max_age:
            print("跳过：rule_health.json 生成于 %.1f 小时前（阈值 %.0f 小时）" % (age_h, a.max_age))
            return

    name = "all.json" if a.all else "lite.json"
    data = json.load(open(os.path.join(ROOT, "api", name), encoding="utf-8"))
    sites = [s for s in data["sites"] if kind_of(s) != "cms"]
    if a.limit and len(sites) > a.limit:
        random.seed(7)
        sites = random.sample(sites, a.limit)
    print("检测 %s：%d 个规则站（csp %d / drpy %d）" % (
        name, len(sites), sum(1 for s in sites if kind_of(s) == "csp"),
        sum(1 for s in sites if kind_of(s) == "drpy")), flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        res = list(ex.map(probe, sites))
    if not a.no_doh:
        refine_dns(res)

    prev = {}
    if os.path.exists(out):
        try:
            prev = json.load(open(out, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            prev = {}
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    for r in res:
        r["tested_at_str"] = stamp
    merge_history(prev, res)

    cnt = collections.Counter(r["level"] for r in res)
    print("\n等级分布：%s  耗时 %.0fs" % (dict(cnt), time.time() - t0))
    print("jar：%s" % dict(collections.Counter(
        ("OK" if r["jar"].startswith("OK") else r["jar"]) for r in res)))
    print("ext：%s" % dict(collections.Counter(r["shape"] for r in res)))
    print("\n%-14s %-16s %-10s %-6s %-6s %-6s %s" % ("站名", "api", "ext", "主页", "搜索", "选择器", "判定"))
    for r in sorted(res, key=lambda x: ("ok weak dead unverifiable".split().index(x["level"]), str(x["name"]))):
        extra = ""
        if r["level"] == "dead":
            extra = "  [连续 %d 轮]" % max(1, int(r.get("dead_streak") or 1))
        print("%-14s %-16s %-10s %-6s %-6s %-6s %s %s%s" % (
            str(r["name"])[:14], str(r["api"])[:16], str(r["shape"])[:10],
            str(r["home"])[:6], str(r["search"])[:6], str(r["sel"])[:6], r["level"],
            ("/ " + r["why"]) if r["why"] else "", extra))

    if a.write:
        # 抽样跑（--limit）时不能把整份文件覆盖成样本：未抽到的站沿用上一轮记录，
        # 否则构建侧会以为「其余站点没有体检结论」，覆盖判定整体失真。
        merged = list(res)
        tested = {r["key"] for r in res}
        for r in ((prev or {}).get("sites") or []):
            if isinstance(r, dict) and r.get("key") and r["key"] not in tested:
                merged.append(r)
        hard = [r for r in merged if r["level"] == "dead" and int(r.get("dead_streak") or 1) >= 2]
        json.dump({"generated_at": stamp, "tested_at": int(time.time()), "scope": name,
                   "summary": dict(collections.Counter(r["level"] for r in merged)),
                   "hard_dead": len(hard),
                   "sites": merged},
                  open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n已写 %s（共 %d 条，其中连续两轮判死 %d 条）" % (out, len(merged), len(hard)))


if __name__ == "__main__":
    main()
