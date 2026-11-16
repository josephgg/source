import { CATALOG } from "../data/catalog.js";

const API_PATHS = new Set([
  "/api.php/provide/vod",
  "/api.php/provide/vod/",
  "/vod",
  "/vod/",
]);
const UPSTREAM_TIMEOUT_MS = 7500;
const UPSTREAM_CONCURRENCY = 18;
const RESULT_LIMIT = 30;
const MAX_DETAIL_ROUTES = 8;
const CACHE_SECONDS = 60;
const UA = "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 JoeTV/1.0";

const SHARE_HOST_SUFFIXES = [
  "pan.baidu.com",
  "pan.quark.cn",
  "alipan.com",
  "aliyundrive.com",
  "cloud.189.cn",
  "115.com",
  "123pan.com",
  "pan.xunlei.com",
  "drive.google.com",
  "youtube.com",
  "youtu.be",
  "t.me",
];

function corsHeaders(extra = {}) {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "X-Content-Type-Options": "nosniff",
    ...extra,
  };
}

function jsonResponse(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: corsHeaders({
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=60",
      ...extra,
    }),
  });
}

function emptyResult(msg = "没有找到结果", extra = {}) {
  return {
    code: 0,
    msg,
    page: 1,
    pagecount: 1,
    limit: RESULT_LIMIT,
    total: 0,
    list: [],
    class: visibleClasses(),
    ...extra,
  };
}

function visibleClasses() {
  return (CATALOG.classes || []).filter((c) =>
    (CATALOG.sources || []).some((s) => (s.categories?.[c.type_id] || []).length > 0),
  );
}

function asString(value) {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function cleanText(value) {
  return asString(value)
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/\s+/g, " ")
    .trim();
}

function decodeEntities(value) {
  return asString(value)
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&nbsp;/gi, " ")
    .trim();
}

