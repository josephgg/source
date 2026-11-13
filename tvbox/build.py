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
from datetime import datetime, timedelta, timezone

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
    # 苹果CMS 的 /at/xml 是同一后端的 XML 输出。XML 体积是同内容的 3~5 倍，
    # 且很多客户端只实现了 JSON 解析（拿到 <?xml 直接整站空），改成 JSON 端点
    # 兼容面更大。注意必须在类型回填之前改：改完 api 就不再是 XML 接口。
    if isinstance(api, str) and re.search(r"/at/xml/?$", api, re.I):
        api = re.sub(r"/at/xml/?$", "/", api, flags=re.I)
        out["api"] = api
        out["type"] = 1
    if out.get("type") not in (0, 1, 3):
        out["type"] = 3 if api.startswith("csp_") else 1
    elif out.get("type") == 0 and "xml" not in api.lower():
        # type=0 表示 XML 接口，但部分仓把 CMS JSON 接口也标成了 0（实测这些 api
        # 返回 code/class/list 的 JSON，按 0 去解析会整站白屏）。
        # 真 XML 接口的路径一定带 /at/xml，据此区分：带 xml 的保持 0，其余改 1。
        out["type"] = 1
    return out


def site_list(cfg):
    """只接受站点对象列表；上游把 sites 写成字符串/数字时隔离该字段。"""
    raw = cfg.get("sites") if isinstance(cfg, dict) else None
    return [s for s in raw if isinstance(s, dict)] if isinstance(raw, list) else []


def build_site(site, src, used_keys, seen_fp, stats, conf_build):
    if not isinstance(site, dict) or not isinstance(site.get("api"), str):
        stats["skip_bad_site"] += 1
        return None
    site = normalize_site(site)
    api = (site.get("api") or "").strip()
    raw_jar = site.get("jar") or src.get("spider") or ""
    jar = raw_jar.strip() if isinstance(raw_jar, str) else ""
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
    """与 FongMi 客户端一致：只有明确的 0 才关闭搜索。

    上游有 searchable=2 的写法；旧逻辑只认 1，会把客户端实际可搜的站
    错排除在精选仓之外。normalize_site 已把数字字符串转成 int。
    """
    v = _as_int(site.get("searchable"))
    return v is None or v != 0


