# -*- coding: utf-8 -*-
"""播放侧体检：判定一个站"点进去能不能播"，而不是"接口能不能通"。

`probe_rules.py` 解决的是规则站能不能开；这个脚本解决采集站（HTTP CMS）的
播放链路：搜索 → 详情 → 首集地址 → HLS 清单 → 首个分片。

之所以需要单独一层，是因为实测里大量"接口 200、搜索有结果、点开就退"的站，
问题都出在最后一跳：

  · share_page    首集是网盘分享页（vip.xxx.com/share/...），返回 HTML 不是 m3u8，
                  播放器拿到一坨 HTML → 解码器初始化失败 → 直接退出
  · bad_url       首集 URL 含未编码的中文（/第01集/index.m3u8），客户端拼 URL 时
                  OkHttp 抛 IllegalArgumentException，多数客户端不捕获 → 闪退
  · dead_link     清单 404 / 502，或被限流的非常规端口不通
  · bad_segment   清单正常但分片 404 —— 表现为"能播几秒然后卡死/闪退"
  · live_format   接口返回 {"class":[...]}，那是直播源格式，放进点播站必然解析异常
  · python_spider type=3 的 .py 爬虫，需要客户端支持 Python，脚本异常会拖崩进程

判决口径：前三类与 live_format 算硬伤（客户端无法自愈），bad_segment 亦然；
python_spider 只提示不判死（支持 py 的客户端能正常用）；无法探测的记 unverifiable。

用法：
    python tools/probe_play.py                 # 只测 api/lite.json
    python tools/probe_play.py --all --limit 200
    python tools/probe_play.py --write         # 写 play_health.json
"""
import argparse
import collections
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36"
TIMEOUT = 12
# 保留这些字符不转义：它们出现在 CMS 返回的播放地址里是常态，转义反而取不到
SAFE = ":/?=&%#[]!$'()*,;@~+"

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
# 显式空 ProxyHandler：会话注入的 HTTP_PROXY 会让本地探测全部失败
_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=_CTX),
)

# 网盘/分享页域名特征：这些链接必须走客户端内置的网盘解析，当直链播必然失败
SHARE_RE = re.compile(
    r"(?:^|\.)(?:[a-z0-9-]*(?:pan|drive|share|cloud)[a-z0-9-]*)\.|"
    r"aliyundrive|alipan|quark|uc\.cn|123pan|115\.com|pikpak|baidu\.com/s/",
    re.I,
)
NETDISK_HINT = re.compile(r"/(?:share|s)/[0-9a-f]{8,}", re.I)


def http(url, timeout=TIMEOUT, headers=None, limit=6_000_000):
    """返回 (状态码或异常名, body)。异常不抛出，交给调用方判定。"""
    hd = {"User-Agent": UA}
    hd.update(headers or {})
    try:
        req = urllib.request.Request(urllib.parse.quote(url, safe=SAFE), headers=hd)
        with _OPENER.open(req, timeout=timeout) as r:
            return r.status, r.read(limit)
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:  # noqa: BLE001
        return type(e).__name__, b""


def kind_of(site):
    api = str(site.get("api") or "")
    if api.startswith(("csp_", "py_")):
        return "rule"
    if re.search(r"\.py(?:$|\?)", api):
        return "py"
    if api.startswith("http") and api.split("?")[0].endswith((".js", ".min.js")):
        return "drpy"
    return "cms"


def with_query(api, extra):
    return api + ("&" if "?" in api else "?") + extra


def json_body(body):
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError):
        return None


def line_episodes(play_url, per_line=1):
    """按线路取分集地址，每条线路取前 per_line 个。

    格式：线路1$第01集$url#第02集$url$$$线路2$...
    只测第一条线路会误判——实测「非凡」首线路是网盘分享页、备用线路才是 m3u8。
    """
    text = play_url if isinstance(play_url, str) else ""
    if isinstance(play_url, list):
        text = "$$$".join(x for x in play_url if isinstance(x, str))
    out = []
    for line in text.split("$$$"):
        urls = []
        for ep in line.split("#"):
            if "$" not in ep:
                continue
            url = ep.split("$", 1)[1].strip()
            if url:
                urls.append(url)
            if len(urls) >= per_line:
                break
        if urls:
            out.append(urls)
    return out


