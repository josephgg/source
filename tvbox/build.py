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

def _open(url, timeout=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Encoding": "identity",
    })
    return urllib.request.urlopen(req, timeout=timeout or TIMEOUT, context=CTX)


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
                "timeout": item.get("timeout"),
                "note": "",
                "parent": item["id"],
            })
        if children:
            with ThreadPoolExecutor(max_workers=min(8, len(children))) as pool:
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
    return out


def build_parses(all_parses, max_parses):
    by_key = {}
    for p in all_parses:
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

    # 清理上一轮产物，避免已下线源留下孤儿文件
    api_dir = os.path.join(ROOT, "api")
    if os.path.isdir(api_dir):
        for name in os.listdir(api_dir):
            if name.endswith(".json"):
                os.remove(os.path.join(api_dir, name))

    # 各源并行抓取：串行时国内源的超时会累加，CI 上可能要十几分钟
    def fetch_one(src):
        t0 = time.time()
        got = collect_multi(src)
        return src, got, int((time.time() - t0) * 1000)

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(sources)))) as pool:
        pulled = list(pool.map(fetch_one, sources))

    results, ok = [], []
    for src, got, cost in pulled:
        for g in got:
            g["ms"] = cost // max(1, len(got))
            results.append(g)
            if "cfg" in g:
                ok.append(g)
        subs = [g for g in got if "cfg" in g]
        print("[fetch] %-9s 子仓=%-2d 站点=%-4d %sms %s" % (
            src["id"], len(subs),
            sum(len(g["cfg"].get("sites") or []) for g in subs), cost,
            "ok" if subs else (got[0].get("error", "empty") if got else "empty")[:60]))

    # 单仓快照 + 收集合并素材
    snapshots = []
    used_keys, seen_fp = set(), set()
    stats = {"dup": 0, "skip_no_api": 0, "skip_no_jar": 0}
    merged_sites = []
    all_parses, all_lives, all_flags, all_ads = [], [], [], []
    first_wall = first_notice = first_spider = ""

    for src in ok:
        cfg = deep_abs(src["cfg"], src["base"])
        src["spider"] = cfg.get("spider") or ""
        if not first_spider and src["spider"]:
            first_spider = src["spider"]
        if not first_wall and isinstance(cfg.get("wallpaper"), str):
            first_wall = cfg["wallpaper"]
        if not first_notice and isinstance(cfg.get("notice"), str):
            first_notice = cfg["notice"]

        # 单仓快照：保留原 key，仅做绝对化
        if bconf.get("emit_source_repo", True):
            snap = {
                "spider": src.get("spider", ""),
                "wallpaper": cfg.get("wallpaper", ""),
                "logo": cfg.get("logo", ""),
                "notice": cfg.get("notice", ""),
                "sites": cfg.get("sites") or [],
                "parses": cfg.get("parses") or [],
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

    # 网络抖动时宁可保留旧产物，也不要把可用配置覆盖成残废版
    min_ratio = float(bconf.get("min_retain_ratio", 0.85))
    if old_sites and os.environ.get("TVBOX_ALLOW_SHRINK") != "1":
        if len(merged_sites) < old_sites * min_ratio:
            print("[abort] 合并站点 %d 低于上次 %d 的 %.0f%%，判定抓取异常，保留旧产物"
                  % (len(merged_sites), old_sites, min_ratio * 100))
            print("        确认要强制覆盖请设置 TVBOX_ALLOW_SHRINK=1")
            return 1

    for sid, snap in snapshots:
        write_json(os.path.join(ROOT, "api", "src-%s.json" % sid), snap)
    write_json(os.path.join(ROOT, "api", "all.json"), merged)

    # 多仓索引
    index = {"name": meta.get("name", "聚合影视仓"), "urls": []}
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

    # 状态与报告
    status = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "total_sites": len(merged_sites),
        "total_parses": len(merged["parses"]),
        "total_lives": len(merged.get("lives") or []),
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
    write_report(status, merged, sources)

    # 地址清单：手机端按顺序试，主地址用 CDN
    lines = ["# 主地址（jsDelivr CDN，国内相对稳定）"]
    for cdn in meta.get("cdn", []):
        lines.append(cdn + "api/all.json")
    lines += ["", "# 多仓索引（可选，配这个可在 APP 内切换仓库）"]
    for cdn in meta.get("cdn", []):
        lines.append(cdn + "index.json")
    lines += ["", "# 备用（GitHub raw）", raw_base + "api/all.json", raw_base + "index.json"]
    lines += ["", "# 备用（raw + 镜像前缀）"]
    for prefix in meta.get("mirrors", []):
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


def write_report(status, merged, sources):
    lines = []
    lines.append("# 构建报告\n")
    lines.append("生成时间：%s\n" % status["generated_at"])
    lines.append("| 指标 | 数值 |")
    lines.append("| --- | --- |")
    lines.append("| 合并后站点数 | %d |" % status["total_sites"])
    lines.append("| 解析源数量 | %d |" % status["total_parses"])
    lines.append("| 直播源数量 | %d |" % status["total_lives"])
    lines.append("| 跨源去重丢弃 | %d |" % status["stats"]["dup"])
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
    write_text(os.path.join(ROOT, "report.md"), "\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
