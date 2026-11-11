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
import hashlib
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
    api = out.get("api") or ""
    if out.get("type") not in (0, 1, 3):
        out["type"] = 3 if api.startswith("csp_") else 1
    elif out.get("type") == 0 and "xml" not in api.lower():
        # type=0 表示 XML 接口，但部分仓把 CMS JSON 接口也标成了 0（实测这些 api
        # 返回 code/class/list 的 JSON，按 0 去解析会整站白屏）。
        # 真 XML 接口的路径一定带 /at/xml，据此区分：带 xml 的保持 0，其余改 1。
        out["type"] = 1
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
SEARCH_Q_FILE = os.path.join(ROOT, "search_quality.json")


def load_search_quality():
    """读 tools/probe_search.py 的实测结果。没测过就返回空，不影响构建。"""
    try:
        with open(SEARCH_Q_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:  # noqa: BLE001
        return {}
    return {k: v for k, v in raw.items()
            if not k.startswith("_") and isinstance(v, dict)}


def api_norm(site):
    """API 归一化，用来跨源认出「同一个后端」。

    同一个 CMS 后端常被几十个源收录，key 和 api 写法各不相同
    （尾斜杠、?ac=list、http/https、from/xxx 后缀）。只按 key 匹配，
    质检结论只覆盖到实际测过的那一个入口，其余几十个照样在搜索里捣乱。
    """
    api = (site.get("api") or "").split(";")[0].strip()
    if not api.startswith("http"):
        return api
    try:
        p = urllib.parse.urlsplit(api)
    except Exception:  # noqa: BLE001
        return api
    path = p.path.rstrip("/")
    # /from/snm3u8、/at/xml 是同一后端的线路变体，不是另一个库
    path = re.sub(r"/(from|at)/[^/]+$", "", path)
    return "%s%s" % ((p.hostname or "").lower(), path)


def apply_search_quality(sites, sq, block_hosts=()):
    """按实测结果处置站点。

    聚合搜索会把所有 searchable 的站点并发发出去，配置层面只有三种处置：
      · 接口返回 HTML/脚本的站，客户端搜一百次也是空 → searchable=0
      · 不认 wd、回整库列表的站，用户看到「搜什么都一堆不相关」→ searchable=0
      · 相关性差但还能用的站 → quickSearch=0（不进首页快速搜索，完整搜索保留）

    成人内容站直接剔除，并按域名记住，避免上游换个 key 又回来。
    匹配口径：key 精确匹配 → API 归一化匹配（覆盖同后端的其他入口）。
    """
    by_norm = {}
    for r in sq.values():
        api = r.get("api") or ""
        if api:
            by_norm.setdefault(api_norm({"api": api}), r)

    def rec_of(site):
        return sq.get(site.get("key")) or by_norm.get(api_norm(site))

    hosts = tuple(h.lower() for h in block_hosts if h)
    # 本地回环地址：这类站靠用户自己电脑上跑的代理程序工作（api 形如
    # http://127.0.0.1:10079/p/0/proxy/<真实地址>），装到手机/盒子上必然打不开。
    # 而且它们和正常站重复（PG·暴風 == 暴风），留着只会白占搜索线程。
    local = ("127.0.0.1", "localhost", "0.0.0.0", "[::1]")
    drop, n_adult, n_host, n_local, n_off, n_quick = set(), 0, 0, 0, 0, 0
    for s in sites:
        api = (s.get("api") or "").lower()
        r = rec_of(s)
        act = (r or {}).get("action")
        if act == "adult":
            drop.add(s["key"])
            n_adult += 1
            continue
        if any(h in api for h in local):
            drop.add(s["key"])
            n_local += 1
            continue
        if hosts and any(h in api for h in hosts):
            drop.add(s["key"])
            n_host += 1
            continue
        if not r:
            continue
        if act == "disable":
            s["searchable"] = 0
            s["quickSearch"] = 0
            n_off += 1
        elif act == "quick_off":
            s["quickSearch"] = 0
            n_quick += 1
    if drop:
        sites[:] = [s for s in sites if s["key"] not in drop]
    return {"adult": n_adult, "host": n_host, "local": n_local,
            "off": n_off, "quick": n_quick}


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
    "4K蓝光":   0.16,
    "动漫":     0.10,
    "短剧":     0.10,
    "少儿":     0.04,
    "音乐MV":   0.05,
    "戏曲":     0.03,
    "综艺":     0.02,
    "纪录片":   0.02,
    "其他":     0.06,
}