def quality_score(site, priority, consensus, dead, alive=False, probe=None, search=None,
                  rule=None, play=None):
    """返回 (分数, 说明)。分数越高越靠前。

    probe 是该站点的探活记录 {"ms","code","cls"}，来自 cms_probe。
    它让「能不能用、多快」从布尔升级为连续值：
      · 通的按耗时加分（越快越高）
      · 明确拒绝(403/401/402) 降权 —— 这类站点在客户端点进去必然空白
      · 超时/5xx/非JSON 不评分（海外 runner 网络差异，不能误杀）

    rule 是 tools/probe_rules.py 的体检记录。这类站（jar/drpy）没法用
    ac=videolist 验活，只能验「jar 完整 + 规则可解析 + 规则里的目标站还在」，
    所以它的结论只做加减分，不参与 alive 的「接口通 +20」。"""
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

    # 搜索实测不再只是开关，也参与质量排序。旧版只把弱站移出快速搜索，
    # 却仍可能凭「HTTP + 分类多」坐上首页。未知结果不奖惩，避免误杀。
    if search:
        verdict = search.get("verdict")
        hit = search.get("hit_rate")
        action = search.get("action")
        if action == "keep" and verdict in ("good", "ok") and isinstance(hit, (int, float)):
            if hit >= 0.85:
                base += 12
                why.append("搜索精准+12")
            elif hit >= 0.70:
                base += 6
                why.append("搜索合格+6")
        elif action == "quick_off" or verdict == "weak":
            base -= 12
            why.append("搜索杂乱-12")
        elif action == "disable":
            base -= 20
            why.append("搜索不可用-20")

    if rule:
        lv = rule.get("level")
        streak = int(rule.get("dead_streak") or 1)
        if lv == "ok":
            base += 6
            why.append("规则可验+6")
        elif lv == "weak":
            # 主页能开但选择器不命中，典型是站点改版：分类还在、点进去空白
            base -= 12
            why.append("规则疑似改版-12")
        elif lv == "dead":
            if streak >= 2:
                base -= 90
                why.append("规则站失效-90")
            else:
                base -= 30
                why.append("规则站首轮不可达-30")
        # unverifiable：ext 为空或目标写在 jar 内，离线无法判定，绝不扣分

    # 播放链路实测（tools/probe_play.py）：接口通 ≠ 能播。
    # 实测踩到的三类：首集是网盘分享页（返回 HTML）、分集 URL 带未编码中文
    # （客户端拼 URL 抛异常）、清单正常但分片 404（播几秒就断）。
    if play:
        verdict = play.get("verdict")
        if verdict in PLAY_STRUCTURAL:
            base -= 60
            why.append("播放结构性缺陷-60")
        elif verdict in PLAY_FLAKY:
            base -= 20
            why.append("播放链路异常-20")
        elif verdict == "ok":
            base += 8
            why.append("播放实测通过+8")
        elif verdict == "direct":
            base += 4
            why.append("直链可播+4")
        elif verdict in PLAY_SECONDARY:
            base -= 25
            why.append("默认线路播不了-25")
        # python_spider / rule_based / unverifiable：解析在客户端，离线判不了，不奖惩

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
                # 不能只读 64KB 再 json.loads：分类多的大站会被硬截断，误判为
                # 非 JSON，进而丢失分类、速度分和首页候选资格。1MB 足够覆盖 CMS 列表。
                body = r.read(1024 * 1024)
            ms = int((time.time() - t0) * 1000)
            try:
                txt = body.decode("utf-8").strip()
            except UnicodeDecodeError:
                txt = body.decode("gb18030", "replace").strip()
            if not txt.startswith(("{", "[")):
                return s["key"], None
            data = json.loads(txt)
            if not isinstance(data, dict):
                return s["key"], None
            nested = data.get("data")
            cls = data.get("class") or (nested.get("class") if isinstance(nested, dict) else []) or []
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
            return s["key"], {"ms": ms, "code": "ok", "cls": names[:48],
                              "api": api_norm(s)}
        except urllib.error.HTTPError as e:
            if e.code in (401, 402, 403):
                return s["key"], {"ms": int((time.time() - t0) * 1000),
                                  "code": "denied", "cls": [], "api": api_norm(s)}
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
RULE_HEALTH_FILE = os.path.join(ROOT, "rule_health.json")
PLAY_FILE = os.path.join(ROOT, "play_health.json")
# 体检结论超过这个天数就不再采信：域名会复活，规则也会被上游修好，
# 拿一个月前的 dead 判定去杀站，等于把可用资源当垃圾清掉。
RULE_HEALTH_TTL_DAYS = 21
# 播放地址比规则变化快得多（换 CDN、换线路顺序都常见），有效期要更短
PLAY_TTL_DAYS = 10
# 结构性缺陷：接口/线路本身出不了流，不会自愈，一轮即生效。
# 注意不含 xml_endpoint —— normalize_site 会把 /at/xml 改写成 JSON 端点，
# 拿旧判决去踢，等于把刚修好的站再杀一次。
PLAY_STRUCTURAL = {"share_page", "bad_url", "live_format", "dns_dead"}
# 默认线路不可用、备用线路可播。搜索和分类都正常，但客户端默认播第一条线路，
# 用户点开就是黑屏/闪退（实测非凡、量子的第一条是网盘分享页）。
# 因此不进精选，但保留在聚合搜索里 —— 会切线路的用户还能用上它的内容。
# xml_endpoint 同理：接口回 XML 但路径里没有 /at/xml（改写规则覆盖不到），
# 客户端按 JSON 解析必然空分类，也不该进精选。
PLAY_SECONDARY = {"ok_secondary", "xml_endpoint"}
# 网络侧缺陷：可能只是节点/边缘抖动，连续两轮才定案
PLAY_FLAKY = {"dead_link", "bad_segment", "html_link"}
PLAY_HARD = PLAY_STRUCTURAL | PLAY_SECONDARY | PLAY_FLAKY


