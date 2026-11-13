#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建规则的离线回归测试。CI 与本地修改后都应运行。"""
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import build  # noqa: E402
from tools import probe_search  # noqa: E402


TITLES = ["庆余年第一季", "庆余年第二季", "庆余年特别篇", "庆余年解说", "庆余年花絮"]


def http_site(key, name, api):
    return {"key": key, "name": name, "api": api, "type": 1, "searchable": 1}


def search_rec(api, titles=None, action="keep", hit=1.0):
    return {"api": api, "action": action, "verdict": "good",
            "hit_rate": hit, "titles1": list(TITLES if titles is None else titles),
            "titles2": [], "tested_at": 100}


class BuildRulesTest(unittest.TestCase):
    def test_searchable_matches_client(self):
        self.assertTrue(build.is_searchable({}))
        self.assertTrue(build.is_searchable({"searchable": 2}))
        self.assertTrue(build.is_searchable({"searchable": "2"}))
        self.assertFalse(build.is_searchable({"searchable": 0}))
        self.assertFalse(build.is_searchable({"searchable": "0"}))

    def test_api_alias_and_business_query(self):
        a = "https://www.example.com/api.php/provide/vod/?ac=list"
        b = "http://example.com//api.php/provide/vod/from/m3u8/at/json/"
        self.assertEqual(build.api_norm({"api": a}), build.api_norm({"api": b}))
        self.assertNotEqual(build.api_norm({"api": "https://example.com/vod?source=1"}),
                            build.api_norm({"api": "https://example.com/vod?source=2"}))
        self.assertEqual(build.api_norm({"api": "https://example.com/vod?ac=list"}),
                         build.api_norm({"api": "https://example.com/vod"}))

    def test_library_keeps_distinct_paths(self):
        self.assertNotEqual(build.lib_key(http_site("a", "甲", "https://cf.example/wsy")),
                            build.lib_key(http_site("b", "乙", "https://cf.example/77")))

    def test_csp_library_compares_full_ext(self):
        prefix = "共同前缀" * 50
        a = {"api": "csp_XBPQ", "ext": prefix + "https://anime-a.example"}
        b = {"api": "csp_XBPQ", "ext": prefix + "https://anime-b.example"}
        self.assertNotEqual(build.lib_of(a), build.lib_of(b))
        self.assertEqual(build.lib_of(a), build.lib_of(dict(a)))

    def test_xml_search_response_is_supported(self):
        xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><rss><list>" \
              "<video><name>庆余年</name></video><video><name>庆余年第二季</name></video>" \
              "</list></rss>"
        self.assertEqual(probe_search.parse_names(xml), ["庆余年", "庆余年第二季"])
        self.assertIsNone(probe_search.parse_names("<html><body>blocked</body></html>"))

    def test_malformed_port_does_not_crash_normalization(self):
        raw = "http://example.com:bad/api.php/provide/vod"
        self.assertEqual(build.api_norm({"api": raw}), raw)

    def test_search_record_alias_and_changed_key(self):
        sq = {"old": search_rec("https://www.example.com/api.php/provide/vod/?ac=list")}
        alias = http_site("new", "别名", "http://example.com/api.php/provide/vod/from/m3u8")
        self.assertIs(build.search_record(alias, sq), sq["old"])
        changed = http_site("old", "换接口", "https://other.example/api.php/provide/vod")
        self.assertIsNone(build.search_record(changed, sq))

    def test_same_titles_deduplicated_across_domains(self):
        sites = [
            http_site("a", "红牛影视", "https://a.example/api.php/provide/vod"),
            http_site("b", "光速影视", "https://b.example/api.php/provide/vod"),
            http_site("c", "天涯影视", "https://c.example/api.php/provide/vod"),
        ]
        sq = {"a": search_rec(sites[0]["api"]), "b": search_rec(sites[1]["api"])}
        picked = build.pick_lite(sites, 3, sq=sq)
        keys = {s["key"] for s in picked}
        self.assertEqual(len(keys), 2)
        self.assertIn("c", keys)
        self.assertEqual(len(keys & {"a", "b"}), 1)

    def test_same_brand_in_different_categories_survives(self):
        sites = [
            {"key": "film", "name": "小米电影", "api": "csp_Film", "ext": "film", "type": 3},
            {"key": "anime", "name": "小米动漫", "api": "csp_Anime", "ext": "anime", "type": 3},
        ]
        picked = build.pick_lite(sites, 2)
        self.assertEqual({s["key"] for s in picked}, {"film", "anime"})

    def test_alive_cache_requires_same_api(self):
        site = http_site("a", "甲", "https://a.example/api.php/provide/vod")
        alias = http_site("b", "乙", "https://www.a.example/api.php/provide/vod/?ac=list")
        rec = {"api": build.api_norm(site), "code": "ok", "ts": 100, "cls": ["电影"]}
        current = build.current_alive([site, alias], {"a": rec})
        self.assertIn("a", current)
        self.assertIn("b", current)
        changed = http_site("a", "甲", "https://new.example/api.php/provide/vod")
        self.assertEqual(build.current_alive([changed], {"a": rec}), {})
        alive, _ = build.merge_alive({"legacy": {"ts": 100, "code": "ok"}}, {})
        self.assertEqual(alive, {})

    def test_search_quality_affects_score(self):
        site = http_site("a", "综合影视", "https://a.example/api.php/provide/vod")
        good, _ = build.quality_score(site, 10, 1, False, search=search_rec(site["api"]))
        weak_rec = search_rec(site["api"], action="quick_off", hit=0.2)
        weak_rec["verdict"] = "weak"
        weak, _ = build.quality_score(site, 10, 1, False, search=weak_rec)
        self.assertGreater(good, weak)

    def test_home_prefers_good_search_over_padding(self):
        a = http_site("a", "暴风影视", "https://a.example/api.php/provide/vod")
        b = http_site("b", "红牛影视", "https://b.example/api.php/provide/vod")
        sites = [a, b]
        alive = {
            "a": {"api": build.api_norm(a), "code": "ok",
                  "cls": ["电影", "电视剧", "动漫"] + ["分类%d" % i for i in range(20)]},
            "b": {"api": build.api_norm(b), "code": "ok", "cls": ["电影", "电视剧", "动漫"]},
        }
        weak = search_rec(a["api"], action="quick_off", hit=0.2)
        weak["verdict"] = "weak"
        other_titles = ["熊出没一", "熊出没二", "熊出没三", "熊出没四", "熊出没五"]
        sq = {"a": weak, "b": search_rec(b["api"], titles=other_titles)}
        picked = build.pick_lite(sites, 4, alive=alive, sq=sq)
        self.assertEqual(picked[0]["key"], "b")

    # ---- 规则站体检（rule_health.json）走的是「两轮确认 + 指纹继承 + 会过期」
    # ---- 三条约束，任何一条被改坏都会让构建批量误杀站点，所以单独锁住。

    def _rule_site(self):
        return {"key": "r1", "name": "香雅·测试动漫", "api": "csp_XYQHiker", "type": 3,
                "searchable": 1, "ext": "https://x.example/rule.json",
                "jar": "https://x.example/spider.jar"}

    def _rh(self, level, streak=1):
        site = self._rule_site()
        return {site["key"]: {"key": site["key"], "sig": build.rule_sig(site),
                              "level": level, "dead_streak": streak}}

    def test_rule_health_needs_two_rounds(self):
        site = self._rule_site()
        once, twice = self._rh("dead", 1), self._rh("dead", 2)
        self.assertFalse(build.rule_dead(site, once))
        self.assertTrue(build.rule_dead(site, twice))
        s1, _ = build.quality_score(site, 10, 1, False, rule=build.rule_record(site, once))
        s2, _ = build.quality_score(site, 10, 1, False, rule=build.rule_record(site, twice))
        self.assertGreater(s1, s2)

    def test_rule_health_inherits_by_signature_only(self):
        site = self._rule_site()
        rh = {"sig#" + build.rule_sig(site): {"key": "上游改名了", "level": "ok"}}
        self.assertEqual(build.rule_record(site, rh)["level"], "ok")
        # 换了 jar 就是另一个规则配置，旧结论不能套过来
        self.assertIsNone(build.rule_record(dict(site, jar="https://x.example/o.jar"), rh))

    def test_stale_rule_health_is_ignored(self):
        import tempfile
        site = self._rule_site()
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"tested_at": __import__("time").time() - 40 * 86400,
                       "sites": [{"key": site["key"], "level": "dead", "dead_streak": 5}]}, f)
        old = build.RULE_HEALTH_FILE
        build.RULE_HEALTH_FILE = path
        try:
            self.assertEqual(build.load_rule_health(), {})
            self.assertFalse(build.rule_dead(site, {}))
        finally:
            build.RULE_HEALTH_FILE = old
            os.remove(path)

    def test_bad_site_is_isolated(self):
        stats = {"skip_bad_site": 0}
        result = build.build_site({"key": "bad", "api": {"not": "a url"}}, {},
                                  set(), set(), stats, {})
        self.assertIsNone(result)
        self.assertEqual(stats["skip_bad_site"], 1)
        self.assertEqual(build.site_list({"sites": "broken"}), [])

    def test_cms_response_over_64kb(self):
        payload = json.dumps({"class": [
            {"type_name": "电影" if i == 0 else "分类%04d" % i} for i in range(2500)
        ], "list": []}).encode("utf-8")
        self.assertGreater(len(payload), 65536)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            api = "http://127.0.0.1:%d/api.php/provide/vod" % server.server_port
            info, probed = build.cms_probe([http_site("big", "大站", api)], timeout=3, workers=1)
            self.assertEqual(probed, 1)
            self.assertEqual(info["big"]["code"], "ok")
            self.assertEqual(len(info["big"]["cls"]), 48)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