# 精选仓里给类目加的短前缀（客户端站点列表是平铺的，前缀让列表可扫读）
CAT_PREFIX = {
    "电影剧集": "影视",
    "4K蓝光": "4K",
    "音乐MV": "音乐",
    "综艺": "综艺",
    "纪录片": "纪录",
    "其他": "综合",
}

CAT_ORDER = ["电影剧集", "4K蓝光", "动漫", "短剧", "少儿", "综艺",
             "音乐MV", "戏曲", "纪录片", "其他"]

# 小众类目：全量仓里供给只有个位数，不能受「单源上限」约束，否则会被主流源挤空
NICHE_CATS = {"少儿", "戏曲", "综艺", "纪录片", "音乐MV"}

# 类目判定关键词：顺序即优先级。名字里的明确信号优先于分类清单 ——
# 「暴风影视」的分类清单里也有「动漫片」，但它是综合库，不该算动漫站。
_CATEGORY_RULES = [
    ("短剧",    ("短剧", "微剧", "竖屏", "爽剧")),
    ("4K蓝光",  ("4K", "4k", "蓝光", "杜比", "原盘")),
    ("少儿",    ("少儿", "儿童", "儿歌", "启蒙", "幼儿", "早教", "宝宝",
                 "小学", "初中", "高中", "课堂", "教育", "英语", "科学")),
    ("戏曲",    ("戏曲", "京剧", "豫剧", "越剧", "黄梅", "评剧", "秦腔", "相声")),
    ("动漫",    ("动漫", "动画", "番剧", "国漫", "日漫", "B站", "哔哩", "bilibili")),
    ("综艺",    ("综艺", "真人秀", "脱口秀")),
    ("纪录片",  ("纪录", "纪实")),
    ("音乐MV",  ("音乐", "MV", "mv", "KTV", "演唱会", "歌曲", "乐库")),
    ("其他",    ("网盘", "磁力", "搜索", "看球", "直播", "听书", "有声", "小说",
                 "壁纸", "工具", "文件", "浏览器", "市场")),
]

_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\u2190-\u21FF\u2300-\u27BF\u2B00-\u2BFF"
    "\uFE0F\u200d\u20e3\u2122\u2139]"
)
_SEP = re.compile(r"[·┃┆｜|/／\s,，、:：•\-—_]+")
_BRL = re.compile(r"[（）()\[\]【】〔〕《》]")  # 只去括号字符，保留内容
_NUM_TAIL = re.compile(r"(\(?\d+(\.\d+)?[万w]\)?|\d+ms|\d+万)$", re.I)

# 营销词 / 类目词 / 泛称：只说明「它是什么」，不构成品牌，命名时剥掉
_NOISE = {
    "采集", "纯净", "秒播", "多线", "无广", "无广告", "弹幕", "设置", "中心",
    "聚合", "备用", "升级", "推荐", "热推", "线路", "资源", "视频", "在线",
    "影视", "电影", "电视剧", "剧集", "动漫", "动画", "番剧", "微剧", "短剧",
    "综艺", "纪录", "纪录片", "纪实", "音乐", "戏曲", "戏剧", "少儿", "儿童",
    "教育", "课堂", "看球", "直播", "高清", "超清", "蓝光", "原盘", "网盘",
    "文件", "搜索", "预告", "全网", "最新", "免费", "官源", "应用", "商店",
    "辅助", "配置", "大全", "影院", "剧场", "4K", "4k", "8K", "8k", "HD",
    "直连", "极速版", "新版", "旧版", "切", "py", "js", "jar", "drpy", "json",
    "m3u8", "app", "App", "APP", "tv", "TV", "版", "合集", "MV", "mv", "Mv",
    "歌曲", "儿歌", "影音",
}
_NOISE_DESC = sorted(_NOISE, key=len, reverse=True)


