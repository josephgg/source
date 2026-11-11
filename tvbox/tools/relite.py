"""离线预览精选仓：不重新抓源，直接拿现有 api/all.json 重算一遍。

调 lite_size / 类目配额 / 命名规则时用它看效果，比跑一次全量构建（约 2 分钟）
快得多。规则本体在 build.py 的 pick_lite / site_category / brand_of 里，
这里只调用不复制 —— 改了 build.py 这里立刻生效，不会两套逻辑走偏。

用法：
    python tools/relite.py               # 按 sources.json 的 lite_size 预览
    python tools/relite.py --size 60     # 临时试别的站数
    python tools/relite.py --dump /tmp/lite.json   # 导出可直接试用的配置
"""
import argparse
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
TVBOX = os.path.dirname(HERE)
sys.path.insert(0, TVBOX)

import build  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=0)
    ap.add_argument("--per-source", type=int, default=0)
    ap.add_argument("--dump", default="")
    args = ap.parse_args()

    conf = json.load(open(os.path.join(TVBOX, "sources.json"), encoding="utf-8"))
    bconf = conf.get("build") or {}
    size = args.size or int(bconf.get("lite_size", 72))
    per = args.per_source or int(bconf.get("lite_per_source", 5))

    allconf = json.load(open(os.path.join(TVBOX, "api", "all.json"), encoding="utf-8"))
    alive = json.load(open(os.path.join(TVBOX, "cms_alive.json"), encoding="utf-8"))
    tags = {s.get("tag") for s in conf["sources"]} | {s.get("name") for s in conf["sources"]}

    # bucket_of：子仓 id -> 顶层源（与 build.py 的构造方式一致）
    bucket = {}
    for s in conf["sources"]:
        top = s["id"].replace("-", "")
        bucket[top] = top
        for i in range(1, 60):
            bucket["%s%d" % (top, i)] = top

    # 与 build.py 一致：先按搜索实测处置（关搜索 / 剔除成人与本机代理站），
    # 再做选站，否则预览结果会包含构建时实际不会出现的站点
    sites = [dict(s) for s in allconf["sites"]]
    build.apply_search_quality(sites, build.load_search_quality(),
                               (conf.get("build") or {}).get("block_hosts") or [])
    sites = [s for s in sites if build.is_searchable(s)]
    picked = build.pick_lite(sites, size, per, bucket, alive, tags=tags,
                             sq=build.load_search_quality(),
                             pin=(conf.get("build") or {}).get("pin_keys") or ())

    cats = Counter(s["name"].split("·")[0] for s in picked)
    print("全量 %d / 可搜 %d → 精选 %d" % (len(allconf["sites"]), len(sites), len(picked)))
    print("类目:", cats.most_common())
    print()
    for s in picked:
        print("  %-14s <- %-30s [%s]" % (
            s["name"], s["key"][:30], build.api_kind(s)))

    if args.dump:
        out = {k: v for k, v in allconf.items() if k != "sites"}
        out["sites"] = picked
        with open(args.dump, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("\n已导出 %s" % args.dump)


if __name__ == "__main__":
    main()
