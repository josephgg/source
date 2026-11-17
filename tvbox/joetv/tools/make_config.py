#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 JoeTV 的 TVBox 配置，并同步到主仓 api/ 供公网加载。"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from paths import PROJECT, find_tvbox  # noqa: E402

TVBOX = find_tvbox()
DEFAULT_ENDPOINT = "https://joetv-joe.pages.dev/api.php/provide/vod/"


def dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    args = ap.parse_args()
    endpoint = args.endpoint.rstrip("/") + "/"

    catalog = json.load((PROJECT / "data/catalog.json").open(encoding="utf-8"))
    if not catalog.get("source_count"):
        raise SystemExit("catalog 没有可用上游")
    site = {
        "key": "joetv",
        "name": "JoeTV",
        "type": 1,
        "api": endpoint,
        "searchable": 1,
        "quickSearch": 1,
        "timeout": 20,
    }
    standalone = {"sites": [copy.deepcopy(site)], "parses": [], "flags": []}

    lite = json.load((TVBOX / "api/lite.json").open(encoding="utf-8"))
    combined = copy.deepcopy(lite)
    # JoeTV 现在已经把精选站也合并进上游目录；再叠加 lite 会让同一内容库在
    # 站点列表里出现两次（用户看到两个「魔都」）。按归一化 API 去掉已被覆盖的。
    covered = {
        "%s%s" % (str(s.get("api", "")).split("?")[0].rstrip("/"), "")
        for s in catalog.get("sources") or []
    }

    def uncovered(site):
        api = str(site.get("api") or "").split("?")[0].rstrip("/")
        if not api:
            return True
        if api in covered:
            return False
        return not any(api.startswith(c + "/") or c.startswith(api + "/") for c in covered)

    combined["sites"] = [copy.deepcopy(site)] + [
        s
        for s in lite.get("sites") or []
        if s.get("key") != "joetv" and uncovered(s)
    ]

    for path, data in [
        (TVBOX / "api/JoeTV.json", standalone),
        (TVBOX / "api/JoeTV-plus-stable.json", combined),
    ]:
        dump(path, data)
        print("wrote %s sites=%d" % (path, len(data["sites"])))
    print("JoeTV upstreams=%d lite=%d" % (catalog["source_count"], len(lite.get("sites") or [])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