def strip_noise(tok):
    """把「旺旺短剧」「醉挽清风4K纯净」「电影天堂」「无损云(12.8万)」剥成纯品牌。

    拉丁词只做整词判断 —— 否则 "KTV" 会被 "TV" 这个噪音词削成 "K"。"""
    tok = _NUM_TAIL.sub("", tok)
    if not re.search(r"[\u4e00-\u9fff]", tok):
        tok = re.sub(r"(jar|js|py|json|m3u8)$", "", tok, flags=re.I)
        tok = re.sub(r"(4k|8k)$", "", tok, flags=re.I)
        tok = re.sub(r"(xyqh?|xyqhj)+$", "", tok, flags=re.I)
        return "" if tok in _NOISE else tok
    tok = re.sub(r"\d+$", "", tok) if len(tok) > 2 else tok
    tok = re.sub(r"(?i)(xyqh?|xyqhj)+$", "", tok)
    changed = True
    while changed and tok:
        changed = False
        for w in _NOISE_DESC:
            if tok == w:
                return ""
            if tok.endswith(w) and len(tok) > len(w):
                tok = tok[:-len(w)]
                changed = True
            elif tok.startswith(w) and len(tok) > len(w):
                tok = tok[len(w):]
                changed = True
    return tok


def _host_label(site):
    """兜底命名：优先取 ext 里的真实站点域名（csp_ 类名对用户没有意义）"""
    for cand in (site.get("ext"), site.get("api")):
        m = re.search(r"https?://([^/\s\"]+)", str(cand or ""))
        if m:
            parts = [x for x in m.group(1).split(":")[0].split(".") if x]
            if parts:
                lab = parts[-2] if len(parts) >= 2 else parts[0]
                if lab not in ("com", "net", "cn", "org", "xyz"):
                    return lab
    api = str(site.get("api") or "").split(";")[0].strip()
    if api.startswith("csp_"):
        return api[4:].replace("Guard", "").replace("App", "")
    if api.startswith("py_"):
        return api[3:]
    return ""


def brand_of(site, tags):
    """从装修过的站名里取出可读品牌。

    返回 (品牌, 是否来自站名)。来自爬虫类名/域名的算「未命名」，
    这类站点在精选仓里按类目编字母，不拿类名糊弄用户。"""
    s = site.get("name") or ""
    head, _, rest = s.partition("·")
    if rest and head in tags:
        s = rest
    s = _BRL.sub("", s)
    s = _EMOJI.sub("", s)
    toks = []
    for t in _SEP.split(s):
        t = strip_noise(t.strip(" 　.。·-—_"))
        if t:
            toks.append(t)
    if toks:
        return "".join(toks[:2])[:8], True
    return _host_label(site)[:8], False


def site_category(site, alive=None):
    """判定站点的内容类目（名字信号优先，CMS 分类清单兜底）。

    上一版只看分类清单，而几乎所有 CMS 采集站的清单里都同时有「电影片」和
    「动漫片」，结果 80% 的综合库被判成动漫站。现在改成：
    名字里明确指向某一类（魔都┃动漫 / 旺旺短剧 / 兔兔儿歌）才归该类，
    否则看清单里有没有电影/剧集分类 —— 有就是综合库。"""
    alive = alive or {}
    name = site.get("name") or ""
    clean = _BRL.sub("", _EMOJI.sub("", name.partition("·")[2] or name))
    for cat, words in _CATEGORY_RULES:
        if any(w in clean for w in words):
            return cat
    rec = alive.get(site.get("key"))
    cls = rec.get("cls") if isinstance(rec, dict) else None
    if cls:
        joined = " ".join(str(c) for c in cls)
        if any(w in joined for w in ("电影", "剧集", "连续剧", "电视剧", "片")):
            return "电影剧集"
        for cat, words in _CATEGORY_RULES:
            if any(w in joined for w in words):
                return cat
    if any(w in name for w in ("影视", "电影", "剧集", "采集", "影院")):
        return "电影剧集"
    return "其他"