function xmlTag(block, tag) {
  const m = block.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`, "i"));
  return m ? decodeEntities(m[1]) : "";
}

function xmlToData(text) {
  const videos = [...text.matchAll(/<video>([\s\S]*?)<\/video>/gi)].map((m) => m[1]);
  if (!videos.length) {
    const classes = [...text.matchAll(/<class>([\s\S]*?)<\/class>/gi)].map((m) => {
      const b = m[1];
      return {
        type_id: xmlTag(b, "ty_id") || xmlTag(b, "type_id") || xmlTag(b, "id"),
        type_name: xmlTag(b, "ty") || xmlTag(b, "type_name") || xmlTag(b, "name"),
        type_pid: xmlTag(b, "type_pid") || "0",
      };
    });
    return {
      code: xmlTag(text, "code") || (classes.length ? "1" : "0"),
      msg: xmlTag(text, "msg"),
      class: classes,
      list: [],
    };
  }
  const list = videos.map((block) => {
    const froms = [];
    const urls = [];
    const ddRe = /<dd[^>]*flag=["']([^"']*)["'][^>]*>([\s\S]*?)<\/dd>/gi;
    for (const m of block.matchAll(ddRe)) froms.push(decodeEntities(m[1]));
    const dl = block.match(/<dl[^>]*>([\s\S]*?)<\/dl>/i);
    if (dl) {
      for (const m of dl[1].matchAll(/<dd[^>]*>([\s\S]*?)<\/dd>/gi)) {
        urls.push(decodeEntities(m[1]));
      }
    }
    return {
      vod_id: xmlTag(block, "id") || xmlTag(block, "vod_id"),
      vod_name: xmlTag(block, "name") || xmlTag(block, "vod_name"),
      type_id: xmlTag(block, "tid") || xmlTag(block, "type_id"),
      type_name: xmlTag(block, "type") || xmlTag(block, "type_name"),
      vod_pic: xmlTag(block, "pic") || xmlTag(block, "vod_pic"),
      vod_remarks: xmlTag(block, "note") || xmlTag(block, "vod_remarks"),
      vod_year: xmlTag(block, "year") || xmlTag(block, "vod_year"),
      vod_area: xmlTag(block, "area") || xmlTag(block, "vod_area"),
      vod_lang: xmlTag(block, "lang") || xmlTag(block, "vod_lang"),
      vod_actor: xmlTag(block, "actor") || xmlTag(block, "vod_actor"),
      vod_director: xmlTag(block, "director") || xmlTag(block, "vod_director"),
      vod_content: xmlTag(block, "des") || xmlTag(block, "vod_content"),
      vod_time: xmlTag(block, "last") || xmlTag(block, "vod_time"),
      vod_play_from: froms.join("$$$"),
      vod_play_url: urls.join("$$$"),
    };
  });
  return { code: "1", msg: "ok", list };
}

function parsePayload(text, contentType = "") {
  const clean = asString(text).replace(/^\uFEFF/, "").trim();
  if (!clean) throw new Error("empty response");
  if (/^<!doctype\s+html/i.test(clean) || /^<html/i.test(clean)) {
    throw new Error("upstream returned HTML");
  }
  if (clean[0] === "{" || clean[0] === "[") {
    const data = JSON.parse(clean);
    if (Array.isArray(data)) return { code: "1", list: data };
    return data;
  }
  if (clean[0] === "<") return xmlToData(clean);
  if (/json/i.test(contentType)) return JSON.parse(clean);
  throw new Error("unsupported upstream format");
}

function decodeBody(buffer, contentType) {
  const m = asString(contentType).match(/charset\s*=\s*["']?([\w-]+)/i);
  const charset = (m?.[1] || "utf-8").toLowerCase();
  try {
    return new TextDecoder(charset === "gb2312" ? "gb18030" : charset).decode(buffer);
  } catch {
    return new TextDecoder("utf-8").decode(buffer);
  }
}

function buildUpstreamUrl(api, params) {
  const u = new URL(api);
  for (const key of ["ac", "wd", "ids", "t", "pg", "at"]) u.searchParams.delete(key);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") u.searchParams.set(key, String(value));
  }
  return u.toString();
}

async function fetchUpstream(source, params) {
  const url = buildUpstreamUrl(source.api, { at: "json", ...params });
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);
  const started = Date.now();
  try {
    const res = await fetch(url, {
      headers: {
        "User-Agent": UA,
        Accept: "application/json, text/xml, application/xml, text/plain, */*",
      },
      redirect: "follow",
      signal: controller.signal,
      cf: { cacheTtl: 60, cacheEverything: true },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const buffer = await res.arrayBuffer();
    if (buffer.byteLength > 5 * 1024 * 1024) throw new Error("response too large");
    const text = decodeBody(buffer, res.headers.get("content-type") || "");
    const data = parsePayload(text, res.headers.get("content-type") || "");
    const items = Array.isArray(data?.list)
      ? data.list
      : Array.isArray(data?.data)
        ? data.data
        : Array.isArray(data?.data?.list)
          ? data.data.list
          : [];
    return {
      ok: true,
      source,
      items,
      classes: data?.class || data?.classes || [],
      page: Number(data?.page || params.pg || 1),
      pagecount: Number(data?.pagecount || data?.page_count || 1),
      total: Number(data?.total || items.length),
      elapsed: Date.now() - started,
    };
  } catch (error) {
    return {
      ok: false,
      source,
      items: [],
      classes: [],
      error: error?.name === "AbortError" ? "timeout" : asString(error?.message || error),
      elapsed: Date.now() - started,
    };
  } finally {
    clearTimeout(timer);
  }
}

async function mapLimit(items, limit, worker) {
  const out = new Array(items.length);
  let cursor = 0;
  async function run() {
    while (cursor < items.length) {
      const index = cursor++;
      out[index] = await worker(items[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, run));
  return out;
}

function absolutePic(pic, api) {
  const value = asString(pic).trim();
  if (!value) return "";
  try {
    return new URL(value, api).toString();
  } catch {
    return "";
  }
}

function sourceByIndex(index) {
  return CATALOG.sources[Number(index)] || null;
}

function categoryMatches(typeId, item, allowedIds) {
  if (allowedIds.has(asString(item.typeId))) return true;
  const name = asString(item.typeName);
  if (!name) return false;
  if (typeId === "movie") return /(电影|片)/.test(name) && !/(纪录|记录)/.test(name);
  if (typeId === "tv") return /(电视剧|连续剧|剧集|剧)/.test(name) && !/短剧/.test(name);
  if (typeId === "anime") return /(动漫|动画)/.test(name);
  if (typeId === "variety") return /综艺/.test(name);
  if (typeId === "short") return /短剧/.test(name);
  if (typeId === "documentary") return /(纪录|记录)/.test(name);
  return false;
}

function normalizeItem(raw, source, sourceIndex) {
  if (!raw || typeof raw !== "object") return null;
  const upstreamId = asString(raw.vod_id ?? raw.id).trim();
  const name = cleanText(raw.vod_name ?? raw.name);
  if (!upstreamId || !name) return null;
  return {
    id: upstreamId,
    source,
    sourceIndex,
    name,
    typeId: asString(raw.type_id ?? raw.tid),
    typeName: cleanText(raw.type_name ?? raw.type),
    pic: absolutePic(raw.vod_pic ?? raw.pic, source.api),
    remarks: cleanText(raw.vod_remarks ?? raw.note),
    year: cleanText(raw.vod_year ?? raw.year),
    area: cleanText(raw.vod_area ?? raw.area),
    lang: cleanText(raw.vod_lang ?? raw.lang),
    actor: cleanText(raw.vod_actor ?? raw.actor),
    director: cleanText(raw.vod_director ?? raw.director),
    content: cleanText(raw.vod_content ?? raw.des),
    time: cleanText(raw.vod_time ?? raw.last),
    playFrom: asString(raw.vod_play_from),
    playUrl: asString(raw.vod_play_url),
  };
}

function normalizeTitle(value) {
  return cleanText(value)
    .toLowerCase()
    .replace(/[\s·:：\-—_.,，。!！?？'"“”‘’()[\]【】《》/\\]+/g, "")
    .replace(/第[一二三四五六七八九十\d]+季$/, "");
}

function titleKey(item) {
  // 不同上游经常只有一部分带年份；按名称合并能避免同片重复出现。
  // 真正的同名不同版本仍可由多线路之间的年份信息区分，不丢内容。
  return normalizeTitle(item.name);
}

function scoreTitle(item, keyword) {
  const target = normalizeTitle(keyword);
  const name = normalizeTitle(item.name);
  if (!target) return 0;
  if (name === target) return 100;
  if (name.startsWith(target)) return 70;
  if (name.includes(target)) return 40;
  return 0;
}

function encodeId(routes) {
  const text = routes
    .slice(0, MAX_DETAIL_ROUTES)
    .map((r) => `${r.sourceIndex}:${encodeURIComponent(r.id)}`)
    .join(",");
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return "J" + btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function decodeId(value) {
  const text = asString(value).trim();
  if (!text.startsWith("J")) return [];
  try {
    const b64 = text.slice(1).replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    const decoded = new TextDecoder().decode(bytes);
    return decoded
      .split(",")
      .map((part) => {
        const mark = part.indexOf(":");
        if (mark <= 0) return null;
        return {
          sourceIndex: Number(part.slice(0, mark)),
          id: decodeURIComponent(part.slice(mark + 1)),
        };
      })
      .filter((r) => r && Number.isInteger(r.sourceIndex) && r.sourceIndex >= 0 && r.id)
      .slice(0, MAX_DETAIL_ROUTES);
  } catch {
    return [];
  }
}

function badMediaHost(hostname) {
  const host = asString(hostname).toLowerCase();
  if (!host) return true;
  return SHARE_HOST_SUFFIXES.some((h) => host === h || host.endsWith(`.${h}`));
}

function sanitizeMediaUrl(value) {
  const raw = decodeEntities(value)
    .replace(/\\\//g, "/")
    .trim();
  if (!/^https?:\/\//i.test(raw)) return "";
  // 客户端拼 URL 时遇到裸中文会直接抛异常；已编码的中文路径不受影响。
  if (/[^\x21-\x7E]/.test(raw)) return "";
  try {
    const u = new URL(raw);
    if (!/^https?:$/.test(u.protocol)) return "";
    if (badMediaHost(u.hostname)) return "";
    if (/\.(?:html?|jsp|aspx?)$/i.test(u.pathname)) return "";
    if (/(?:^|\/)share(?:\/|$)/i.test(u.pathname)) return "";
    return u.toString();
  } catch {
    return "";
  }
}

function splitGroups(value) {
  return asString(value)
    .split("$$$")
    .map((x) => x.trim());
}

function normalizePlayLines(item, source) {
  const froms = splitGroups(item.playFrom);
  const urls = splitGroups(item.playUrl);
  if (!urls.length || urls.every((x) => !x)) return [];
  let start = 0;
  // 播放体检确认默认线路是伪直链、第二条才能播的源，丢掉第一条，
  // 避免聚合结果把已知坏线路重新放到默认位置。
  if (source.skip_first_line && urls.length > 1) start = 1;
  const lines = [];
  for (let i = start; i < urls.length; i += 1) {
    const episodes = [];
    const seen = new Set();
    for (const part of urls[i].split("#")) {
      const mark = part.indexOf("$");
      if (mark <= 0) continue;
      const name = cleanText(part.slice(0, mark)) || `第${episodes.length + 1}集`;
      const url = sanitizeMediaUrl(part.slice(mark + 1));
      if (!url || seen.has(url)) continue;
      seen.add(url);
      episodes.push(`${name}$${url}`);
    }
    if (episodes.length) {
      lines.push({
        from: cleanText(froms[i] || "") || `线路${i + 1}`,
        episodes,
      });
    }
  }
  return lines;
}

async function fetchHead(url, maxBytes = 4096) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 3500);
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": UA, Range: `bytes=0-${Math.max(31, maxBytes - 1)}` },
      redirect: "follow",
      signal: controller.signal,
    });
    if (![200, 206].includes(res.status) || !res.body) return null;
    const reader = res.body.getReader();
    const { value } = await reader.read();
    try {
      await reader.cancel();
    } catch {
      // body may already be closed
    }
    if (!value?.length) return null;
    const ctype = asString(res.headers.get("content-type")).toLowerCase();
    const head = new TextDecoder("utf-8").decode(value).replace(/^\uFEFF/, "").trimStart();
    return { value, ctype, head };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function isDirectMedia(probe) {
  if (!probe) return false;
  if (probe.ctype.startsWith("video/") || probe.ctype.startsWith("audio/")) return true;
  if (probe.value[0] === 0x47) return true; // MPEG-TS
  const v = probe.value;
  return v.length >= 12 && v[4] === 0x66 && v[5] === 0x74 && v[6] === 0x79 && v[7] === 0x70;
}

function looksLikeHtml(probe) {
  return (
    !probe ||
    /^<!doctype\s+html/i.test(probe.head) ||
    /^<html/i.test(probe.head) ||
    /^<head/i.test(probe.head)
  );
}

async function mediaLooksPlayable(url) {
  // 播放分片的深度检测已由构建期 probe_play 完成。这里只做一次轻量响应
  // 检查，目的是拦住 HTML 播放器页、网盘页和错误直链；避免在详情请求里
  // 对同一 CDN 连环探测，反而触发限流把正常线路误删。
  const probe = await fetchHead(url, 8192);
  if (!probe || looksLikeHtml(probe)) return false;
  if (probe.head.includes("#EXTM3U")) return true;
  if (isDirectMedia(probe)) return true;
  return probe.ctype.includes("mpegurl");
}

function pickMeta(target, item) {
  for (const key of ["pic", "remarks", "year", "area", "lang", "actor", "director", "content", "time"]) {
    if (!target[key] && item[key]) target[key] = item[key];
  }
}

function buildSearchList(groups, keyword) {
  const list = [...groups.values()];
  list.sort((a, b) => {
    const byScore = scoreTitle(b, keyword) - scoreTitle(a, keyword);
    if (byScore) return byScore;
    if (a.time && b.time && a.time !== b.time) return b.time.localeCompare(a.time);
    return a.name.localeCompare(b.name, "zh-CN");
  });
  return list.slice(0, RESULT_LIMIT).map((group) => ({
    vod_id: encodeId(group.routes),
    vod_name: group.name,
    vod_pic: group.pic,
    vod_remarks: group.remarks,
    vod_year: group.year,
    vod_area: group.area,
    vod_lang: group.lang,
    vod_actor: group.actor,
    vod_director: group.director,
    vod_content: group.content,
    vod_play_from: group.labels.join("$$$"),
    vod_play_url: "",
  }));
}

async function search(keyword, page) {
  const sources = CATALOG.sources;
  const results = await mapLimit(sources, UPSTREAM_CONCURRENCY, (source, sourceIndex) =>
    fetchUpstream(source, { ac: "videolist", wd: keyword, pg: page }),
  );
  const groups = new Map();
  let successes = 0;
  let pagecount = 1;
  for (const result of results) {
    if (!result.ok) continue;
    successes += 1;
    pagecount = Math.max(pagecount, Math.min(50, Number(result.pagecount) || 1));
    for (const raw of result.items) {
      const item = normalizeItem(raw, result.source, sources.indexOf(result.source));
      if (!item) continue;
      const key = titleKey(item);
      let group = groups.get(key);
      if (!group) {
        group = {
          name: item.name,
          pic: item.pic,
          remarks: item.remarks,
          year: item.year,
          area: item.area,
          lang: item.lang,
          actor: item.actor,
          director: item.director,
          content: item.content,
          time: item.time,
          routes: [],
          labels: [],
        };
        groups.set(key, group);
      }
      pickMeta(group, item);
      if (!group.routes.some((r) => r.sourceIndex === item.sourceIndex && r.id === item.id)) {
        group.routes.push({ sourceIndex: item.sourceIndex, id: item.id });
      }
      if (!group.labels.includes(item.source.label)) group.labels.push(item.source.label);
    }
  }
  if (!successes) {
    return {
      ...emptyResult("所有上游暂时不可达"),
      class: visibleClasses(),
    };
  }
  return {
    code: 1,
    msg: `ok ${successes}/${sources.length}`,
    page,
    pagecount,
    limit: RESULT_LIMIT,
    total: groups.size,
    list: buildSearchList(groups, keyword),
    class: visibleClasses(),
  };
}

async function category(typeId, page) {
  if (!(CATALOG.classes || []).some((c) => c.type_id === typeId)) {
    return emptyResult("未知分类");
  }
  const sources = CATALOG.sources
    .map((source, index) => ({ source, index }))
    .filter(({ source }) => (source.categories?.[typeId] || []).length > 0);
  if (!sources.length) return emptyResult("该分类暂无可用上游");

  const results = await mapLimit(sources, UPSTREAM_CONCURRENCY, ({ source }) =>
    fetchUpstream(source, {
      ac: "detail",
      t: (source.categories[typeId] || []).join(","),
      pg: page,
    }),
  );
  const groups = new Map();
  let successes = 0;
  let pagecount = 1;
  for (const result of results) {
    if (!result.ok) continue;
    successes += 1;
    pagecount = Math.max(pagecount, Math.min(50, Number(result.pagecount) || 1));
    const sourceIndex = CATALOG.sources.indexOf(result.source);
    const allowedIds = new Set((result.source.categories?.[typeId] || []).map(String));
    for (const raw of result.items) {
      const item = normalizeItem(raw, result.source, sourceIndex);
      if (!item || !categoryMatches(typeId, item, allowedIds)) continue;
      const key = titleKey(item);
      let group = groups.get(key);
      if (!group) {
        group = {
          name: item.name,
          pic: item.pic,
          remarks: item.remarks,
          year: item.year,
          area: item.area,
          lang: item.lang,
          actor: item.actor,
          director: item.director,
          content: item.content,
          time: item.time,
          routes: [],
          labels: [],
        };
        groups.set(key, group);
      }
      pickMeta(group, item);
      if (!group.routes.some((r) => r.sourceIndex === item.sourceIndex && r.id === item.id)) {
        group.routes.push({ sourceIndex: item.sourceIndex, id: item.id });
      }
      if (!group.labels.includes(item.source.label)) group.labels.push(item.source.label);
    }
  }
  if (!successes) return emptyResult("分类上游暂时不可达");
  return {
    code: 1,
    msg: `ok ${successes}/${sources.length}`,
    page,
    pagecount,
    limit: RESULT_LIMIT,
    total: groups.size,
    list: buildSearchList(groups, ""),
    class: visibleClasses(),
  };
}

async function detail(routeList) {
  if (!routeList.length) return emptyResult("无效的资源 ID");
  const results = await mapLimit(routeList, MAX_DETAIL_ROUTES, (route) => {
    const source = sourceByIndex(route.sourceIndex);
    if (!source) return Promise.resolve({ ok: false, source: null, items: [] });
    return fetchUpstream(source, { ac: "detail", ids: route.id });
  });

  let base = null;
  const lines = [];
  const seenBlocks = new Set();
  const usedLabels = new Set();
  for (const result of results) {
    if (!result.ok || !result.source) continue;
    const sourceIndex = CATALOG.sources.indexOf(result.source);
    for (const raw of result.items) {
      const item = normalizeItem(raw, result.source, sourceIndex);
      if (!item) continue;
      if (!base) {
        base = {
          name: item.name,
          pic: item.pic,
          remarks: item.remarks,
          year: item.year,
          area: item.area,
          lang: item.lang,
          actor: item.actor,
          director: item.director,
          content: item.content,
        };
      } else {
        pickMeta(base, item);
      }
      const playLines = normalizePlayLines(item, result.source);
      for (const line of playLines) {
        const blockKey = line.episodes.map((x) => x.slice(x.indexOf("$") + 1)).join("|");
        if (!blockKey || seenBlocks.has(blockKey)) continue;
        seenBlocks.add(blockKey);
        let label = result.source.label || "线路";
        let n = 2;
        while (usedLabels.has(label)) label = `${result.source.label}${n++}`;
        usedLabels.add(label);
        lines.push({ from: label, episodes: line.episodes });
        if (lines.length >= 8) break;
      }
      if (lines.length >= 8) break;
    }
    if (lines.length >= 8) break;
  }
  // 详情在返回前抽检每条线路的首个播放地址，能挡住“URL 长得像 m3u8、
  // 实际返回 HTML 播放器/网盘页”的情况；失败线路不给客户端，避免点开闪退。
  const checked = await mapLimit(lines, 8, async (line) => {
    const first = line.episodes[0];
    const url = first.slice(first.indexOf("$") + 1);
    return { line, ok: await mediaLooksPlayable(url) };
  });
  const playableLines = checked.filter((x) => x.ok).map((x) => x.line);
  if (!base || !playableLines.length) return emptyResult("详情或播放地址暂不可用");
  return {
    code: 1,
    msg: `ok ${playableLines.length} lines`,
    page: 1,
    pagecount: 1,
    limit: RESULT_LIMIT,
    total: 1,
    list: [
      {
        vod_id: encodeId(routeList),
        vod_name: base.name,
        vod_pic: base.pic,
        vod_remarks: base.remarks,
        vod_year: base.year,
        vod_area: base.area,
        vod_lang: base.lang,
        vod_actor: base.actor,
        vod_director: base.director,
        vod_content: base.content,
        vod_play_from: playableLines.map((x) => x.from).join("$$$"),
        vod_play_url: playableLines.map((x) => x.episodes.join("#")).join("$$$"),
      },
    ],
    class: visibleClasses(),
  };
}

function intParam(value, fallback, min, max) {
  const n = Number.parseInt(asString(value), 10);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, n));
}

async function routeApi(url) {
  const params = url.searchParams;
  const ids = params.get("ids") || "";
  if (ids) return detail(decodeId(ids));

  const page = intParam(params.get("pg"), 1, 1, 50);
  const keyword = cleanText(params.get("wd") || "");
  if (keyword) return search(keyword.slice(0, 50), page);

  const typeId = cleanText(params.get("t") || "");
  if (typeId) return category(typeId, page);

  return {
    code: 1,
    msg: "JoeTV ready",
    page: 1,
    pagecount: 1,
    limit: RESULT_LIMIT,
    total: 0,
    list: [],
    class: visibleClasses(),
  };
}

async function cachedResponse(request, ctx, producer) {
  const cache = typeof caches !== "undefined" ? caches.default : null;
  if (!cache) return producer();
  const key = new Request(request.url, { method: "GET" });
  try {
    const hit = await cache.match(key);
    if (hit) return hit;
  } catch {
    // cache is an optimization only
  }
  const response = await producer();
  if (response.ok) {
    try {
      ctx?.waitUntil?.(cache.put(key, response.clone()));
    } catch {
      // ignore cache write failures
    }
  }
  return response;
}

export async function handle(request, ctx = null) {
  const url = new URL(request.url);
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders() });
  if (request.method !== "GET" && request.method !== "HEAD") {
    return jsonResponse({ code: 0, msg: "method not allowed", list: [] }, 405);
  }

  if (url.pathname === "/" || url.pathname === "/health") {
    return jsonResponse({
      code: 1,
      name: "JoeTV",
      version: "1.0",
      sources: CATALOG.source_count,
      generated_at: CATALOG.generated_at,
      endpoint: `${url.origin}/api.php/provide/vod/`,
    });
  }
  if (url.pathname === "/diag") {
    const keyword = cleanText(url.searchParams.get("wd") || "庆余年").slice(0, 50);
    const started = Date.now();
    const results = await mapLimit(CATALOG.sources, UPSTREAM_CONCURRENCY, (source) =>
      fetchUpstream(source, { ac: "videolist", wd: keyword, pg: 1 }),
    );
    return jsonResponse({
      code: 1,
      keyword,
      total_ms: Date.now() - started,
      ok: results.filter((x) => x.ok).length,
      sources: results.map((x) => ({
        id: x.source.id,
        label: x.source.label,
        ok: x.ok,
        items: x.items.length,
        error: x.error || "",
        elapsed_ms: x.elapsed,
      })),
    });
  }
  if (!API_PATHS.has(url.pathname)) {
    return jsonResponse({ code: 0, msg: "not found", list: [] }, 404);
  }

  try {
    return await cachedResponse(request, ctx, async () => jsonResponse(await routeApi(url)));
  } catch (error) {
    return jsonResponse(
      {
        code: 0,
        msg: `JoeTV error: ${asString(error?.message || error).slice(0, 160)}`,
        page: 1,
        pagecount: 1,
        limit: RESULT_LIMIT,
        total: 0,
        list: [],
      },
      502,
    );
  }
}

export default {
  fetch(request, env, ctx) {
    return handle(request, ctx);
  },
};

export const __test__ = {
  encodeId,
  decodeId,
  sanitizeMediaUrl,
  normalizePlayLines,
  parsePayload,
  normalizeTitle,
  titleKey,
};
