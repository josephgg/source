import assert from "node:assert/strict";
import test from "node:test";

import worker, { __test__, handle } from "../src/index.js";

const {
  encodeId,
  decodeId,
  sanitizeMediaUrl,
  normalizePlayLines,
  parsePayload,
  normalizeTitle,
  scoreTitle,
} = __test__;

test("资源 ID 可逆且不含 URL 危险字符", () => {
  const routes = [
    { sourceIndex: 0, id: "12345" },
    { sourceIndex: 17, id: "abc/def?x=1" },
  ];
  const id = encodeId(routes);
  assert.match(id, /^J[A-Za-z0-9_-]+$/);
  assert.deepEqual(decodeId(id), routes);
});

test("网盘页与裸中文地址被剔除", () => {
  assert.equal(
    sanitizeMediaUrl("https://play.hhuus.com/play/x/index.m3u8"),
    "https://play.hhuus.com/play/x/index.m3u8",
  );
  assert.equal(sanitizeMediaUrl("https://example.com/中文/1.m3u8"), "");
  assert.equal(sanitizeMediaUrl("https://pan.baidu.com/s/abc"), "");
  assert.equal(sanitizeMediaUrl("not-a-url"), "");
  assert.equal(
    sanitizeMediaUrl("https://cdn.example.com/a/index.m3u8?token=1"),
    "https://cdn.example.com/a/index.m3u8?token=1",
  );
});

test("备用线路跳过首条伪线路", () => {
  const source = { label: "测试", skip_first_line: true };
  const lines = normalizePlayLines(
    {
      playFrom: "m3u8$$$m3u8",
      playUrl:
        "第1集$https://play.hhuus.com/play/x/index.m3u8#第2集$https://play.hhuus.com/play/x/2.m3u8$$$第1集$https://cdn.example.com/1.m3u8#第2集$https://cdn.example.com/2.m3u8",
    },
    source,
  );
  assert.equal(lines.length, 1);
  assert.equal(lines[0].episodes.length, 2);
  assert.ok(lines[0].episodes.every((x) => x.includes("cdn.example.com")));
});

test("XML CMS 搜索响应可解析", () => {
  const data = parsePayload(`<?xml version="1.0"?><rss><list><video>
    <id>42</id><name><![CDATA[测试影片]]></name><pic>https://x/a.jpg</pic>
    <note>HD</note><dl><dd flag="m3u8"><![CDATA[第1集$https://cdn.example.com/1.m3u8]]></dd></dl>
  </video></list></rss>`);
  assert.equal(data.list.length, 1);
  assert.equal(data.list[0].vod_id, "42");
  assert.equal(data.list[0].vod_name, "测试影片");
  assert.match(data.list[0].vod_play_url, /cdn\.example\.com/);
});

test("标题归一化能合并标点差异", () => {
  assert.equal(normalizeTitle(" 庆余年：第二季 "), normalizeTitle("庆余年第二季"));
});

test("根路径返回状态，未知路径返回 404", async () => {
  const home = await worker.fetch(new Request("https://joetv.example/"), {}, null);
  assert.equal(home.status, 200);
  const body = await home.json();
  assert.equal(body.name, "JoeTV");
  assert.ok(body.sources >= 1);

  const missing = await handle(new Request("https://joetv.example/nope"));
  assert.equal(missing.status, 404);
});

// 真实上游用例依赖外网；CI 里先用 JOETV_SKIP_LIVE=1 跑离线集，再单独跑这一组。
const SKIP_LIVE = process.env.JOETV_SKIP_LIVE === "1";