def lib_key(site):
    """HTTP 采集站的「资源库」身份：去掉功能性子域后的主机名。

    不能粗暴取末两段 —— blbl.example.com 与 mgzy.example.com 会被并成
    example.com，把两个不同的库当成一个。"""
    api = (site.get("api") or "").split(";")[0].strip()
    if not api.startswith("http"):
        return api
    try:
        host = urllib.parse.urlsplit(api).hostname or ""
    except Exception:  # noqa: BLE001
        return api
    # app./m./play. 是同一后端的移动端镜像，不剥会留下「暴风」「暴风影音」两个入口
    for pre in ("www.", "api.", "cj.", "cms.", "vod.", "zy.", "m.", "app.", "play."):
        if host.startswith(pre):
            host = host[len(pre):]
            break
    return host


def lib_of(site):
    """资源库身份。csp_ 站点同一个爬虫类会被几十个不同站点复用，
    只按类名归并会把「兔兔儿歌」和「宝宝儿歌」当成同一个库 —— 必须带上 ext。"""
    api = str(site.get("api") or "")
    if api.startswith(("csp_", "py_")):
        ext = site.get("ext")
        if isinstance(ext, (dict, list)):
            ext = json.dumps(ext, ensure_ascii=False, sort_keys=True)
        return "%s|%s" % (api, str(ext or "")[:120])
    return lib_key(site)


def lite_name(cat, brand):
    return "%s·%s" % (CAT_PREFIX.get(cat, cat), brand)