def load_search_quality():
    """读 tools/probe_search.py 的实测结果。没测过就返回空，不影响构建。"""
    try:
        with open(SEARCH_Q_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:  # noqa: BLE001
        return {}
    return {k: v for k, v in raw.items()
            if not k.startswith("_") and isinstance(v, dict)}


def rule_sig(site):
    """规则站指纹：api + jar + ext 三者一起算，供 key 改名后继承体检结论。

    与 fingerprint() 的区别：那个用来判「同一个站点」，含 name；这里只关心
    「同一个规则配置」，名字变了（上游加前缀/改品牌）不该丢掉健康记录。
    """
    api = str(site.get("api") or "").split(";")[0].strip()
    jar = str(site.get("jar") or "").split(";")[0].strip()
    ext = site.get("ext")
    if isinstance(ext, (dict, list)):
        ext = json.dumps(ext, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(
        ("%s\n%s\n%s" % (api, jar, str(ext or "").strip())).encode("utf-8")
    ).hexdigest()[:16]


def load_rule_health(ttl_days=RULE_HEALTH_TTL_DAYS):
    """读 tools/probe_rules.py 的体检结果，按 key 和规则指纹双索引。

    文件不存在或过期都返回空字典：构建不该因为「没跑体检」而失败，
    更不该因为一份旧结论把可用站点判死。
    """
    try:
        with open(RULE_HEALTH_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:  # noqa: BLE001
        return {}
    recs = raw.get("sites") if isinstance(raw, dict) else raw
    if not isinstance(recs, list):
        return {}
    tested = raw.get("tested_at") if isinstance(raw, dict) else 0
    if tested and time.time() - float(tested) > ttl_days * 86400:
        print("[rules] 体检结果已过期（>%d 天），本轮不采信" % ttl_days)
        return {}
    out = {}
    for r in recs:
        if not isinstance(r, dict) or not r.get("key"):
            continue
        out[r["key"]] = r
        sig = r.get("sig") or rule_sig(r)
        if sig:
            out.setdefault("sig#" + sig, r)
    return out


def rule_record(site, rh):
    """取站点的体检记录：先按 key 精确匹配，再按规则指纹匹配。"""
    rh = rh or {}
    rec = rh.get(site.get("key"))
    if rec:
        return rec
    return rh.get("sig#" + rule_sig(site))


def rule_dead(site, rh):
    """硬失效：连续两轮判死才算。

    单轮网络抖动很常见（4MB 大 jar 带保护壳，弱网首跑必超时），
    一轮就踢站会误杀；连续两轮仍是 dead，基本可以确定站点或规则废了。
    """
    r = rule_record(site, rh)
    if not r or r.get("level") != "dead":
        return False
    return int(r.get("dead_streak") or 1) >= 2


def apply_rule_health(sites, rh):
    """硬失效的规则站移出聚合搜索（站点仍留在列表里，便于用户自行核对）。

    与爬虫 404 同一处置口径：搜不到内容的站留在聚合搜索里只会占并发、
    拖慢整体返回，还会让「搜索无结果」被误认为仓里没这片子。
    """
    n = 0
    for s in sites:
        if not rule_dead(s, rh):
            continue
        if is_searchable(s):
            s["searchable"] = 0
            s["quickSearch"] = 0
            n += 1
    return n


def play_sig(site):
    """播放体检的继承键：按「同一后端」归一，不看名字也不看入口写法。

    同一后端被几十个源收录，主机和路径写法各不相同，但播放行为完全一样：
      cj.ffzyapi.com/api.php/provide/vod/
      ffzyapi.com/api/provide/vod/
    按 lib_key 比对仍会漏（前者 /api.php/、后者 /api/），实测「非凡」就因此
    带着「默认线路是网盘分享页」的毛病重新混进了精选。这里把功能子域和
    接口前缀一并抹掉，只留主机主干 + 业务路径。
    """
    norm = api_norm(site)
    if not norm or not isinstance(norm, str) or norm.startswith(("csp_", "py_")):
        return norm
    host, _, rest = norm.partition("/")
    for pre in ("www.", "api.", "cj.", "cms.", "vod.", "zy.", "m.", "app.", "play."):
        if host.startswith(pre):
            host = host[len(pre):]
            break
    path = "/" + rest
    # api.php/provide/vod 与 api/provide/vod 是同一接口的两种写法
    if path.startswith("/api.php/"):
        path = path[len("/api.php"):]
    elif path.startswith("/api/"):
        path = path[len("/api"):]
    return host + path


def load_play_health(ttl_days=PLAY_TTL_DAYS):
    """读 tools/probe_play.py 的播放链路体检结果。

    文件不存在或过期返回空：播放地址天天变，一份两周前的「首集 404」
    极可能已经修好，不能拿旧结论杀站。
    """
    try:
        with open(PLAY_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:  # noqa: BLE001
        return {}
    recs = raw.get("sites") if isinstance(raw, dict) else raw
    if not isinstance(recs, list):
        return {}
    tested = raw.get("tested_at") if isinstance(raw, dict) else 0
    if tested and time.time() - float(tested) > ttl_days * 86400:
        print("[play] 播放体检已过期（>%d 天），本轮不采信" % ttl_days)
        return {}
    out = {}
    for r in recs:
        if not isinstance(r, dict):
            continue
        if r.get("key"):
            out[r["key"]] = r
        sig = r.get("sig") or play_sig(r)
        if sig:
            out.setdefault("api#" + sig, r)
    return out


def play_record(site, ph):
    """取播放体检记录：先按 key，再按归一化 api（换皮站共享结论）。"""
    ph = ph or {}
    rec = ph.get(site.get("key"))
    if rec:
        return rec
    return ph.get("api#" + play_sig(site))


def play_bad(site, ph, for_lite=False):
    """返回该站的播放缺陷等级：structural / secondary / flaky / ""。

    结构性缺陷（首集是网盘分享页、URL 带未编码中文、直播格式）不可能自己恢复，
    一轮即生效；网络侧的 404/502/分片取不到要连续两轮，否则一次边缘抖动就会误杀。

    for_lite=True 时把「默认线路不可用」也算进去：精选是给用户直接点的成品，
    默认线路播不了就没有存在意义；而全量列表可以留着，让会切线路的人自己用。

    「搜索不通」则要先看 DoH：本机 DNS 被拦的站是好的，不能杀；DoH 也没有
    A 记录的才是域名真死，同样不该进精选。
    """
    r = play_record(site, ph)
    if not r:
        return ""
    verdict = r.get("verdict")
    if verdict in PLAY_STRUCTURAL:
        return "structural"
    if verdict in PLAY_SECONDARY:
        return "secondary" if for_lite else ""
    if verdict in PLAY_FLAKY and int(r.get("bad_streak") or 1) >= 2:
        return "flaky"
    if verdict == "search_fail":
        # 搜索都不通要先分清是谁的锅：DoH 拿得到 A 记录，说明只是本机 DNS 被拦，
        # 手机上照样能用，不能杀；DoH 也没有 A 记录（NXDOMAIN / 空解析 / SERVFAIL），
        # 那是域名自己死了，留在精选里只会让用户搜出一片空。
        if r.get("doh_ips"):
            return ""
        if for_lite or int(r.get("bad_streak") or 0) >= 2:
            return "structural"
        return ""
    return ""


def apply_play_health(sites, ph):
    """播放不可用的站移出聚合搜索。站点仍在列表里，用户可自行点开核对。"""
    n = 0
    for s in sites:
        if not play_bad(s, ph):
            continue
        if is_searchable(s):
            s["searchable"] = 0
            s["quickSearch"] = 0
            n += 1
    return n


def api_norm(site):
    """API 归一化，用来跨源认出「同一个后端」。

    统一主机大小写、重复斜杠、尾斜杠、ac/wd/pg 参数和 from/at 线路后缀；
    保留 source/type 等业务参数——它们可能指向同一域名下的不同内容库。
    非 HTTP 的 csp_/py_ 标识原样返回，调用方仍需结合 ext 判断资源库。
    """
    api = str(site.get("api") or "").split(";")[0].strip()
    if not api.startswith("http"):
        return api
    try:
        p = urllib.parse.urlsplit(api)
    except Exception:  # noqa: BLE001
        return api
    host = (p.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    try:
        port = p.port
    except ValueError:
        return api
    if port and not ((p.scheme == "http" and port == 80) or
                     (p.scheme == "https" and port == 443)):
        host += ":%d" % port
    path = re.sub(r"/{2,}", "/", p.path).rstrip("/")
    # /from/snm3u8、/at/xml 是同一后端的线路变体，不是另一个库。
    # 循环处理 /from/x/at/m3u8 这种连续后缀。
    old = None
    while old != path:
        old = path
        path = re.sub(r"/(from|at)/[^/]+$", "", path, flags=re.I)
    query = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
    query = sorted((k, v) for k, v in query
                   if k.lower() not in ("ac", "wd", "pg", "page"))
    suffix = ("?" + urllib.parse.urlencode(query)) if query else ""
    return "%s%s%s" % (host, path, suffix)


def index_search_quality(sq):
    """按归一化 API 建索引，让一个入口的实测结论覆盖同后端别名。

    同一 API 若有多条记录，安全处置优先（adult > disable > quick_off > keep），
    避免 setdefault 碰巧先读到一条旧的 keep 而把已确认的问题站放回来。
    """
    severity = {"keep": 0, "quick_off": 1, "disable": 2, "adult": 3}
    by_norm = {}
    for r in (sq or {}).values():
        if not isinstance(r, dict) or not r.get("api"):
            continue
        norm = api_norm({"api": r["api"]})
        old = by_norm.get(norm)
        candidate = (severity.get(r.get("action"), 0), int(r.get("tested_at") or 0))
        current = (severity.get((old or {}).get("action"), 0),
                   int((old or {}).get("tested_at") or 0)) if old else (-1, -1)
        if old is None or candidate >= current:
            by_norm[norm] = r
    return by_norm


def search_record(site, sq, by_norm=None):
    """读取站点质检记录；同 key 但 API 已变化时绝不复用旧结论。"""
    sq = sq or {}
    norm = api_norm(site)
    direct = sq.get(site.get("key"))
    if isinstance(direct, dict) and direct.get("api"):
        if api_norm({"api": direct["api"]}) == norm:
            return direct
    if by_norm is None:
        by_norm = index_search_quality(sq)
    return by_norm.get(norm)


def apply_search_quality(sites, sq, block_hosts=()):
    """按实测结果处置站点。

    聚合搜索会把所有 searchable 的站点并发发出去，配置层面只有三种处置：
      · 接口返回 HTML/脚本的站，客户端搜一百次也是空 → searchable=0
      · 不认 wd、回整库列表的站，用户看到「搜什么都一堆不相关」→ searchable=0
      · 相关性差但还能用的站 → quickSearch=0（不进首页快速搜索，完整搜索保留）

    成人内容站直接剔除，并按域名记住，避免上游换个 key 又回来。
    匹配口径：key 精确匹配 → API 归一化匹配（覆盖同后端的其他入口）。
    """
    by_norm = index_search_quality(sq)

    def rec_of(site):
        return search_record(site, sq, by_norm)

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
    """读取历史探活；旧格式可读取，但 merge_alive 会淘汰无 API 的不可信记录。"""
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
    两次构建之间来回跳；七天内成功过一次就继续算可用。记录必须带 api，
    否则上游同 key 换接口后会把旧站的速度与分类错套到新站。
    """
    now = int(time.time())
    # 2026-11 之前的缓存没有 api，无法证明它仍对应当前站点，主动淘汰。
    hist = {k: v for k, v in hist.items()
            if isinstance(v, dict) and v.get("api")}
    for k, rec in now_info.items():
        if rec.get("code") == "ok" and rec.get("api"):
            hist[k] = {"ts": now, "ms": rec.get("ms"),
                       "code": "ok", "cls": rec.get("cls") or [],
                       "api": rec["api"]}
    ttl = int(ttl_days) * 86400
    hist = {k: v for k, v in hist.items()
            if now - int(v.get("ts", 0)) <= ttl}
    return hist, hist


def current_alive(sites, records):
    """只返回与当前 API 匹配的探活，并让同后端别名共享分类与速度。

    denied 是本轮明确拒绝，优先于历史 ok；历史记录本身不会持久化 denied。
    """
    by_api = {}
    for rec in (records or {}).values():
        if not isinstance(rec, dict) or not rec.get("api"):
            continue
        norm = rec["api"]
        old = by_api.get(norm)
        rank = (1 if rec.get("code") == "denied" else 0, int(rec.get("ts") or 0))
        old_rank = ((1 if (old or {}).get("code") == "denied" else 0),
                    int((old or {}).get("ts") or 0))
        if old is None or rank >= old_rank:
            by_api[norm] = rec
    out = {}
    for s in sites:
        norm = api_norm(s)
        rec = (records or {}).get(s.get("key"))
        if not isinstance(rec, dict) or rec.get("api") != norm:
            rec = by_api.get(norm)
        if isinstance(rec, dict) and rec.get("api") == norm:
            out[s["key"]] = rec
    return out


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
    # 电影/剧集仍是主体；动漫是独立内容库，不能只用综合采集站里的「动漫片」
    # 分类凑数。72 站目标：影视约 31、动漫 12、4K 10，其余类目保留代表。
    "电影剧集": 0.40,
    "4K蓝光":   0.14,
    "动漫":     0.17,
    "短剧":     0.08,
    "少儿":     0.04,
    "音乐MV":   0.04,
    "戏曲":     0.03,
    "综艺":     0.02,
    "纪录片":   0.02,
    "其他":     0.04,
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
        # 「方舟丨动漫」剥掉噪音词后会剩下尾部的分隔符，精选里显示成「动漫·方舟丨」
        # 很像 bug；品牌本身不该以符号收尾。
        brand = "".join(toks[:2]).strip(" 丨|/\\-—_、,，.·")
        if brand:
            return brand[:8], True
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
    """HTTP 站的资源库身份：规范化主机 + 接口路径 + 业务参数。

    旧版只保留域名，会把 cf.example/wsy 与 cf.example/77 两个不同库误并；
    现在仍剥离 www/api/cj 等功能子域，但保留路径，并统一 from/at 线路变体。
    """
    api = str(site.get("api") or "").split(";")[0].strip()
    if not api.startswith("http"):
        return api
    norm = api_norm(site)
    try:
        p = urllib.parse.urlsplit("//" + norm)
    except Exception:  # noqa: BLE001
        return norm
    host = p.netloc
    for pre in ("www.", "api.", "cj.", "cms.", "vod.", "zy.", "m.", "app.", "play."):
        if host.startswith(pre):
            host = host[len(pre):]
            break
    return host + p.path + (("?" + p.query) if p.query else "")


def lib_of(site):
    """资源库身份。csp_/py_ 必须比较完整 ext，而不是只看类名或前缀。

    XBPQ/XYQHiker 的大量动漫站共用相同 JSON 开头，旧版截取前 120 字符会把
    后半段才出现不同主页 URL 的站误并。这里对完整配置做稳定哈希，既避免误并，
    也不会把数千字符的 XBPQ 规则塞进内存索引键。
    """
    api = str(site.get("api") or "")
    if api.startswith(("csp_", "py_")):
        ext = site.get("ext")
        if isinstance(ext, (dict, list)):
            text = json.dumps(ext, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        else:
            text = urllib.parse.unquote(str(ext or "").strip())
            if text.startswith(("{", "[")):
                try:
                    text = json.dumps(json.loads(text), ensure_ascii=False,
                                      sort_keys=True, separators=(",", ":"))
                except (ValueError, TypeError):
                    pass
            elif text.startswith("http"):
                text = unwrap_mirror(text)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:20] if text else ""
        return "%s|%s" % (api, digest)
    return lib_key(site)


def lite_name(cat, brand):
    return "%s·%s" % (CAT_PREFIX.get(cat, cat), brand)


def pick_lite(sites, size, per_source=5, bucket_of=None, alive=None,
              quota=None, tags=None, sq=None, pin=(), rh=None, ph=None):
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
    所以再用「搜索结果指纹」兜一层：指纹相同的只留一个入口。

    rh 是 rules 体检结果。连续两轮判死的规则站直接不参与精选——分数已经很低，
    但类目配额会把它「保回来」（每个类目至少 1 个），那样等于精选里留个空壳。

    ph 是播放链路体检结果。接口通但播不了的站（首集是网盘分享页、URL 带未编码
    中文）同样不进精选：用户点开就是闪退，这比「搜不到」更伤体验。"""
    alive = alive or {}
    quota = quota or CATEGORY_QUOTA
    bucket_of = bucket_of or {}
    tags = tags or set()
    sq = sq or {}
    rh = rh or {}
    ph = ph or {}
    sq_by_norm = index_search_quality(sq)
    order = {id(s): i for i, s in enumerate(sites)}

    def top_of(s):
        sid = s["key"].split("_")[0]
        return bucket_of.get(sid, sid)

    def search_sig(site):
        """同关键词下返回完全相同的标题集合 → 同一个内容库的不同外壳。"""
        r = search_record(site, sq, sq_by_norm)
        if not r:
            return None
        t = r.get("titles1") or []
        if len(t) < 5:
            return None
        return hashlib.md5("\n".join(sorted(t)).encode("utf-8")).hexdigest()[:12]

    seen_b, cand = set(), []
    n_rdead = n_pbad = 0
    for s in sites:
        if rule_dead(s, rh):
            n_rdead += 1
            continue
        if play_bad(s, ph, for_lite=True):
            n_pbad += 1
            continue
        try:
            cat = site_category(s, alive)
            brand, named = brand_of(s, tags)
        except Exception:  # noqa: BLE001 —— 脏站名只该丢这一个站
            continue
        if named:
            # 同名只在一个类目内去重。旧版全局按品牌丢弃，会把「小米电影」
            # 与「小米动漫」等不同内容库互相挤掉，造成类目覆盖缺失。
            brand_key = (cat, brand.lower())
            if brand_key in seen_b:
                continue
            seen_b.add(brand_key)
        cand.append({"site": s, "cat": cat, "brand": brand,
                     "named": named, "top": top_of(s),
                     "sig": search_sig(s)})

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
            if not relax_src:
                if not relax_cat and filled.get(c["cat"], 0) >= caps[c["cat"]]:
                    continue
                if relax_cat and filled.get(c["cat"], 0) >= caps[c["cat"]] + 2:
                    continue
                if c["cat"] not in NICHE_CATS and used.get(c["top"], 0) >= per_source:
                    continue
            if not c["named"] and any(x["cat"] == c["cat"] and x["named"] for x in group):
                continue
            if relax_cat and not relax_src and not c["named"]:
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
            if lib not in seen_lib:
                # 最后一档也不能绕过搜索指纹与系列限制，更不能漏记类目计数。
                take(group, lib, relax_cat=True, relax_src=True)

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

    # 首页源：不能只看分类数量。优先同时覆盖电影、电视剧、动漫，且搜索
    # 实测合格、CMS 当前可访问的综合库；jar 站无这些离线数据时不奖惩。
    def home_rank(c):
        rec = alive.get(c["site"].get("key")) or {}
        cls = " ".join(str(x) for x in (rec.get("cls") or []))
        core = sum(any(w in cls for w in words) for words in (
            ("电影", "电影片"), ("电视剧", "连续剧", "剧集"),
            ("动漫", "动画")))
        sr = search_record(c["site"], sq, sq_by_norm) or {}
        hit = sr.get("hit_rate")
        search_good = (sr.get("action") == "keep" and
                       sr.get("verdict") in ("good", "ok") and
                       isinstance(hit, (int, float)) and hit >= 0.70)
        return (core == 3, search_good, rec.get("code") == "ok",
                core, breadth(c), -order[id(c["site"])])

    head = None
    film = [c for c in out if c["cat"] == "电影剧集"]
    if film:
        head = max(film, key=home_rank)
        out.remove(head)

    ordered = ([head] if head else []) + sorted(
        out, key=lambda c: (CAT_ORDER.index(c["cat"]), order[id(c["site"])]))

    result = []
    for c in ordered[:size]:
        t = dict(c["site"])
        t["name"] = lite_name(c["cat"], c["brand"])
        result.append(t)
    if n_rdead:
        print("[lite] 跳过 %d 个连续两轮判死的规则站" % n_rdead)
    if n_pbad:
        print("[lite] 跳过 %d 个播放链路不可用的站" % n_pbad)
    return result


def rank_sites(sites, prio_map, consensus, dead, alive=None, sq=None, rh=None, ph=None):
    """按质量分降序，同分按源优先级、再按名称，保证每次构建顺序一致。"""
    alive = alive or {}
    sq = sq or {}
    rh = rh or {}
    ph = ph or {}
    sq_by_norm = index_search_quality(sq)
    scored = []
    for s in sites:
        sid = s["key"].split("_")[0]
        prio = prio_map.get(sid, 100)
        probe = alive.get(s["key"])
        search = search_record(s, sq, sq_by_norm)
        score, why = quality_score(s, prio, consensus.get(fingerprint(s), 1),
                                   is_dead(s, dead), s["key"] in alive, probe, search,
                                   rule_record(s, rh), play_record(s, ph))
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
            sum(len(site_list(g["cfg"])) for g in subs), cost,
            "ok" if subs else (got[0].get("error", "empty") if got else "empty")[:60]))

    # 预展开：一次绝对化，同时统计「同一后端被几个源收录」
    prio_map = {src["id"].replace("-", ""): src.get("priority", 100) for src in sources}
    consensus = {}
    for src in ok:
        src["_abs"] = deep_abs(src["cfg"], src["base"])
        for site in site_list(src["_abs"]):
            fp = fingerprint(site)
            consensus[fp] = consensus.get(fp, 0) + 1

    # 单仓快照 + 收集合并素材
    snapshots = []
    used_keys, seen_fp = set(), set()
    stats = {"dup": 0, "skip_no_api": 0, "skip_no_jar": 0, "skip_bad_site": 0}
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
            raw_sites = site_list(cfg)
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
        for site in site_list(cfg):
            built = build_site(site, src, used_keys, seen_fp, stats, bconf)
            if built:
                merged_sites.append(built)

        all_parses.extend(as_list(cfg.get("parses")))
        all_lives.extend(as_list(cfg.get("lives")))
        all_flags.extend(as_list(cfg.get("flags")))
        all_ads.extend(as_list(cfg.get("ads")))
        src["n_sites"] = len(site_list(cfg))
        src["n_new"] = len(merged_sites) - before

    # 人工下架：域名已注销 / 规则彻底不可用的站，没必要靠两轮体检才沉下去。
    # 放在探活之前，省掉对死站的无谓请求。
    retire = {str(k) for k in (bconf.get("retire_keys") or ())}
    if retire:
        kept = [s for s in merged_sites if s["key"] not in retire]
        if len(kept) != len(merged_sites):
            print("[retire] 按 sources.json 下架 %d 个站点：%s" % (
                len(merged_sites) - len(kept),
                "、".join(s["key"] for s in merged_sites if s["key"] in retire)))
        merged_sites = kept

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
            alive = current_alive(merged_sites, alive)
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

    # 规则站（jar/drpy）体检：连续两轮判死的移出聚合搜索
    rh = load_rule_health()
    if rh:
        n_rdead = apply_rule_health(merged_sites, rh)
        cnt_r = {}
        for s in merged_sites:
            r = rule_record(s, rh)
            if r:
                cnt_r[r.get("level")] = cnt_r.get(r.get("level"), 0) + 1
        print("[rules] 体检命中 %d 站（%s），其中 %d 个硬失效已移出聚合搜索"
              % (sum(cnt_r.values()),
                 " / ".join("%s %d" % (k, v) for k, v in sorted(cnt_r.items())),
                 n_rdead))

    # 播放链路体检：接口通但播不了的站（网盘分享页 / 未编码中文 / 分片 404）
    # 同样移出聚合搜索。用户能搜到却点开闪退，比搜不到更伤体验。
    ph = load_play_health()
    if ph:
        n_pbad = apply_play_health(merged_sites, ph)
        cnt_p = {}
        for s in merged_sites:
            r = play_record(s, ph)
            if r:
                cnt_p[r.get("verdict")] = cnt_p.get(r.get("verdict"), 0) + 1
        print("[play] 体检命中 %d 站（%s），其中 %d 个播放不可用已移出聚合搜索"
              % (sum(cnt_p.values()),
                 " / ".join("%s %d" % (k, v) for k, v in sorted(cnt_p.items())),
                 n_pbad))

    # 质量排序：首页取第一个站点，站点列表与搜索也按这个顺序
    ranked = rank_sites(merged_sites, prio_map, consensus, dead, alive, sq, rh, ph)
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
                           bucket_of, alive, tags=tags, sq=sq, rh=rh, ph=ph,
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
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
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

    print("\n[done] 合并站点 %d / 解析 %d / 直播 %d，去重 %d，跳过(无api) %d，跳过(无jar) %d，跳过(坏站点) %d" % (
        len(merged_sites), len(merged["parses"]), len(merged.get("lives") or []),
        stats["dup"], stats["skip_no_api"], stats["skip_no_jar"], stats["skip_bad_site"]))
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
        lines.append("排序口径：接口类型 + jar 成本 + 跨源收录 + CMS 探活/速度 + 搜索实测 "
                     "− 工具类站点 − 搜索杂乱 − 爬虫失效，同分按源优先级。首页另需三类覆盖。")
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
