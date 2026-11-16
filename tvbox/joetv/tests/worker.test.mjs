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

test("真实上游：分类、搜索、详情和播放地址", { timeout: 60000 }, async () => {
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

test("真实上游：电影分类可返回列表", { timeout: 60000 }, async () => {
  const url = "https://joetv.example/api.php/provide/vod/?ac=detail&t=movie&pg=1";
  const data = await (await handle(new Request(url))).json();
  assert.equal(data.code, 1);
  assert.ok(data.list.length > 0, "电影分类至少应有一个上游返回数据");
  assert.ok(data.list.every((x) => String(x.vod_id).startsWith("J")));
});