def pick_lite(sites, size, per_source=5, bucket_of=None, alive=None,
              quota=None, tags=None, sq=None, pin=()):
    """精选仓选站：一个资源库只留一个入口、按类目配额铺开、名字统一重写。

    与 all.json 的分工：all.json 保留「源前缀·原名」便于溯源排查，
    lite.json 是给用户看的成品，去掉来源前缀、emoji 和营销词，按类目分组。

    选站顺序：必收录 → 质量序 → 同类目不超过配额 → 同一顶层源不超过 per_source。
    某库的最佳代表因单源上限进不来时，自动换用该库下一个来源的代表 ——
    否则会出现「最好的库被同作者的系列站挤掉」这种反直觉结果。

    `pin` 是 sources.json 里点名的 key，先钉进来占名额再走常规选站：
    有些站质量分不差，但同类目候选上百个、单源又已满额，纯按规则永远排不进。

    sq 是 tools/probe_search.py 的实测结果。域名不同的站可能挂着同一个内容库
    （实测有 8 个站搜同一关键词返回一模一样的 8 条），只靠 lib_key 分不出来，
    所以再用「搜索结果指纹」兜一层：指纹相同的只留一个入口。"""
    alive = alive or {}
    quota = quota or CATEGORY_QUOTA
    bucket_of = bucket_of or {}
    tags = tags or set()
    sq = sq or {}
    order = {id(s): i for i, s in enumerate(sites)}

    def top_of(s):
        sid = s["key"].split("_")[0]
        return bucket_of.get(sid, sid)

    def search_sig(key):
        """同关键词下返回完全相同的标题集合 → 同一个内容库的不同外壳。"""
        r = sq.get(key)
        if not r:
            return None
        t = r.get("titles1") or []
        if len(t) < 5:
            return None
        return hashlib.md5("\n".join(sorted(t)).encode("utf-8")).hexdigest()[:12]

    seen_b, cand = set(), []
    for s in sites:
        try:
            cat = site_category(s, alive)
            brand, named = brand_of(s, tags)
        except Exception:  # noqa: BLE001 —— 脏站名只该丢这一个站
            continue
        if named:
            if brand.lower() in seen_b:
                continue
            seen_b.add(brand.lower())
        cand.append({"site": s, "cat": cat, "brand": brand,
                     "named": named, "top": top_of(s),
                     "sig": search_sig(s["key"])})

    libs = {}
    for c in cand:
        libs.setdefault(lib_of(c["site"]), []).append(c)
    for v in libs.values():
        v.sort(key=lambda x: (not x["named"], order[id(x["site"])]))
    groups = sorted(libs.values(),
                    key=lambda v: (not v[0]["named"], order[id(v[0]["site"])]))

    caps = {c: max(1, round(size * quota.get(c, 0.02))) for c in CAT_ORDER}
    out, used, filled, seen_lib, seen_sig = [], {}, {}, set(), set()
    stem = {}

    # 必收录：用户点名的站先钉进来。这类站往往质量不差，只是同类目候选上百个、
    # 单源又已满额，纯按规则永远排不到。先占名额，常规流程再按剩余名额铺。
    by_key = {c["site"]["key"]: c for c in cand}
    for pk in (pin or ()):
        c = by_key.get(pk)
        if not c or c["site"]["key"] in {x["site"]["key"] for x in out}:
            continue
        lib = lib_of(c["site"])
        if lib in seen_lib:
            continue
        seen_lib.add(lib)
        if c["sig"]:
            seen_sig.add(c["sig"])
        out.append(c)
        used[c["top"]] = used.get(c["top"], 0) + 1
        filled[c["cat"]] = filled.get(c["cat"], 0) + 1
        stem[(c["cat"], c["brand"][:2])] = stem.get((c["cat"], c["brand"][:2]), 0) + 1
    if pin:
        print("[lite] 必收录 %d 个：%s" % (
            len(out), "、".join(c["brand"] for c in out)))

    def take(group, lib, relax_cat=False, relax_src=False):
        for c in group:
            if not relax_cat and filled.get(c["cat"], 0) >= caps[c["cat"]]:
                continue
            if relax_cat and filled.get(c["cat"], 0) >= caps[c["cat"]] + 2:
                continue
            if not relax_src and c["cat"] not in NICHE_CATS and used.get(c["top"], 0) >= per_source:
                continue
            if not c["named"] and any(x["cat"] == c["cat"] and x["named"] for x in group):
                continue
            if relax_cat and not c["named"]:
                continue
            if c["sig"] and c["sig"] in seen_sig:
                continue
            k = (c["cat"], c["brand"][:2])
            if stem.get(k, 0) >= 3:  # 同一作者的系列站（分享U酷/分享最大…）最多 3 个
                continue
            seen_lib.add(lib)
            if c["sig"]:
                seen_sig.add(c["sig"])
            out.append(c)
            used[c["top"]] = used.get(c["top"], 0) + 1
            filled[c["cat"]] = filled.get(c["cat"], 0) + 1
            stem[k] = stem.get(k, 0) + 1
            return True
        return False

    for group in groups:
        if len(out) >= size:
            break
        lib = lib_of(group[0]["site"])
        if lib in seen_lib:
            continue
        take(group, lib)

    # 名额没填满：先放宽类目配额，再放宽单源上限
    if len(out) < size:
        for group in groups:
            if len(out) >= size:
                break
            lib = lib_of(group[0]["site"])
            if lib not in seen_lib:
                take(group, lib, relax_cat=True)
    if len(out) < size:
        for group in groups:
            if len(out) >= size:
                break
            lib = lib_of(group[0]["site"])
            if lib in seen_lib:
                continue
            seen_lib.add(lib)
            c = group[0]
            out.append(c)
            used[c["top"]] = used.get(c["top"], 0) + 1

    # 取不到站名的按类目编字母（戏曲那类全是匿名 jar 站）
    seq = {}
    for c in out:
        if not c["named"]:
            seq[c["cat"]] = seq.get(c["cat"], 0) + 1
            n = seq[c["cat"]]
            c["brand"] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[n - 1] if n <= 26 else str(n)

    def breadth(c):
        rec = alive.get(c["site"].get("key"))
        cls = rec.get("cls") if isinstance(rec, dict) else None
        return len(cls or [])

    # 首页源：FongMi 拿配置里第一个站点当首页，固定选分类最全的综合库
    head = None
    film = [c for c in out if c["cat"] == "电影剧集"]
    if film:
        head = max(film, key=lambda c: breadth(c))
        out.remove(head)

    ordered = ([head] if head else []) + sorted(
        out, key=lambda c: (CAT_ORDER.index(c["cat"]), order[id(c["site"])]))

    result = []
    for c in ordered[:size]:
        t = dict(c["site"])
        t["name"] = lite_name(c["cat"], c["brand"])
        result.append(t)
    return result


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
            # 必须是 0：客户端按 searchable != 0 判断能否搜索，
            # 原来写 2 等于「照样参与聚合搜索」，只会占并发、拖慢并污染结果
            s["searchable"] = 0
            s["quickSearch"] = 0
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

    # 搜索质量实测（tools/probe_search.py）：关掉搜不到/搜不准的站，剔除成人内容
    sq = load_search_quality()
    if sq:
        st = apply_search_quality(merged_sites, sq, bconf.get("block_hosts") or [])
        print("[search] 实测 %d 站：剔除 %d（成人 %d / 域名黑名单 %d / 本机代理 %d），"
              "关搜索 %d，仅关快速搜索 %d"
              % (len(sq), st["adult"] + st["host"] + st["local"],
                 st["adult"], st["host"], st["local"], st["off"], st["quick"]))
    else:
        st = {"adult": 0, "host": 0, "local": 0, "off": 0, "quick": 0}

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
    lite_size = int(bconf.get("lite_size", 72))
    tags = {s.get("tag") for s in sources} | {s.get("name") for s in sources}
    lite_sites = pick_lite([s for s in merged_sites if is_searchable(s)],
                           lite_size, int(bconf.get("lite_per_source", 5)),
                           bucket_of, alive, tags=tags, sq=sq,
                           pin=bconf.get("pin_keys") or ())
    lite = {k: v for k, v in merged.items() if k != "sites"}
    lite["sites"] = lite_sites
    write_json(os.path.join(ROOT, "api", "lite.json"), lite)

    # 类目构成统计，写进报告便于核对「覆盖是否全面」
    from collections import Counter as _C
    # 精选仓的名字已经是「类目·品牌」，直接按前缀还原类目，
    # 不要再跑一遍 site_category（它看的是源名，会把重写后的名字判歪）
    _rev = {c: c for c in CAT_ORDER}  # 动漫/短剧/少儿/戏曲 的前缀就是类目名本身
    _rev.update({v: k for k, v in CAT_PREFIX.items()})
    lite_cat = _C(_rev.get(s["name"].split("·")[0], "其他") for s in lite_sites)

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
        "search_quality": st,
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
    sqs = status.get("search_quality") or {}
    if sqs:
        lines.append("| 搜索实测：关搜索 | %d |" % sqs.get("off", 0))
        lines.append("| 搜索实测：仅关快速搜索 | %d |" % sqs.get("quick", 0))
        lines.append("| 剔除：成人内容 | %d |" % sqs.get("adult", 0))
        lines.append("| 剔除：域名黑名单 | %d |" % sqs.get("host", 0))
        lines.append("| 剔除：本机代理地址 | %d |" % sqs.get("local", 0))
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
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 —— CI 上的 traceback 必须能带回来
        import traceback
        tb = traceback.format_exc()
        print(tb)
        try:
            with open(os.path.join(ROOT, "last_error.txt"), "w",
                      encoding="utf-8", newline="\n") as f:
                f.write(tb)
        finally:
            sys.exit(1)