def probe(site, keyword="庆余年"):
    r = {
        "key": site.get("key"),
        "name": site.get("name"),
        "api": site.get("api"),
        "kind": kind_of(site),
        "verdict": "unverifiable",
        "why": "",
        "first_url": "",
        "codec": "",
        "codec_unsafe": False,
        "requires_referer": False,
        "playlists_checked": 0,
        "segments_total": 0,
        "segments_checked": 0,
        "bytes_checked": 0,
        "tested_at": int(time.time()),
        "ms": None,
    }
    api = str(site.get("api") or "").split(";")[0]
    if r["kind"] != "cms":
        # 规则站/JS 站的播放靠客户端跑 jar/JS，离线无法判定
        r["verdict"] = "python_spider" if r["kind"] == "py" else "rule_based"
        r["why"] = "解析在客户端执行" if r["kind"] != "py" else "需要客户端支持 Python 爬虫"
        return r

    t0 = time.time()
    st, body = http(with_query(api, "ac=videolist&wd=" + urllib.parse.quote(keyword)))
    if st != 200:
        r["verdict"], r["why"] = "search_fail", "搜索 HTTP %s" % st
        return r
    data = json_body(body)
    if data is None:
        head = body[:80].decode("utf-8", "replace").strip()
        if "<rss" in head or "<?xml" in head:
            r["verdict"], r["why"] = "xml_endpoint", "接口返回 XML（/at/xml），非 JSON"
        else:
            r["verdict"], r["why"] = "search_bad", "搜索响应非 JSON：%s" % head[:40]
        return r
    if "class" in data and "list" not in data:
        r["verdict"], r["why"] = "live_format", "返回直播格式 {\"class\":...}，不是点播接口"
        return r
    lst = data.get("list")
    if not isinstance(lst, list) or not lst:
        r["verdict"], r["why"] = "no_result", "搜索无结果"
        return r

    vid = lst[0].get("vod_id")
    st, body = http(with_query(api, "ac=detail&ids=" + urllib.parse.quote(str(vid))), timeout=15)
    if st != 200:
        r["verdict"], r["why"] = "detail_fail", "详情 HTTP %s" % st
        return r
    data = json_body(body) or {}
    detail = (data.get("list") or [{}])[0]
    lines = line_episodes(detail.get("vod_play_url"))
    if not lines:
        r["verdict"], r["why"] = "no_episode", "详情无可用分集地址"
        return r

    # 逐线路试：只要有一条线路能取到真实视频流，这个站就能播。
    # 但「默认线路（第一条）失败、备用线路可用」必须单独记：客户端默认播第一条，
    # 实测非凡/量子的第一条是网盘分享页，点开必然黑屏或闪退，用户不会每次都切线路。
    first_fail = None
    for i, urls in enumerate(lines[:3]):
        url = urls[0]
        r["first_url"] = url[:200]
        verdict, why = check_stream(url, r)
        if verdict in ("ok", "direct"):
            if i == 0:
                r["verdict"], r["why"] = verdict, why or ""
            else:
                r["verdict"] = "ok_secondary"
                r["why"] = "默认线路不可用（%s），切到第 %d 条线路才能播" % (
                    first_fail[1] if first_fail else "-", i + 1)
            r["ms"] = int((time.time() - t0) * 1000)
            return r
        if first_fail is None:
            first_fail = (url, verdict, why)
    url, verdict, why = first_fail
    r["first_url"] = url[:200]
    r["verdict"], r["why"] = verdict, why
    if len(lines) > 1:
        r["why"] = "%s（%d 条线路全部失败）" % (why, min(len(lines), 3))
    return r


DNS_BAD_IP = ("0.0.0.0", "127.", "::", "0:0:0:0:0:0:0:0")


