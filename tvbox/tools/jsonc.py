# -*- coding: utf-8 -*-
"""JSONC / 宽松 JSON 解析：去 BOM、注释、尾逗号；支持 base64 包裹"""
import json
import re
import base64

_B64_PREFIX = re.compile(r"^[A-Za-z0-9]{8}\*\*")


def strip_jsonc(s):
    s = s.lstrip("\ufeff").strip()
    out, i, n = [], 0, len(s)
    in_str = esc = False
    while i < n:
        c = s[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "#":
            # 有些配置把人读的 Markdown 标题也留在文件里（`## json`、`## 切片`），
            # 只对「行首（允许前导空白）」的 # 生效，避免误伤引号外的颜色值
            j = i - 1
            while j >= 0 and s[j] in " \t":
                j -= 1
            if j < 0 or s[j] in "\r\n":
                while i < n and s[i] not in "\r\n":
                    i += 1
                continue
        if c == "/" and i + 1 < n and s[i + 1] == "/":
            while i < n and s[i] not in "\r\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and s[i + 1] == "*":
            i += 2
            while i + 1 < n and not (s[i] == "*" and s[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    t = "".join(out)
    t = re.sub(r",(\s*[}\]])", r"\1", t)
    return t


def try_base64(s):
    """FongMi Decoder 约定：8 位字母数字 + ** 前缀，其后为 base64"""
    m = _B64_PREFIX.match(s.strip())
    if not m:
        return None
    body = s.strip()[m.end():]
    try:
        raw = base64.b64decode(body + "=" * (-len(body) % 4))
    except Exception:
        return None
    try:
        return raw.decode("utf-8")
    except Exception:
        return None


_CBC_RE = re.compile(r"^2423[0-9a-fA-F]{200,}$")


def _pad16(s):
    return (s + "0" * 16)[:16]


def try_cbc(text):
    """对齐 FongMi Decoder.cbc()：hex 体以 2423 开头，末尾 26 位为 iv，
    头部 $#...#$ 之间为 key。缺 cryptography 时静默跳过。"""
    s = re.sub(r"\s+", "", text.strip())
    if not _CBC_RE.match(s):
        return None
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:
        raise RuntimeError("该源为 AES-CBC 加密配置，需要 pip install cryptography")
    marker = s.find("2324")
    if marker < 0:
        return None
    head, body_hex, tail = s[:marker], s[marker + 4:len(s) - 26], s[len(s) - 26:]
    k_at = head.find("2423")
    if k_at < 0:
        return None
    try:
        key = _pad16(bytes.fromhex(head[k_at + 4:]).decode("utf-8", "ignore").lower()).encode()
        iv = _pad16(bytes.fromhex(tail).decode("utf-8", "ignore").lower()).encode()
        dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        plain = dec.update(bytes.fromhex(body_hex)) + dec.finalize()
    except Exception:
        return None
    if plain and 1 <= plain[-1] <= 16:
        plain = plain[:-plain[-1]]
    try:
        return plain.decode("utf-8")
    except Exception:
        return None


def fix_bad_escape(s):
    """把 JSON 字符串里的非法转义降级为字面量。

    国内配置常从 JS 里拷字符串，带 `\\'` 这种 JSON 不认的转义（合法转义只有
    `" \\ / b f n r t u`）。`\\'` 在 JSON 里就该写成 `'`，去掉反斜杠即可；
    `\\\\'`（反斜杠+引号）是合法的，不能被误改，所以要按状态机逐字符走。
    """
    out, i, n = [], 0, len(s)
    in_str = False
    while i < n:
        c = s[i]
        if not in_str:
            if c == '"':
                in_str = True
            out.append(c)
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            nxt = s[i + 1]
            if nxt == "'":          # \\' -> '
                out.append("'")
                i += 2
                continue
            out.append(c)
            out.append(nxt)
            i += 2
            continue
        if c == '"':
            in_str = False
        out.append(c)
        i += 1
    return "".join(out)


def _loads_tolerant(body):
    """容忍两类国内配置常见脏数据：
    1. 字符串里带原生换行/制表符（json.loads 默认 strict=True 会报 invalid control character）
    2. JSON 后面跟一段 HTML/广告尾巴（Extra data），只取第一个 JSON 值
    """
    try:
        return json.loads(body, strict=False)
    except Exception:
        pass
    try:
        return json.JSONDecoder(strict=False).raw_decode(body.lstrip())[0]
    except Exception:
        return None


def parse_cfg(text):
    """返回 dict。抛出 ValueError 表示无法解析"""
    text = text.strip()
    if not text:
        raise ValueError("empty body")
    for candidate in (text, try_base64(text), try_cbc(text)):
        if not candidate:
            continue
        for body in (candidate, strip_jsonc(candidate)):
            obj = _loads_tolerant(body)
            if isinstance(obj, (dict, list)):
                return obj
            # 最后一档：注释/尾逗号都清过还失败，多半是从 JS 拷来的非法转义
            fixed = fix_bad_escape(body)
            if fixed != body:
                obj = _loads_tolerant(fixed)
                if isinstance(obj, (dict, list)):
                    return obj
    # 报错片段要能安全写进 report.md：非可打印字符（NUL、控制符、二进制）一律折成 "."
    raw = text[:100].replace("\n", " ").replace("\r", " ")
    head = "".join(ch if ch.isprintable() else "." for ch in raw)
    kind = "（返回的是图片/二进制，不是配置）" if (
        text[:3] == "\xff\xd8\xff" or text[:3] in ("GIF", "\x89PN") or "<html" in text[:200].lower()
    ) else ""
    raise ValueError("not json%s | head=%s" % (kind, head))