test("真实上游：分类、搜索、详情和播放地址", { timeout: 60000, skip: SKIP_LIVE }, async () => {
  const base = "https://joetv.example/api.php/provide/vod/";
  const classes = await (await handle(new Request(base + "?ac=list"))).json();
  assert.equal(classes.code, 1);
  assert.ok(classes.class.length >= 3);

  const search = await (await handle(new Request(base + "?ac=videolist&wd=庆余年"))).json();
  assert.equal(search.code, 1);
  assert.ok(search.list.length > 0, "至少一个上游应返回搜索结果");
  const names = search.list.map((x) => normalizeTitle(x.vod_name));
  assert.equal(names.length, new Set(names).size, "聚合搜索不应出现重复片名");

  const first = search.list[0];
  assert.ok(first.vod_id.startsWith("J"));
  const detail = await (await handle(new Request(base + "?ac=detail&ids=" + encodeURIComponent(first.vod_id)))).json();
  assert.equal(detail.code, 1);
  assert.ok(detail.list.length === 1);
  assert.ok(detail.list[0].vod_play_url.includes("http"));
  assert.ok(!detail.list[0].vod_play_url.includes("pan.baidu.com"));
});

test("真实上游：电影分类可返回列表", { timeout: 60000, skip: SKIP_LIVE }, async () => {
  const url = "https://joetv.example/api.php/provide/vod/?ac=detail&t=movie&pg=1";
  const data = await (await handle(new Request(url))).json();
  assert.equal(data.code, 1);
  assert.ok(data.list.length > 0, "电影分类至少应有一个上游返回数据");
  assert.ok(data.list.every((x) => String(x.vod_id).startsWith("J")));
});

test("同名搜索：版本条目优先于共享前缀的其他作品", () => {
  const kw = "繁花";
  const exact = scoreTitle({ name: "繁花" }, kw);
  const version = scoreTitle({ name: "繁花 普通话" }, kw);
  const versionB = scoreTitle({ name: "繁花 沪语版" }, kw);
  const shortTail = scoreTitle({ name: "繁花错" }, kw);
  const longTail = scoreTitle({ name: "繁花照春晚" }, kw);
  const longer = scoreTitle({ name: "繁花之东北爱情故事" }, kw);

  assert.equal(exact, 100);
  assert.ok(version > shortTail, "「繁花 普通话」应高于「繁花错」");
  assert.ok(versionB > shortTail, "「繁花 沪语版」应高于「繁花错」");
  assert.ok(shortTail > longTail, "标题越接近原名越靠前");
  assert.ok(longTail > longer);
  // 前缀条目不能被溢出长度惩罚压到「包含匹配」档以下
  assert.ok(longer >= 40, "长标题仍需高于 includes 档");

  // 非前缀命中不受影响
  assert.equal(scoreTitle({ name: "一路繁花" }, kw), 40);
  assert.equal(scoreTitle({ name: "某部无关片" }, kw), 0);
});

test("详情抽检：限流/超时不算坏线路，HTML 播放页才算", async () => {
  const { probeMediaState } = __test__;
  const orig = globalThis.fetch;
  const stub = (body, status = 200, ctype = "text/html") => async () =>
    new Response(body, { status, headers: { "content-type": ctype } });
  try {
    // 403（CDN 限流）与网络异常 → unknown，保留给客户端
    globalThis.fetch = stub("", 403);
    assert.equal(await probeMediaState("https://cdn.example/a/index.m3u8"), "unknown");

    globalThis.fetch = async () => {
      throw new TypeError("network error");
    };
    assert.equal(await probeMediaState("https://cdn.example/b/index.m3u8"), "unknown");

    // 真 HTML 播放器页/网盘页 → bad，必须丢，否则点开黑屏或闪退
    globalThis.fetch = stub("<!DOCTYPE html><html><head></head></html>", 200, "text/html");
    assert.equal(await probeMediaState("https://cdn.example/c/share/abc"), "bad");

    // 正常清单与 TS 流 → ok
    globalThis.fetch = stub("#EXTM3U\n#EXT-X-VERSION:3", 200, "application/vnd.apple.mpegurl");
    assert.equal(await probeMediaState("https://cdn.example/d/index.m3u8"), "ok");

    globalThis.fetch = stub(new Uint8Array([0x47, 0x40, 0x11, 0x10]), 200, "video/mp2t");
    assert.equal(await probeMediaState("https://cdn.example/e/index.ts"), "ok");
  } finally {
    globalThis.fetch = orig;
  }
});