def _doh(host):
    """返回 (Status, [有效A记录])。国内解析影视站常被投毒，必须走 DoH 复核。"""
    for base in ("https://dns.alidns.com/resolve", "https://doh.pub/dns-query"):
        try:
            q = "%s?name=%s&type=A" % (base, urllib.parse.quote(host))
            req = urllib.request.Request(q, headers={
                "accept": "application/dns-json", "User-Agent": "curl/8"})
            with _OPENER.open(req, timeout=8) as r:
                j = json.loads(r.read().decode("utf-8", "replace"))
            ips = [a.get("data") for a in (j.get("Answer") or [])
                   if a.get("type") in (1, 5) and a.get("data")]
            ips = [i for i in ips if not str(i).startswith(DNS_BAD_IP)]
            if ips:
                return j.get("Status"), ips
            status = j.get("Status")
        except Exception:  # noqa: BLE001
            status = "ERR"
    return status, []


def refine_dns(results):
    """把「搜索不通」拆成真死和本机被拦两种，后者不能杀站。

    实测 10 个 search_fail 的精选站里，4 个是 NXDOMAIN（真死），
    3 个 DoH 有正常 A 记录（本机 DNS 被投毒，站还活着），其余是空解析。
    """
    todo = [r for r in results if r["verdict"] in ("search_fail", "dead_link", "no_result")
            and str(r.get("api") or "").startswith("http")]
    hosts = []
    for r in todo:
        host = urllib.parse.urlsplit(str(r["api"]).split(";")[0]).netloc.split(":")[0]
        if host:
            hosts.append((r, host))
    cache = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {h: ex.submit(_doh, h) for _, h in hosts}
        for h, f in futs.items():
            cache[h] = f.result()
    for r, host in hosts:
        status, ips = cache.get(host, (None, []))
        r["doh_status"] = status
        r["doh_ips"] = ips[:2]
        if not ips and status in (2, 3):
            r["verdict"] = "dns_dead"
            r["why"] = "DoH 无 A 记录（Status %s），域名已失效" % status
        elif ips:
            r["why"] = (r["why"] + "；DoH 有 A 记录，属本机 DNS 被拦").strip("；")


UNSUPPORTED_CODEC_RE = re.compile(r"hvc1|hev1|av01|vp09", re.I)


def _looks_like_text(body):
    """媒体地址返回 JSON/XML/文本时，不能当作直链视频放行。"""
    head = body[:600].lstrip().lower()
    if (head.startswith((b"<html", b"<!doctype", b"<?xml", b"<head", b"<meta",
                         b"<body", b"<script", b"<title")) or
            b"<html" in head or b"<head" in head):
        return True
    if b"not found" in head[:120]:
        return True
    if head.startswith((b"{", b"[")):
        # 加密分片是随机字节，不能仅凭首字节 {/[ 就误判成 JSON。
        try:
            body[:4096].decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False
    return False


def _ts_stream_types(body):
    """读取 MPEG-TS PAT/PMT 的流类型；加密或非标分片返回空集合。"""
    if len(body) < 188 or body[0] != 0x47:
        return set()

    def payload(packet):
        if len(packet) != 188 or packet[0] != 0x47:
            return None
        off = 4
        if packet[3] & 0x20:
            off += 1 + packet[4]
        if off >= 188 or not (packet[1] & 0x40):
            return None
        pointer = packet[off]
        return packet[off + 1 + pointer:]

    packets = [body[i:i + 188] for i in range(0, len(body) - 187, 188)]
    pmt_pid = None
    for packet in packets:
        pid = ((packet[1] & 0x1F) << 8) | packet[2]
        if pid != 0:
            continue
        sec = payload(packet)
        if not sec or len(sec) < 12 or sec[0] != 0:
            continue
        end = min(len(sec), 3 + (((sec[1] & 0x0F) << 8) | sec[2]) - 4)
        for i in range(8, end - 3, 4):
            if sec[i:i + 2] != b"\0\0":
                pmt_pid = ((sec[i + 2] & 0x1F) << 8) | sec[i + 3]
                break
        if pmt_pid is not None:
            break
    if pmt_pid is None:
        return set()
    for packet in packets:
        pid = ((packet[1] & 0x1F) << 8) | packet[2]
        if pid != pmt_pid:
            continue
        sec = payload(packet)
        if not sec or len(sec) < 16 or sec[0] != 2:
            continue
        end = min(len(sec), 3 + (((sec[1] & 0x0F) << 8) | sec[2]) - 4)
        info_len = ((sec[10] & 0x0F) << 8) | sec[11]
        i, types = 12 + info_len, set()
        while i + 5 <= end:
            types.add(sec[i])
            i += 5 + (((sec[i + 3] & 0x0F) << 8) | sec[i + 4])
        return types
    return set()


