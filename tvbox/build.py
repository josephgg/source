#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""影视仓聚合构建器

读取 sources.json -> 抓取各源配置 -> 绝对化相对路径 -> 合并为一个总仓
产出：
  docs/api/all.json          总聚合仓（一个地址装下全部站点）
  docs/api/src-<id>.json     各源单仓快照（排查用）
  docs/index.json            FongMi 多仓索引（选择式）
  docs/status.json           机器可读构建状态
  docs/report.md             人类可读构建报告

设计约束（来自 FongMi/TV 源码，勿随意改动）：
1. 客户端 Decoder.fix() 会按「配置 URL」解析 ./ ../ 相对路径。合并后 base
   变成本仓地址，因此构建期必须完成绝对化，否则站点全部 404。
2. Site 唯一键就是配置里的 key。跨源 key 会冲突（实测 gao 与 top98 撞 3 个），
   必须重排且保证稳定（同一站点每次构建 key 不变，否则用户收藏/历史丢失）。
3. BaseLoader/JarLoader 按 jar 的 md5 缓存多个 DexClassLoader，因此不同爬虫
   家族的站点可以共存于一个配置；每个站点必须显式写 jar（源仓顶层 spider
   不会跨源继承）。
"""
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from jsonc import parse_cfg  # noqa: E402

UA = "okhttp/3.15"
TIMEOUT = 40
CHILD_TIMEOUT = 30
RETRY = 3

# 会话注入的代理会让部分直连可用的源走代理后 502，默认清空；需要时设 TVBOX_USE_PROXY=1
if os.environ.get("TVBOX_USE_PROXY") != "1":
    for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(_k, None)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 无 scheme 的相对路径只对这些字段补全，避免误伤 csp_XXX / drpy 等标识符
PATH_KEYS = {"spider", "jar", "wallpaper", "click", "playUrl", "epg", "logo"}

# 常见 GitHub 镜像前缀。部分仓（如无邪）会把别家源整体搬运并加前缀，
# 归一时必须先剥离，否则同一站点会被当成新站点重复收录。
MIRROR_RE = re.compile(
    r"^https?://(?:gh-proxy\.com|ghfast\.top|ghproxy\.net|gh\.llkk\.cc|"
    r"ghps\.cc|mirror\.ghproxy\.com|ghproxy\.cc|gh-proxy\.net)/",
    re.I,
)
BROKEN_SCHEME_RE = re.compile(r"^(https?):/+", re.I)


# ---------------------------------------------------------------- 网络

def ascii_url(u):
    """中文域名转 punycode。urllib 只接受 ASCII，直接请求 http://饭太硬.net 会抛
    'latin-1' codec can't encode，源站本身是好的，不转就等于整源丢失。"""
    if not isinstance(u, str) or "://" not in u:
        return u
    try:
        parts = urllib.parse.urlsplit(u)
        host = parts.hostname or ""
        if not host or all(ord(c) < 128 for c in host):
            return u
        host = host.encode("idna").decode("ascii")
        netloc = host + (":%d" % parts.port if parts.port else "")
        return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:  # noqa: BLE001
        return u


def _open(url, timeout=None):
    req = urllib.request.Request(ascii_url(url), headers={
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Encoding": "identity",
    })
    return urllib.request.urlopen(req, timeout=timeout or TIMEOUT, context=CTX)


def _permanent(e):
    """判断错误是否「重试也没用」：域名已死、页面被删、需要鉴权。

    这类错误对着同一台机器重试 3 次只会白等（DNS 失败一次就是十几秒），
    多仓里几十个死链能把单次构建拖长一两分钟。超时 / 连接重置 / 5xx
    仍按原策略重试——那是真抖动。"""
    if isinstance(e, urllib.error.HTTPError):
        return e.code in (400, 401, 404, 410, 451)
    reason = getattr(e, "reason", None)
    if isinstance(reason, socket.gaierror):
        return True
    if isinstance(e, (socket.gaierror, UnicodeError, ValueError)):
        return True
    return False


def fetch(url, timeout=None):
    last = None
    for attempt in range(RETRY + 1):
        try:
            with _open(url, timeout) as r:
                raw = r.read()
                charset = r.headers.get_content_charset()
            if charset:
                try:
                    return raw.decode(charset)
                except Exception:
                    pass
            for enc in ("utf-8", "gbk", "gb18030"):
                try:
                    return raw.decode(enc)
                except Exception:
                    continue
            return raw.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            if _permanent(e):
                break
            time.sleep(1.5 * (attempt + 1))
    raise last


def norm_url(u):
    """中文域名 -> punycode，路径/查询保留原义"""
    p = urllib.parse.urlsplit(u.strip())
    host = p.hostname or ""
    try:
        host = host.encode("idna").decode("ascii")
    except Exception:
        pass
    port = ":%d" % p.port if p.port else ""
    path = urllib.parse.quote(urllib.parse.unquote(p.path), safe="/%:@&=+$,;~")
    query = urllib.parse.quote(urllib.parse.unquote(p.query), safe="=&%:@+$,;~/?")
    return urllib.parse.urlunsplit((p.scheme or "http", host + port, path, query, ""))


# ---------------------------------------------------------------- 路径绝对化

def unwrap_mirror(value):
    """剥离镜像前缀并修复 https:/ 这类坏 scheme，用于跨源同一性判定"""
    if not isinstance(value, str) or not value:
        return value or ""
    s = BROKEN_SCHEME_RE.sub(lambda m: m.group(1).lower() + "://", value.strip())
    for _ in range(3):
        nxt = MIRROR_RE.sub("", s)
        if nxt == s:
            break
        s = BROKEN_SCHEME_RE.sub(lambda m: m.group(1).lower() + "://", nxt)
        # 镜像站点常被改写为 gh-proxy.com/https://x，剥离后可能多出前导斜杠
        s = s.lstrip("/")
    return s


def encode_url(u):
    """URL 规范化：中文/空格转百分号，修复 https:/ 单斜杠"""
    if not isinstance(u, str) or "://" not in u:
        return u
    u = re.sub(r"(https?):/(?!/)", r"\1://", u, flags=re.I)
    try:
        p = urllib.parse.urlsplit(u)
    except Exception:
        return u
    netloc = p.netloc
    try:
        netloc.encode("ascii")
    except UnicodeEncodeError:
        host = (p.hostname or "").encode("idna").decode("ascii")
        netloc = host + ((":%d" % p.port) if p.port else "")
    path = urllib.parse.quote(urllib.parse.unquote(p.path), safe="/%:@&=+$,;~()!*'")
    query = urllib.parse.quote(urllib.parse.unquote(p.query), safe="=&%:@+$,;~/?()!*'")
    return urllib.parse.urlunsplit((p.scheme, netloc, path, query, ""))