def _has_media_signature(body):
    """小体积直链必须有明确媒体头，避免把播放器网页/初始化碎片当视频。"""
    return (body[:3] == b"FLV" or body[:4] == b"ID3" or
            body[:4] == b"\x1aE\xdf\xa3" or body[:4] == b"\x00\x00\x01\xba" or
            body[4:8] in (b"ftyp", b"moov", b"mdat", b"styp", b"moof") or
            (body[:4] == b"RIFF" and body[8:12] in (b"AVI ", b"WAVE")) or
            (len(body) >= 376 and body[0] == 0x47 and body[188] == 0x47) or
            (len(body) >= 2 and body[0] == 0xFF and body[1] & 0xE0 == 0xE0))


def _media_codec_unsafe(body):
    """识别 fMP4 与 TS 中仅含 HEVC/AV1 的流，避免老设备硬解闪退。"""
    head = body[:1_000_000]
    if (re.search(rb"hvc1|hev1|av01|vp09", head, re.I) and
            not re.search(rb"avc1|avc3", head, re.I)):
        return True
    types = _ts_stream_types(body)
    return bool(types & {0x24, 0x2D}) and 0x1B not in types


def _fetch_media(url, origin, limit):
    """下载媒体内容；仅在带 Referer 才能成功时标记，稳定版不接受这种源。"""
    st, body = http(url, limit=limit)
    if st in (200, 206):  # 部分 CDN 对末段直接返回 206，属于有效媒体响应
        return st, body, False
    st2, body2 = http(url, headers={"Referer": origin}, limit=limit)
    if st2 in (200, 206):
        return st2, body2, True
    return st, b"", False


def _check_playlist(url, text, r, origin, depth=0):
    """递归验证 master/media 清单，并抽查首、中、尾三个分片。"""
    r["playlists_checked"] += 1
    if depth > 2:
        return "bad_playlist", "清单嵌套超过 2 层"

    # master playlist：必须继续下载变体清单，不能只看到 200 就判可播。
    if "#EXT-X-STREAM-INF" in text.upper():
        variants = []
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not line.upper().startswith("#EXT-X-STREAM-INF"):
                continue
            m = re.search(r'CODECS="([^"]+)"', line, re.I)
            codec = m.group(1) if m else ""
            for nxt in lines[i + 1:]:
                if nxt.strip() and not nxt.startswith("#"):
                    variants.append((nxt.strip(), codec))
                    break
        if not variants:
            return "bad_playlist", "主清单没有变体地址"
        r["codec"] = ",".join(sorted({c for _, c in variants if c}))[:120]
        safe = [v for v in variants if not UNSUPPORTED_CODEC_RE.search(v[1])]
        if not safe:
            r["codec_unsafe"] = True
            return "unsupported_codec", "全部变体均为 HEVC/AV1/VP9，老旧硬解设备可能闪退"
        suburl = urllib.parse.urljoin(url, safe[0][0])
        ss, sb, need_ref = _fetch_media(suburl, origin, 400_000)
        r["requires_referer"] = r["requires_referer"] or need_ref
        if ss not in (200, 206):
            return "bad_segment", "变体子清单 HTTP %s" % ss
        subtext = sb.decode("utf-8", "replace")
        if not subtext.lstrip().startswith("#EXTM3U"):
            return "bad_playlist", "变体地址返回的不是 M3U8 清单"
        return _check_playlist(suburl, subtext, r, origin, depth + 1)

    codecs = re.findall(r'CODECS="([^"]+)"', text, re.I)
    if codecs:
        r["codec"] = ",".join(codecs)[:120]
        if all(UNSUPPORTED_CODEC_RE.search(c) for c in codecs):
            r["codec_unsafe"] = True
            return "unsupported_codec", "码流为 HEVC/AV1/VP9，老旧硬解设备可能闪退"

    # 所有不同密钥与 fMP4 初始化分片都必须可取；只验第一把密钥会漏掉后续加密段。
    key_urls = []
    for pattern in (r'#EXT-X-KEY:[^\n]*URI="([^"]+)"',
                    r'#EXT-X-MAP:[^\n]*URI="([^"]+)"'):
        for uri in re.findall(pattern, text, re.I):
            full = urllib.parse.urljoin(url, uri.strip())
            if full not in key_urls:
                key_urls.append(full)
    for aux in key_urls[:4]:
        ks, kb, need_ref = _fetch_media(aux, origin, 16_384)
        r["requires_referer"] = r["requires_referer"] or need_ref
        if ks not in (200, 206) or not kb or _looks_like_text(kb):
            return "bad_segment", "密钥/初始化分片不可用（HTTP %s）" % ks

    segs = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if not segs:
        return "bad_playlist", "媒体清单没有分片地址"
    r["segments_total"] = len(segs)
    indexes = list(dict.fromkeys((0, len(segs) // 2, len(segs) - 1)))
    for idx in indexes:
        seg = urllib.parse.urljoin(url, segs[idx])
        ss, sb, need_ref = _fetch_media(seg, origin, 2_000_000)
        r["requires_referer"] = r["requires_referer"] or need_ref
        if ss not in (200, 206):
            return "bad_segment", "第 %d/%d 个抽检分片 HTTP %s" % (idx + 1, len(segs), ss)
        if len(sb) < 512 or _looks_like_text(sb) or sb[:7] == b"#EXTM3U":
            return "bad_segment", "第 %d/%d 个抽检分片不是有效媒体内容" % (idx + 1, len(segs))
        if idx == 0 and _media_codec_unsafe(sb):
            r["codec_unsafe"] = True
            return "unsupported_codec", "分片仅含 HEVC/AV1，老旧硬解设备可能闪退"
        r["segments_checked"] += 1
        r["bytes_checked"] += len(sb)
    return "ok", "需 Referer，客户端不带会失败" if r["requires_referer"] else ""


def check_stream(url, r):
    """判定单个播放地址能否持续出流，返回 (verdict, why)。"""
    for key, value in (("codec", ""), ("codec_unsafe", False),
                       ("requires_referer", False), ("playlists_checked", 0),
                       ("segments_total", 0), ("segments_checked", 0),
                       ("bytes_checked", 0)):
        r[key] = value
    if not url.isascii():
        return "bad_url", "分集地址含未编码中文，客户端拼 URL 会抛异常"
    if not re.match(r"^https?://", url):
        return "bad_url", "分集地址不是 HTTP"

    host = urllib.parse.urlsplit(url).netloc
    origin = "%s://%s/" % (urllib.parse.urlsplit(url).scheme, host)
    st, body, need_ref = _fetch_media(url, origin, 400_000)
    r["requires_referer"] = need_ref
    if st not in (200, 206):
        return "dead_link", "首集返回 %s（带 Referer 也失败）" % st

    text = body[:400_000].decode("utf-8", "replace")
    if "<html" in text[:600].lower() or "<!doctype" in text[:300].lower():
        is_share = bool(SHARE_RE.search(host) or NETDISK_HINT.search(url))
        return ("share_page" if is_share else "html_link",
                "首集是网页而非视频流（%s）" % ("网盘分享页" if is_share else "HTML 页面"))

    if not text.lstrip().startswith("#EXTM3U"):
        if len(body) < 512 or _looks_like_text(body):
            return "direct_invalid", "直链返回文本/异常内容，不是有效媒体"
        if len(body) < 65_536 and not _has_media_signature(body):
            return "direct_invalid", "小体积直链没有可识别的媒体签名"
        if _media_codec_unsafe(body):
            r["codec_unsafe"] = True
            return "unsupported_codec", "直链仅含 HEVC/AV1，老旧硬解设备可能闪退"
        r["bytes_checked"] = len(body)
        return "direct", "需 Referer，客户端不带会失败" if need_ref else ""
    return _check_playlist(url, text, r, origin)


def main():
    ap = argparse.ArgumentParser(description="采集站播放链路体检")
    ap.add_argument("--input", default=os.path.join(ROOT, "api/lite.json"))
    ap.add_argument("--all", action="store_true", help="用 api/all.json 全量")
    ap.add_argument("--limit", type=int, default=0, help="只测前 N 个（配合 --all 抽样）")
    ap.add_argument("--kw", default="庆余年", help="探测用关键词")
    ap.add_argument("--jobs", type=int, default=10)
    ap.add_argument("--no-doh", action="store_true", help="跳过 DoH 复核（不区分真死与本机被拦）")
    ap.add_argument("--write", action="store_true", help="写 play_health.json")
    a = ap.parse_args()

    path = os.path.join(ROOT, "api/all.json") if a.all else a.input
    name = os.path.basename(path)
    cfg = json.load(open(path, encoding="utf-8"))
    sites = [s for s in (cfg.get("sites") or []) if isinstance(s, dict) and s.get("api")]
    if a.limit:
        sites = sites[:a.limit]
    print("待检 %d 站（%s）" % (len(sites), name), flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        res = list(ex.map(lambda s: probe(s, a.kw), sites))

    if not a.no_doh:
        refine_dns(res)

    cnt = collections.Counter(r["verdict"] for r in res)
    print("\n判决分布：%s  用时 %.0fs" % (dict(cnt), time.time() - t0))

    bad = ("xml_endpoint", "share_page", "bad_url", "live_format", "dead_link",
           "bad_segment", "bad_playlist", "direct_invalid", "unsupported_codec",
           "html_link", "search_bad", "ok_secondary", "dns_dead")
    print("\n%-14s %-7s %-13s %s" % ("站名", "类型", "判决", "说明"))
    for r in sorted(res, key=lambda x: (x["verdict"] not in bad, x["verdict"], str(x["name"]))):
        if r["verdict"] in ("rule_based", "python_spider"):
            continue
        print("%-14s %-7s %-13s %s" % (str(r["name"])[:14], r["kind"], r["verdict"], r["why"][:56]))

    if a.write:
        out = os.path.join(ROOT, "play_health.json")
        prev = {}
        tested = {r["key"] for r in res}
        if os.path.exists(out):
            try:
                old = json.load(open(out, encoding="utf-8"))
                prev = {x["key"]: x for x in old.get("sites") or [] if isinstance(x, dict)}
                # 抽样写盘时保留未测到的旧记录，否则整份文件被样本覆盖
                for k, v in prev.items():
                    if k not in tested:
                        res.append(v)
            except (ValueError, OSError, KeyError):
                prev = {}
        for r in res:
            if r["key"] not in tested:
                continue  # 保留的旧记录未参与本轮，不得累计连续通过/失败轮次
            p = prev.get(r["key"])
            if p and str(p.get("api") or "") != str(r.get("api") or ""):
                p = None  # 同 key 换接口后，旧接口的稳定性证据不得继承
            if p:
                # 连续失败轮次：分享页/死链这种结构性问题不会自己好，两轮即定案
                bad_now = r["verdict"] in bad
                good_now = (r["verdict"] in ("ok", "direct") and
                            not r.get("codec_unsafe") and not r.get("requires_referer"))
                r["bad_streak"] = int(p.get("bad_streak") or 0) + 1 if bad_now else 0
                r["ok_streak"] = int(p.get("ok_streak") or 0) + 1 if good_now else 0
                r["prev_verdict"] = p.get("verdict")
            else:
                r["bad_streak"] = 1 if r["verdict"] in bad else 0
                good_now = (r["verdict"] in ("ok", "direct") and
                            not r.get("codec_unsafe") and not r.get("requires_referer"))
                r["ok_streak"] = 1 if good_now else 0
                r["prev_verdict"] = None
        json.dump({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "tested_at": int(time.time()),
                   "scope": name, "keyword": a.kw,
                   "summary": dict(collections.Counter(r["verdict"] for r in res)),
                   "sites": res},
                  open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        stable = [r for r in res if r["key"] in tested and
                  r.get("verdict") in ("ok", "direct") and
                  int(r.get("ok_streak") or 0) >= 2 and
                  not r.get("requires_referer") and not r.get("codec_unsafe")]
        print("连续两轮播放通过：%d 个候选" % len(stable))
        print("\n已写 %s（%d 条）" % (out, len(res)))


if __name__ == "__main__":
    main()