def abs_url(value, base):
    """把 ./ ../ 以及裸相对路径解析为绝对地址，保留 ;md5; 之类的尾巴"""
    if not isinstance(value, str):
        return value
    v = value.strip()
    if not v:
        return value
    if re.match(r"^https?:/+", v, re.I):
        return encode_url(BROKEN_SCHEME_RE.sub(lambda m: m.group(1).lower() + "://", v))
    if v.startswith(("./", "../")):
        return encode_url(urllib.parse.urljoin(base, v))
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", v) or v.startswith(("file:", "assets:", "proxy:", "data:")):
        return encode_url(value)
    if v.startswith("/"):
        return encode_url(urllib.parse.urljoin(base, v))
    return value


def deep_abs(obj, base, key=None):
    if isinstance(obj, dict):
        return {k: deep_abs(v, base, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deep_abs(v, base, key) for v in obj]
    if isinstance(obj, str):
        s = obj.strip()
        if s.startswith(("./", "../")) or s.startswith("/"):
            return abs_url(s, base)
        if key in PATH_KEYS and "/" in s and not s.startswith("csp_") and "://" not in s:
            return abs_url(s, base)
        # 已是绝对 URL 的字段（api / url / ext 等）也要走一遍规范化：
        # 修 https:/ 单斜杠、中文与空格转百分号
        if "://" in s:
            return encode_url(s)
        return obj
    return obj


# ---------------------------------------------------------------- 源展开

def expand_sources(conf):
    """把 sources.json 的配置展开为待抓取列表，支持多仓递归"""
    out = []
    for src in conf.get("sources", []):
        if not src.get("enabled", True):
            continue
        out.append({
            "id": src["id"],
            "name": src.get("name") or src["id"],
            "tag": src.get("tag") or src.get("name") or src["id"],
            "url": norm_url(src["url"]),
            "priority": src.get("priority", 100),
            "timeout": src.get("timeout"),
            "note": src.get("note", ""),
            "parent": None,
        })
    return out


def collect_multi(item, depth=0, budget=None):
    """抓取一个源；若为多仓，展开其子仓（最多 2 层）"""
    budget = budget if budget is not None else []
    try:
        text = fetch(item["url"], item.get("timeout"))
        cfg = parse_cfg(text)
    except Exception as e:  # noqa: BLE001
        item["error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
        return [item]

    if not isinstance(cfg, dict):
        item["error"] = "配置不是 JSON 对象"
        return [item]

    subs = cfg.get("urls") or cfg.get("storeHouse")
    if isinstance(subs, list) and subs:
        if depth >= 2:
            item["error"] = "多仓嵌套超过 2 层"
            return [item]
        results = []
        children = []
        for idx, sub in enumerate(subs):
            if not isinstance(sub, dict):
                continue
            sub_url = sub.get("url") or sub.get("sourceUrl") or ""
            sub_name = sub.get("name") or sub.get("sourceName") or ""
            # 占位条目（有些仓用 "更新时间" 之类做分隔）
            if not sub_url or not re.match(r"^https?://", sub_url.strip()):
                continue
            children.append({
                "id": "%s-%d" % (item["id"], idx + 1),
                "name": "%s / %s" % (item["name"], sub_name or ("子仓%d" % (idx + 1))),
                "tag": item["tag"],
                "url": norm_url(sub_url),
                "priority": item["priority"],
                # 子仓只是一个 json，几十 KB，给 30s 足够；但别再往下砍：本地
                # 实测 20s 会判死 20-30s 才响应的慢子仓（少 160 站），只省 3 秒
                "timeout": min(int(item.get("timeout") or TIMEOUT), CHILD_TIMEOUT),
                "note": "",
                "parent": item["id"],
            })
        if children:
            with ThreadPoolExecutor(max_workers=min(16, len(children))) as pool:
                for part in pool.map(lambda c: collect_multi(c, depth + 1, budget), children):
                    results.extend(part)
        if not results:
            item["error"] = "多仓内无可用子仓"
            return [item]
        return results

    item["cfg"] = cfg
    item["base"] = item["url"]
    return [item]


# ---------------------------------------------------------------- 合并

def stable_key(source_id, orig_key, name):
    raw = (orig_key or "").strip()
    if not raw:
        raw = re.sub(r"\s+", "", name or "") or "site"
    raw = re.sub(r"[^\w\u4e00-\u9fff.\-]+", "_", raw)[:40].strip("_") or "site"
    return "%s_%s" % (source_id.replace("-", ""), raw)


def fingerprint(site):
    """跨源同一性判定：api + ext 归一到「去镜像前缀」后的形态"""
    ext = site.get("ext")
    if isinstance(ext, (dict, list)):
        ext = json.dumps(ext, ensure_ascii=False, sort_keys=True)
    ext = ext or ""
    if ext:
        ext = unwrap_mirror(ext) if ext.startswith("http") else ext
        ext = MIRROR_RE.sub("", ext) if "gh-proxy" in ext or "ghfast" in ext else ext
    return "%s|%s|%s" % (unwrap_mirror(site.get("api") or ""),
                         ext, site.get("type") or "")


# 客户端 Site 模型的字段类型（FongMi/TV bean/Site.java）：
#   String  : key name lang api ext jar click playUrl
#   Integer : type hide indexs timeout searchable changeable quickSearch danmaku
#   List    : categories
#   Object  : header(Map<String,String>) style(Style)
# Gson 是严格类型：ext 收到对象会抛异常。FongMi 用 try-catch 兜住，
# 该站静默变成空站点；严格的客户端则整份配置解析中断 —— 站点列表为空，
# 点播页全白。所以产物必须按这里的类型逐个归一化。
STR_FIELDS = ("key", "name", "lang", "api", "ext", "jar", "click", "playUrl")
INT_FIELDS = ("type", "hide", "indexs", "timeout", "searchable",
              "changeable", "quickSearch", "danmaku")
OBJ_FIELDS = ("header", "style")


def _as_str(v):
    if isinstance(v, str):
        return v
    if isinstance(v, (dict, list)):
        # TVBox 生态的通行写法：ext 用 JSON 文本表示对象
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    return str(v)


def _as_int(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        try:
            return int(float(v.strip()))
        except Exception:
            return None
    return None


def _as_obj(v):
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("{"):
            try:
                o = json.loads(s)
                return o if isinstance(o, dict) else None
            except Exception:
                return None
    return None


def normalize_site(site):
    """把站点字段压成客户端声明接受的字面类型，非法值直接丢弃"""
    out = {}
    for k, v in site.items():
        if v is None:
            continue
        if k in STR_FIELDS:
            out[k] = _as_str(v)
        elif k in INT_FIELDS:
            iv = _as_int(v)
            if iv is not None:
                out[k] = iv
        elif k == "categories":
            if isinstance(v, list):
                out[k] = [str(x) for x in v if x is not None]
            elif isinstance(v, str) and v.strip():
                out[k] = [x.strip() for x in v.split(",") if x.strip()]
        elif k in OBJ_FIELDS:
            ov = _as_obj(v)
            if ov:
                out[k] = ov
        else:
            out[k] = v
    # type 缺失或客户端未定义（如 4）时按 api 形态回填，否则该站点了打不开
    if out.get("type") not in (0, 1, 3):
        api = out.get("api") or ""
        out["type"] = 3 if api.startswith("csp_") else 1
    return out


def build_site(site, src, used_keys, seen_fp, stats, conf_build):
    api = (site.get("api") or "").strip()
    jar = (site.get("jar") or src.get("spider") or "").strip()
    name = (site.get("name") or "").strip() or "未命名"

    if not api:
        stats["skip_no_api"] += 1
        return None
    if api.startswith("csp_") and not jar:
        stats["skip_no_jar"] += 1
        return None

    fp = fingerprint(site)
    if fp in seen_fp:
        stats["dup"] += 1
        return None

    if conf_build.get("name_prefix", True):
        display = "%s·%s" % (src["tag"], name)
    else:
        display = name

    base_key = stable_key(src["id"], site.get("key"), name)
    key = base_key
    n = 2
    while key in used_keys:
        key = "%s_%d" % (base_key, n)
        n += 1
    used_keys.add(key)
    seen_fp.add(fp)

    out = dict(site)
    out["key"] = key
    out["name"] = display
    if jar:
        out["jar"] = jar
    return normalize_site(out)


# ---------------------------------------------------------------------------
# 站点质量排序
#
# 排序目标不是「谁更好看」，而是「打开列表 / 首页 / 搜索时先碰到能用的」：
#   · 首页源取站点列表第一个（VodConfig.setHome 找不到 home 时 fallback 到 get(0)）
#   · 搜索按列表顺序提交，靠前的不影响总量，但靠前的好站点先出结果
# 评分口径写在 README「站点排序」，改动时同步更新文档。
# ---------------------------------------------------------------------------

TOOL_WORDS = ("MV", "音乐", "音频", "磁力", "网盘", "盘搜", "搜搜", "搜索", "下载", "直播",
              "弹幕", "配置", "工具", "急救", "存储", "推送", "图集", "小说", "漫画", "豆瓣",
              "公告", "订阅", "更新", "测速", "线路", "浏览器", "云盘", "央视", "卫视",
              "电台", "有声", "听书")

FILM_WORDS = ("影视", "电影", "电视剧", "剧集", "短剧", "动漫", "综艺", "记录片", "纪录片",
              "片库", "影库", "资源", "采集", "视频", "4K", "高清", "蓝光", "新片", "在线")

KIND_BASE = {"http": 34, "csp": 20, "other": 14, "js": 8, "py": 8}


def api_kind(site):
    api = site.get("api") or ""
    if api.startswith("csp_"):
        return "csp"
    if api.endswith(".js") or ".js?" in api:
        return "js"
    if api.startswith("http"):
        return "http"
    if api.startswith("py_"):
        return "py"
    return "other"


def is_searchable(site):
    v = site.get("searchable")
    return (1 if v is None else v) == 1


def quality_score(site, priority, consensus, dead, alive=False, probe=None):
    """返回 (分数, 说明)。分数越高越靠前。

    probe 是该站点的探活记录 {"ms","code","cls"}，来自 cms_probe。
    它让「能不能用、多快」从布尔升级为连续值：
      · 通的按耗时加分（越快越高）
      · 明确拒绝(403/401/402) 降权 —— 这类站点在客户端点进去必然空白
      · 超时/5xx/非JSON 不评分（海外 runner 网络差异，不能误杀）"""
    kind = api_kind(site)
    jar = (site.get("jar") or "").split(";")[0].strip()
    why = []

    base = KIND_BASE.get(kind, 10)
    why.append("%s+%d" % (kind, base))

    # 不需要额外下载 jar 的最快：内置类直接可用
    if not jar:
        base += 8
        why.append("无jar+8")
    elif jar.endswith(".jar"):
        base += 3
    elif jar.endswith((".js", ".zip")):
        base += 1

    name = site.get("name") or ""
    if any(w in name for w in FILM_WORDS):
        base += 10
        why.append("影视+10")
    if any(w in name for w in TOOL_WORDS):
        base -= 22
        why.append("工具-22")

    # 跨源共识：多个源都收录同一后端，说明这个后端在多方验证下可用（权重要克制，
    # 它衡量的是「传播广」，不是「质量好」，给太大会把音乐/网盘站顶到首页）
    if consensus > 1:
        bonus = min(consensus - 1, 2) * 3
        base += bonus
        why.append("%d源+%d" % (consensus, bonus))

    if is_searchable(site):
        base += 5
    else:
        base -= 6

    if dead:
        base -= 80
        why.append("死链-80")
    elif probe is not None and probe.get("code") == "denied":
        base -= 30
        why.append("被拒-30")
    elif alive:
        base += 20
        why.append("接口通+20")
        # 响应速度：把「通」从布尔细化为梯度。1s 内体感即时，3s 以上明显拖慢搜索
        ms = probe.get("ms") if probe else None
        if isinstance(ms, int) and ms > 0:
            if ms < 800:
                base += 6
                why.append("极速+6")
            elif ms < 1500:
                base += 3
                why.append("较快+3")
            elif ms > 3000:
                base -= 8
                why.append("很慢-8")
            elif ms > 2000:
                base -= 4
                why.append("偏慢-4")

    # 源优先级做细调，避免同分时顺序随机
    base += max(0, 100 - int(priority if priority is not None else 100)) / 20.0
    return base, why


def spider_urls(sites):
    urls = set()
    for s in sites:
        for field in ("jar", "api"):
            v = (s.get(field) or "").split(";")[0].strip()
            if not v.startswith("http"):
                continue
            if field == "jar" or v.endswith(".js") or ".js?" in v:
                urls.add(v)
    return urls


def probe_spiders(sites, timeout=10, workers=12):
    """探活爬虫文件。只把 404/410 判死；超时/连接失败一律不算，
    避免 GitHub 海外 runner 连不上国内域名时误杀站点。"""
    urls = sorted(spider_urls(sites))

    def one(u):
        req = urllib.request.Request(u, headers={
            "User-Agent": UA, "Range": "bytes=0-0", "Accept-Encoding": "identity"})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                r.read(1)
            return u, False
        except urllib.error.HTTPError as e:
            return u, e.code in (404, 410)
        except Exception:  # noqa: BLE001
            return u, False

    dead = set()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for u, gone in pool.map(one, urls):
            if gone:
                dead.add(u)
    return dead


def is_dead(site, dead):
    if not dead:
        return False
    for field in ("jar", "api"):
        v = (site.get(field) or "").split(";")[0].strip()
        if v and v in dead:
            return True
    return False


def cms_probe(sites, timeout=12, workers=16):
    """探活 CMS 采集接口（api?ac=list，返回带 class 的 JSON 视为可用）。

    返回 (info, probed)，info = {key: {"ms": 耗时, "code": 状态, "cls": [分类]}}：
      · 通的记录毫秒数与分类清单，用于速度分与类目识别
      · code: "ok" 通 / "denied" 明确拒绝(403/401/402) / "bad" 其他失败(超时/5xx/非JSON)
    「denied」才降权，「bad」中性 —— GitHub 海外 runner 连不上国内域名时，
    结果退化成纯启发式排序，而不是把可用站点误杀。"""
    cand = [s for s in sites
            if (s.get("api") or "").startswith("http")
            and not (s["api"].endswith(".js") or ".js?" in s["api"])]

    def one(s):
        api = s["api"]
        u = api if "ac=" in api else api + ("&" if "?" in api else "?") + "ac=list"
        t0 = time.time()
        try:
            req = urllib.request.Request(u, headers={
                "User-Agent": UA, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                body = r.read(65536)
            ms = int((time.time() - t0) * 1000)
            txt = body.decode("utf-8", "replace").strip()
            if not txt.startswith(("{", "[")):
                return s["key"], None
            data = json.loads(txt)
            cls = data.get("class") or (data.get("data") or {}).get("class") or []
            if not isinstance(cls, list):
                cls = []
            names = []
            for c in cls:
                if isinstance(c, dict):
                    n = c.get("type_name") or c.get("name")
                    if n:
                        names.append(str(n))
            if not cls and not data.get("list"):
                return s["key"], None
            return s["key"], {"ms": ms, "code": "ok", "cls": names[:24]}
        except urllib.error.HTTPError as e:
            if e.code in (401, 402, 403):
                return s["key"], {"ms": int((time.time() - t0) * 1000),
                                  "code": "denied", "cls": []}
            return s["key"], None
        except Exception:  # noqa: BLE001
            return s["key"], None

    info = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for key, rec in pool.map(one, cand):
            if rec:
                info[key] = rec
    return info, len(cand)


ALIVE_FILE = os.path.join(ROOT, "cms_alive.json")


def load_alive():
    """读取历史探活。兼容两种格式：旧的 {key: ts}，新的 {key: {ts,ms,code,cls}}。"""
    try:
        with open(ALIVE_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            out[k] = v
        else:
            try:
                out[k] = {"ts": int(v), "ms": None, "code": "ok", "cls": []}
            except Exception:  # noqa: BLE001
                continue
    return out


def merge_alive(hist, now_info, ttl_days=7):
    """把本轮探活并入历史，返回 (TTL 内仍算可用的记录, 新历史)。

    本地与 GitHub 海外 runner 的网络差别很大，只认单轮结果会让首页源在
    两次构建之间来回跳；七天内成功过一次就继续算可用。denied 不写入历史——
    403 是上游明确拒绝，下次构建会重新探，不该因为曾经活着就一直加分。"""
    now = int(time.time())
    for k, rec in now_info.items():
        if rec.get("code") == "ok":
            hist[k] = {"ts": now, "ms": rec.get("ms"),
                       "code": "ok", "cls": rec.get("cls") or []}
    ttl = int(ttl_days) * 86400
    hist = {k: v for k, v in hist.items()
            if now - int(v.get("ts", 0)) <= ttl}
    return hist, hist


# ---------------------------------------------------------------------------
# 精选仓：源保底 + 类目配额 + 同库去重
#
# 旧逻辑只做「每源保底 + 分数补满」，结果是电影/剧集采集站霸榜（77/160），
# 综艺/纪录片/音乐整类缺席，且同一资源库（百度/索尼/非凡…）在 40 个源的
# 保底位里反复出现。改为三层：
#   1. 类目识别：优先用 CMS 接口返回的真实分类清单，其次按名字关键词
#   2. 同库去重：同一后端资源库（按 api 域名）在精选里只留分数最高的一个，
#      避免「拾光·非凡」「老刘·非凡」这种换皮入口占名额
#   3. 配额挑选：每个顶层源保底 N 个保覆盖，再按类目配额补到 size，
#      保证电影/剧集为主力的同时，每个内容类型都有代表
# ---------------------------------------------------------------------------

# 类目配额：精选仓的内容构成。键是类目，值是目标占比（合计 ~1.0）。
# 主流影视占大头，小众类型保底——这是「覆盖全」与「精简」的折中。
CATEGORY_QUOTA = {
    "电影剧集": 0.40,
    "短剧":     0.10,
    "动漫":     0.10,
    "综艺":     0.07,
    "4K蓝光":   0.08,
    "纪录片":   0.05,
    "音乐MV":   0.05,
    "戏曲":     0.04,
    "少儿":     0.04,
    "其他":     0.07,
}

# 类目识别关键词：命中即归该类。顺序即优先级，前面的先匹配。
_CATEGORY_RULES = [
    ("4K蓝光",  ("4K", "4k", "蓝光", "BluRay", "蓝光4K", "杜比")),
    ("短剧",    ("短剧", "微剧", "竖屏剧", "爽剧")),
    ("动漫",    ("动漫", "动画", "番剧", "二次元", "哔哩", "B站", "bilibili",
                 "国漫", "日漫", "卡通")),
    ("综艺",    ("综艺", "真人秀", "脱口秀")),
    ("纪录片",  ("纪录", "纪实", "探索发现")),
    ("音乐MV",  ("音乐", "MV", "mv", "🎶", "🎵", "演唱会", "歌曲", "乐库")),
    ("戏曲",    ("戏曲", "戏剧", "京剧", "豫剧", "越剧", "黄梅戏", "评剧", "秦腔")),
    ("少儿",    ("少儿", "儿童", "启蒙", "幼儿", "早教", "kid")),
    ("电影剧集", ("电影", "电视剧", "剧集", "影视", "采集", "资源", "片库",
                  "影院", "剧场", "美剧", "韩剧", "日剧", "港剧", "国产剧",
                  "新片", "在线", "视频", "高清")),
]


def site_category(site, alive=None):
    """判定站点的内容类目。

    首选 CMS 接口返回的真实分类清单（构建期探活已抓到），比名字关键词准：
    一个名叫「XX采集」的站，分类清单里有「动漫/综艺」就说明它真实覆盖这些。
    名字关键词作为兜底（探活未通过的站没有清单）。"""
    alive = alive or {}
    rec = alive.get(site.get("key"))
    cls = rec.get("cls") if isinstance(rec, dict) else None
    if cls:
        joined = " ".join(str(c) for c in cls)
        # 分类清单按「小众优先」：有动漫/综艺/纪录/戏曲/少儿 就归小众，
        # 否则归泛影视。清单存在时以清单为准 —— 名字里的「4K」只是宣传词。
        for cat, words in _CATEGORY_RULES:
            if cat in ("电影剧集", "4K蓝光"):
                continue
            if any(w in joined for w in words):
                return cat
        # 清单里明确有 4K/蓝光专区才认这个类目，否则按泛影视
        if any(w in joined for w in ("4K", "蓝光", "BluRay")):
            return "4K蓝光"
        return "电影剧集"
    name = site.get("name") or ""
    for cat, words in _CATEGORY_RULES:
        if any(w in name for w in words):
            return cat
    return "其他"


def lib_key(site):
    """站点的「资源库」身份：同一后端库只留一个入口。

    主流 CMS 采集站的后端就是它的 api 域名（百度/索尼/非凡…一个域名一个库），
    不同仓收录的只是换皮入口。规则：去掉常见功能性子域（www/api/cj/…），
    剩下的主机名作为库标识 —— 不能粗暴取「最后两段」，否则 example.com 这种
    会把不同子域的不同库误并成一个。"""
    api = (site.get("api") or "").split(";")[0].strip()
    if not api.startswith("http"):
        return api  # csp_/py_ 等按原样，不做库归并
    try:
        host = urllib.parse.urlsplit(api).hostname or ""
    except Exception:  # noqa: BLE001
        return api
    # 只剥离功能性前缀，保留能区分不同库的主机名主体
    for pre in ("www.", "api.", "cj.", "cms.", "vod.", "zy.", "m."):
        if host.startswith(pre):
            host = host[len(pre):]
            break
    return host


def pick_lite(sites, size, per_source=3, bucket_of=None, alive=None,
              quota=None):
    """精选仓选站：源保底保覆盖 + 类目配额保均衡 + 同库去重保精简。

    步骤：
      1. 同库去重：每个资源库只留质量序最高的一个站点
      2. 类目标注：用探活分类清单或名字关键词给每个站点打类目标签
      3. 源保底：每个顶层源取质量序前 per_source 个（不整源消失）
      4. 类目配额：剩余名额按 CATEGORY_QUOTA 分配，类目内按质量序补齐
    保底优先于总额：源多时可能超出 size，此时宁可超出也不裁掉整源。"""
    alive = alive or {}
    quota = quota or CATEGORY_QUOTA
    bucket_of = bucket_of or {}
    order = {id(s): i for i, s in enumerate(sites)}

    # 1. 同库去重：sites 已按质量分降序，先出现的即该库最优
    seen_lib = set()
    dedup = []
    for s in sites:
        lk = lib_key(s)
        if lk in seen_lib:
            continue
        seen_lib.add(lk)
        dedup.append(s)

    # 2. 类目标注
    cat_of = {id(s): site_category(s, alive) for s in dedup}

    # 3. 源保底：每个顶层源取 per_source 个。但不做「纯按质量序取前 N」——
    #    那样会把源里唯一覆盖小众类目（动漫/综艺/纪录）的站点挤出保底位。
    #    改为「先各源取第 1 名保在线，再在源内优先选能补全局类目缺口的」。
    picked = set()
    out = []
    by_src = {}
    for s in dedup:
        sid = s["key"].split("_")[0]
        sid = bucket_of.get(sid, sid)
        by_src.setdefault(sid, []).append(s)

    # 3a. 每源先锁第 1 名（质量序最高，保证这个源在精选里有代表）
    for sid, lst in by_src.items():
        if lst:
            picked.add(id(lst[0]))
            out.append(lst[0])

    # 3b. 剩余保底名额：源内优先选「能补全局缺口类目」的站点
    target = {c: max(1, round(size * w)) for c, w in quota.items()}
    have = {}
    for s in out:
        c = cat_of[id(s)]
        have[c] = have.get(c, 0) + 1
    for sid, lst in by_src.items():
        for s in lst[1:]:
            if sum(1 for x in lst if id(x) in picked) >= per_source:
                break
            c = cat_of[id(s)]
            # 优先选那些「全局还没铺满」的类目站点
            if have.get(c, 0) < target.get(c, 1):
                picked.add(id(s))
                out.append(s)
                have[c] = have.get(c, 0) + 1
    # 3c. 还有源没填满保底（全是泛影视类），按质量序补
    for sid, lst in by_src.items():
        for s in lst:
            if sum(1 for x in lst if id(x) in picked) >= per_source:
                break
            if id(s) not in picked:
                picked.add(id(s))
                out.append(s)
                c = cat_of[id(s)]
                have[c] = have.get(c, 0) + 1

    # 4. 类目配额补满
    if len(out) < size:
        remaining = [s for s in dedup if id(s) not in picked]
        while len(out) < size:
            deficit = sorted(((target.get(c, 0) - have.get(c, 0), c)
                              for c in target), reverse=True)
            progressed = False
            for _, cat in deficit:
                if len(out) >= size:
                    break
                cand = next((s for s in remaining
                             if cat_of[id(s)] == cat and id(s) not in picked), None)
                if cand is None:
                    continue
                picked.add(id(cand))
                out.append(cand)
                have[cat] = have.get(cat, 0) + 1
                progressed = True
            if not progressed:
                for s in remaining:
                    if len(out) >= size:
                        break
                    if id(s) not in picked:
                        picked.add(id(s))
                        out.append(s)
                break

    # 输出按原质量序（首页源=第一个站点，不能打乱）
    out.sort(key=lambda s: order[id(s)])
    return out[:size] if len(out) > size and len(out) > size * 1.05 else out


def rank_sites(sites, prio_map, consensus, dead, alive=None):
    """按质量分降序，同分按源优先级、再按名称，保证每次构建顺序一致。

    alive 是 {key: 探活记录} 的字典（merge_alive 返回），
    不是集合 —— 需要里面的耗时与状态码做速度/403 评分。"""
    alive = alive or {}
    scored = []
    for s in sites:
        sid = s["key"].split("_")[0]
        prio = prio_map.get(sid, 100)
        probe = alive.get(s["key"])
        score, why = quality_score(s, prio, consensus.get(fingerprint(s), 1),
                                   is_dead(s, dead), s["key"] in alive, probe)
        scored.append((score, int(prio), s.get("name") or "", s, why))
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))
    return scored


def normalize_parse(p):
    """Parse 模型同样严格：type 是 Integer，name/url 是 String，ext/header 是对象。
    Parse.objectFrom 没有 try-catch，一个坏字段就会让 initParse 抛异常，
    进而 parseConfig 整体失败 —— 表现就是点播页全空。"""
    out = {}
    for k, v in p.items():
        if v is None:
            continue
        if k in ("name", "url", "click"):
            out[k] = v if isinstance(v, str) else str(v)
        elif k == "type":
            iv = _as_int(v)
            if iv is not None:
                out[k] = iv
        elif k in ("ext", "header"):
            ov = _as_obj(v)
            if ov:
                out[k] = ov
        elif k == "flag":
            if isinstance(v, list):
                out[k] = [str(x) for x in v if x is not None]
        else:
            out[k] = v
    # 没有 type 的解析源客户端无从选择链路，留着也只是占位
    return out if "type" in out else None


def build_parses(all_parses, max_parses):
    by_key = {}
    for p in all_parses:
        if not isinstance(p, dict):
            continue
        p = normalize_parse(p)
        if not p:
            continue
        k = "%s|%s" % (p.get("name") or "", p.get("url") or "")
        if k in by_key:
            by_key[k]["_n"] += 1
            continue
        item = dict(p)
        item["_n"] = 1
        by_key[k] = item
    items = sorted(by_key.values(), key=lambda x: (-x["_n"], x.get("name") or ""))
    if max_parses:
        items = items[:max_parses]
    for it in items:
        it.pop("_n", None)
    return items


def build_lives(all_lives, max_lives):
    out, seen = [], set()
    for live in all_lives:
        if not isinstance(live, dict):
            continue
        k = "%s|%s" % (live.get("name") or "", live.get("url") or "")
        if k in seen:
            continue
        seen.add(k)
        out.append(live)
        if max_lives and len(out) >= max_lives:
            break
    return out


def as_list(x):
    return x if isinstance(x, list) else []


def dedupe_list(seq):
    seen, out = set(), []
    for x in seq:
        if not isinstance(x, str):
            continue
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


# ---------------------------------------------------------------- 主流程

def main():
    with open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
        conf = json.load(f)
    meta = conf.get("meta", {})
    bconf = conf.get("build", {})

    owner = meta.get("owner", "YOUR_GITHUB_NAME")
    repo = meta.get("repo", "source")
    branch = meta.get("branch", "main")
    subdir = (meta.get("subdir") or "").strip("/")
    suffix = (subdir + "/") if subdir else ""
    pages_base = meta.get("pages_base") or "https://%s.github.io/%s/%s" % (owner, repo, suffix)
    raw_base = "https://raw.githubusercontent.com/%s/%s/%s/%s" % (owner, repo, branch, suffix)
    cdn_base = (meta.get("cdn") or [""])[0]
    bases = {"pages": pages_base, "raw": raw_base, "cdn": cdn_base}
    index_base = bases.get(meta.get("index_base", "cdn")) or pages_base

    sources = sorted(expand_sources(conf), key=lambda x: x["priority"])

    # 上一轮规模：用于判断本次抓取是否异常退化
    old_sites = 0
    old_all = os.path.join(ROOT, "api", "all.json")
    if os.path.exists(old_all):
        try:
            with open(old_all, encoding="utf-8") as f:
                old_sites = len(json.load(f).get("sites") or [])
        except Exception:
            old_sites = 0

    # 上一轮产物清单：本轮写完后统一清理，失败源保留旧快照（见下方 orphan 清理）
    api_dir = os.path.join(ROOT, "api")
    old_names = set()
    if os.path.isdir(api_dir):
        old_names = {n for n in os.listdir(api_dir) if n.endswith(".json")}

    # 各源并行抓取：串行时国内源的超时会累加，CI 上可能要十几分钟
    def fetch_one(src):
        t0 = time.time()
        got = collect_multi(src)
        return src, got, int((time.time() - t0) * 1000)

    with ThreadPoolExecutor(max_workers=min(12, max(1, len(sources)))) as pool:
        pulled = list(pool.map(fetch_one, sources))

    results, ok = [], []
    bucket_of = {}
    for src, got, cost in pulled:
        top = src["id"].replace("-", "")
        for g in got:
            g["ms"] = cost // max(1, len(got))
            results.append(g)
            bucket_of[g["id"].replace("-", "")] = top
            if "cfg" in g:
                ok.append(g)
        subs = [g for g in got if "cfg" in g]
        print("[fetch] %-9s 子仓=%-2d 站点=%-4d %sms %s" % (
            src["id"], len(subs),
            sum(len(g["cfg"].get("sites") or []) for g in subs), cost,
            "ok" if subs else (got[0].get("error", "empty") if got else "empty")[:60]))

    # 预展开：一次绝对化，同时统计「同一后端被几个源收录」
    prio_map = {src["id"].replace("-", ""): src.get("priority", 100) for src in sources}
    consensus = {}
    for src in ok:
        src["_abs"] = deep_abs(src["cfg"], src["base"])
        for site in src["_abs"].get("sites") or []:
            fp = fingerprint(site)
            consensus[fp] = consensus.get(fp, 0) + 1

    # 单仓快照 + 收集合并素材
    snapshots = []
    used_keys, seen_fp = set(), set()
    stats = {"dup": 0, "skip_no_api": 0, "skip_no_jar": 0}
    merged_sites = []
    all_parses, all_lives, all_flags, all_ads = [], [], [], []
    first_wall = first_notice = first_spider = ""

    for src in ok:
        cfg = src["_abs"]
        src["spider"] = cfg.get("spider") or ""
        if not first_spider and src["spider"]:
            first_spider = src["spider"]
        if not first_wall and isinstance(cfg.get("wallpaper"), str):
            first_wall = cfg["wallpaper"]
        if not first_notice and isinstance(cfg.get("notice"), str):
            first_notice = cfg["notice"]

        # 单仓快照：保留原 key，仅做绝对化。多仓子仓不再单独出快照——
        # 它们多为镜像，产物价值低，但会让仓库体积按构建次数膨胀。
        # 注意这里同样要走归一化：快照是给人直接填进 APP 的地址，
        # 类型不合规在严格客户端上会整份配置加载失败。
        if bconf.get("emit_source_repo", True) and not src.get("parent"):
            raw_sites = [s for s in (cfg.get("sites") or []) if isinstance(s, dict)]
            raw_parses = [p for p in (cfg.get("parses") or []) if isinstance(p, dict)]
            snap = {
                "spider": src.get("spider", ""),
                "wallpaper": cfg.get("wallpaper", ""),
                "logo": cfg.get("logo", ""),
                "notice": cfg.get("notice", ""),
                "sites": [x for x in (normalize_site(s) for s in raw_sites) if x],
                "parses": [x for x in (normalize_parse(p) for p in raw_parses) if x],
                "flags": cfg.get("flags") or [],
            }
            for extra in ("lives", "doh", "hosts", "rules", "headers", "proxy", "ads"):
                if extra in cfg:
                    snap[extra] = cfg[extra]
            snapshots.append((src["id"], snap))

        before = len(merged_sites)
        for site in cfg.get("sites") or []:
            built = build_site(site, src, used_keys, seen_fp, stats, bconf)
            if built:
                merged_sites.append(built)

        all_parses.extend(as_list(cfg.get("parses")))
        all_lives.extend(as_list(cfg.get("lives")))
        all_flags.extend(as_list(cfg.get("flags")))
        all_ads.extend(as_list(cfg.get("ads")))
        src["n_sites"] = len(cfg.get("sites") or [])
        src["n_new"] = len(merged_sites) - before

    # 爬虫文件探活：404/410 的站点移出聚合搜索（仍能在列表里点开），并在排序中沉底
    dead, demoted = set(), 0
    if bconf.get("probe_spider", True):
        try:
            dead = probe_spiders(merged_sites, timeout=bconf.get("probe_timeout", 10))
        except Exception as e:  # noqa: BLE001
            print("[probe] 跳过：%s" % e)
    for s in merged_sites:
        if is_dead(s, dead) and is_searchable(s):
            s["searchable"] = 2
            demoted += 1
    if bconf.get("probe_spider", True):
        print("[probe] 爬虫文件 %d/%d 失效，%d 个站点移出聚合搜索"
              % (len(dead), len(spider_urls(merged_sites)), demoted))

    # CMS 采集接口探活：通的按速度加分，403 降权，分类清单喂给类目识别
    alive, n_cms, alive_now, denied_now = {}, 0, 0, 0
    if bconf.get("probe_cms", True):
        try:
            fresh, n_cms = cms_probe(merged_sites, timeout=bconf.get("cms_timeout", 12))
            alive_now = sum(1 for r in fresh.values() if r["code"] == "ok")
            denied_now = sum(1 for r in fresh.values() if r["code"] == "denied")
            # denied 是本轮实测的明确拒绝，历史里没有它（merge 只收 ok），
            # 但排序要用，所以并进去
            alive, hist = merge_alive(load_alive(), fresh, bconf.get("alive_ttl_days", 7))
            for k, r in fresh.items():
                if r["code"] == "denied":
                    alive[k] = r
            write_json(ALIVE_FILE, hist)
            print("[probe] CMS 接口本轮 %d/%d 有返回（拒绝 %d），历史有效 %d"
                  % (alive_now, n_cms, denied_now, len(alive)))
        except Exception as e:  # noqa: BLE001
            print("[probe] CMS 探活跳过：%s" % e)

    # 质量排序：首页取第一个站点，站点列表与搜索也按这个顺序
    ranked = rank_sites(merged_sites, prio_map, consensus, dead, alive)
    merged_sites = [item[3] for item in ranked]

    merged = {}
    if first_spider:
        merged["spider"] = first_spider
    if first_wall:
        merged["wallpaper"] = first_wall
    if first_notice:
        merged["notice"] = first_notice
    merged["sites"] = merged_sites
    merged["parses"] = build_parses(all_parses, bconf.get("max_parses", 36))
    if bconf.get("merge_flags", True):
        flags = dedupe_list(all_flags)
        if flags:
            merged["flags"] = flags
    if bconf.get("merge_ads", False):
        ads = dedupe_list(all_ads)
        if ads:
            merged["ads"] = ads
    if bconf.get("merge_lives", True):
        lives = build_lives(all_lives, bconf.get("max_lives", 12))
        if lives:
            merged["lives"] = lives

    # 固定输出值：覆盖各源自带的 name/notice/wallpaper/logo。
    # 上面「取第一个非空」只是让 40 个源的公告不打架，内容仍随源站变；
    # 想要自己的品牌就显式覆盖。留空字符串 = 删掉该字段（例如不要公告）。
    ov = bconf.get("override") or {}
    for k in ("name", "notice", "wallpaper", "logo"):
        if k in ov:
            if ov[k]:
                merged[k] = ov[k]
            else:
                merged.pop(k, None)

    # 网络抖动时宁可保留旧产物，也不要把可用配置覆盖成残废版
    min_ratio = float(bconf.get("min_retain_ratio", 0.85))
    if old_sites and os.environ.get("TVBOX_ALLOW_SHRINK") != "1":
        if len(merged_sites) < old_sites * min_ratio:
            print("[abort] 合并站点 %d 低于上次 %d 的 %.0f%%，判定抓取异常，保留旧产物"
                  % (len(merged_sites), old_sites, min_ratio * 100))
            print("        确认要强制覆盖请设置 TVBOX_ALLOW_SHRINK=1")
            return 1

    planned_src = set()
    for sid, snap in snapshots:
        name = "src-%s.json" % sid
        write_json(os.path.join(ROOT, "api", name), snap)
        planned_src.add(name)
    write_json(os.path.join(ROOT, "api", "all.json"), merged)

    # 精选仓：源保底保覆盖 + 类目配额保均衡 + 同库去重保精简。
    # 只留参与聚合搜索的站点——精选的意义就是「点开能搜到」
    lite_size = int(bconf.get("lite_size", 150))
    lite_sites = pick_lite([s for s in merged_sites if is_searchable(s)],
                           lite_size, int(bconf.get("lite_per_source", 3)),
                           bucket_of, alive)
    lite = {k: v for k, v in merged.items() if k != "sites"}
    lite["sites"] = lite_sites
    write_json(os.path.join(ROOT, "api", "lite.json"), lite)

    # 类目构成统计，写进报告便于核对「覆盖是否全面」
    from collections import Counter as _C
    lite_cat = _C(site_category(s, alive) for s in lite_sites)

    # 多仓索引
    index = {"name": meta.get("name", "聚合影视仓"), "urls": []}
    index["urls"].append({
        "name": "⭐ 精选（%d 站点，排序靠前的）" % len(lite_sites),
        "url": index_base + "api/lite.json",
    })
    index["urls"].append({
        "name": "🌟 全部聚合（%d 站点）" % len(merged_sites),
        "url": index_base + "api/all.json",
    })
    for src in ok:
        # 只列顶层源；多仓展开出的子仓多为聚合镜像，列出来只会误导
        if src.get("parent"):
            continue
        if not src.get("n_sites") or src.get("n_new", 0) < 20:
            continue
        index["urls"].append({
            "name": "%s（%d 站点）" % (src["name"][:24], src["n_sites"]),
            "url": index_base + "api/src-%s.json" % src["id"],
        })
    write_json(os.path.join(ROOT, "index.json"), index)

    # 孤儿产物清理（只针对 src-*）：
    #   · 本轮已写出        → 跳过
    #   · 本轮抓取失败      → 保留上一轮快照（上游抖动一次就把地址变成 404），
    #                        并顺手做类型归一化，防止旧格式快照继续存在
    #   · 源已从配置移除    → 删除
    # 非 src- 前缀的文件一律不碰，避免误删 lite/index/status 等产物。
    failed_ids = {r["id"] for r in results if "cfg" not in r}
    for name in sorted(old_names):
        if not name.startswith("src-") or not name.endswith(".json"):
            continue
        if name in planned_src:
            continue
        sid = name[len("src-"):-len(".json")]
        path = os.path.join(api_dir, name)
        if sid in failed_ids:
            print("[keep] 保留上一轮快照 %s（本次抓取失败）" % name)
            try:
                with open(path, encoding="utf-8") as f:
                    old = json.load(f)
                old["sites"] = [x for x in (normalize_site(s) for s in (old.get("sites") or [])
                                            if isinstance(s, dict)) if x]
                old["parses"] = [x for x in (normalize_parse(p) for p in (old.get("parses") or [])
                                             if isinstance(p, dict)) if x]
                write_json(path, old)
            except Exception as e:  # noqa: BLE001
                print("       归一化失败，保留原样：%s" % str(e)[:60])
            continue
        try:
            os.remove(path)
            print("[clean] 删除孤儿快照 %s" % name)
        except OSError as e:
            print("[clean] 删除失败 %s：%s" % (name, e))

    # 状态与报告
    status = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "total_sites": len(merged_sites),
        "total_parses": len(merged["parses"]),
        "total_lives": len(merged.get("lives") or []),
        "lite_sites": len(lite_sites),
        "searchable_sites": len([s for s in merged_sites if is_searchable(s)]),
        "dead_spider_files": len(dead),
        "demoted_sites": demoted,
        "cms_probed": n_cms,
        "cms_alive": len(alive),
        "cms_alive_now": alive_now,
        "cms_denied_now": denied_now,
        "lite_categories": dict(lite_cat),
        "sources": [
            {
                "id": r["id"],
                "name": r["name"],
                "url": r["url"],
                "ok": "cfg" in r,
                "n_sites": r.get("n_sites", 0),
                "n_new": r.get("n_new", 0),
                "ms": r.get("ms", 0),
                "error": r.get("error", ""),
            }
            for r in results
        ],
        "stats": stats,
    }
    write_json(os.path.join(ROOT, "status.json"), status)
    write_report(status, merged, sources, top=ranked[:20], demoted=demoted)

    # 地址清单：手机端按顺序试，主地址用 CDN
    lines = ["# 精选（%d 站点，排序靠前、接口已验证）" % len(lite_sites)]
    for cdn in meta.get("cdn", []):
        lines.append(cdn + "api/lite.json")
    lines += ["", "# 全部聚合（%d 站点，一个地址装下所有资源）" % len(merged_sites)]
    for cdn in meta.get("cdn", []):
        lines.append(cdn + "api/all.json")
    lines += ["", "# 多仓索引（仅带仓库选择器的客户端可用）"]
    for cdn in meta.get("cdn", []):
        lines.append(cdn + "index.json")
    lines += ["", "# 备用（GitHub raw）", raw_base + "api/lite.json", raw_base + "api/all.json", raw_base + "index.json"]
    lines += ["", "# 备用（raw + 镜像前缀）"]
    for prefix in meta.get("mirrors", []):
        lines.append(prefix.rstrip("/") + "/" + raw_base + "api/lite.json")
        lines.append(prefix.rstrip("/") + "/" + raw_base + "api/all.json")
    lines += ["", "# 可选（需在仓库设置里启用 GitHub Pages）", pages_base + "api/all.json"]
    write_text(os.path.join(ROOT, "mirrors.txt"), "\n".join(lines) + "\n")

    print("\n[done] 合并站点 %d / 解析 %d / 直播 %d，去重 %d，跳过(无api) %d，跳过(无jar) %d" % (
        len(merged_sites), len(merged["parses"]), len(merged.get("lives") or []),
        stats["dup"], stats["skip_no_api"], stats["skip_no_jar"]))
    print("[out ] %s" % os.path.join(ROOT))


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def write_report(status, merged, sources, top=None, demoted=0):
    lines = []
    lines.append("# 构建报告\n")
    lines.append("生成时间：%s\n" % status["generated_at"])
    lines.append("| 指标 | 数值 |")
    lines.append("| --- | --- |")
    lines.append("| 合并后站点数 | %d |" % status["total_sites"])
    lines.append("| 参与聚合搜索 | %d |" % status.get("searchable_sites", 0))
    lines.append("| 精选仓站点数 | %d |" % status.get("lite_sites", 0))
    lines.append("| 解析源数量 | %d |" % status["total_parses"])
    lines.append("| 直播源数量 | %d |" % status["total_lives"])
    lines.append("| 跨源去重丢弃 | %d |" % status["stats"]["dup"])
    lines.append("| 爬虫文件失效 | %d |" % status.get("dead_spider_files", 0))
    lines.append("")
    lines.append("## 各源状态\n")
    lines.append("| 源 | 站点 | 新增 | 耗时 | 状态 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for s in status["sources"]:
        state = "OK" if s["ok"] else ("失败：" + (s["error"] or "未知"))
        lines.append("| %s | %s | %s | %sms | %s |" % (
            s["name"], s["n_sites"] or "-", s.get("n_new", 0), s["ms"], state))
    lines.append("")
    if status["stats"]["skip_no_jar"]:
        lines.append("> 有 %d 个 csp_ 站点因来源仓未提供 spider 被跳过。" % status["stats"]["skip_no_jar"])
    if demoted:
        lines.append("> %d 个站点的爬虫文件返回 404/410，已移出聚合搜索（仍可在站点列表中打开）。" % demoted)
    if top:
        lines.append("")
        lines.append("## 站点排序（前 20，即首页与列表头部）\n")
        lines.append("| # | 站点 | 分数 | 依据 |")
        lines.append("| --- | --- | --- | --- |")
        for i, (score, _prio, _name, site, why) in enumerate(top, 1):
            lines.append("| %d | %s | %.1f | %s |" % (i, site["name"][:26], score, " ".join(why)))
        lines.append("")
        lines.append("排序口径：接口类型（采集 API > 内置爬虫 > JS 爬虫）+ 是否需要下载 jar "
                     "+ 跨源收录数 + 是否参与搜索 − 工具类站点 − 爬虫失效，同分按源优先级。")
    write_text(os.path.join(ROOT, "report.md"), "\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
