# 聚合影视仓

面向 [FongMi/TV](https://github.com/FongMi/TV)（影视仓）的多源聚合配置。把多个公开影视仓的接口抓下来、去重、合并成一份配置，APP 里只填一个地址就能用上全部站点的资源。

本目录是 `josephgg/source` 仓的 `tvbox/` 子目录，与仓库根目录的 IPTV 直播源互不影响。

## 直接使用

三个仓，按需要选一个填进 APP「设置 → 配置地址」：

| 仓 | 地址后缀 | 站点 | 适合 |
| --- | --- | --- | --- |
| 精选（推荐） | `api/lite.json` | 72 | 一库一入口 + 类目配额 + 站名重写，接口探活且按速度排序 |
| 全部聚合 | `api/all.json` | 3400+ | 找冷门资源，一个地址装下 40 个源的全部站点 |
| 分源 | `api/src-<id>.json` | 4–298 | 只用某一家 |

精选仓（主地址）：

```
https://cdn.jsdelivr.net/gh/josephgg/source@main/tvbox/api/lite.json
```

全部聚合：

```
https://cdn.jsdelivr.net/gh/josephgg/source@main/tvbox/api/all.json
```

备用地址，主地址拉不动时换着试（`api/lite.json` 同理换后缀）：

```
https://fastly.jsdelivr.net/gh/josephgg/source@main/tvbox/api/all.json
https://raw.githubusercontent.com/josephgg/source/main/tvbox/api/all.json
https://gh-proxy.com/https://raw.githubusercontent.com/josephgg/source/main/tvbox/api/all.json
https://ghfast.top/https://raw.githubusercontent.com/josephgg/source/main/tvbox/api/all.json
```

完整清单见 `mirrors.txt`（构建时自动生成）。

## 站点排序

站点列表的顺序就是配置里的顺序，而 APP 打开首页用的正是**第一个站点**（`VodConfig.setHome()` 找不到 `home` 时 fallback 到 `getSites().get(0)`）。所以排序不是好看问题，它决定首屏能不能出内容。

打分口径（`build.py: quality_score`），分数越高越靠前：

| 项 | 分值 | 理由 |
| --- | --- | --- |
| CMS 采集接口（`type` 为采集 API） | +34 | 直连资源站，结构稳定、无需运行时 |
| 内置爬虫 `csp_*` | +20 | 依赖对应 jar 与客户端运行时，仍比远程 JS 稳定 |
| JS 爬虫 | +8 | 要起 JS 运行时并下载脚本，最慢也最易失效 |
| 无需 jar / jar / js,zip | +8 / +3 / +1 | 免下载的打开更快 |
| 名称含影视类词 | +10 | 影视、电影、剧集、动漫、采集、资源、4K… |
| 名称含工具类词 | −22 | MV、音乐、网盘、搜索、磁力、直播、豆瓣、央视… |
| 接口探活通过 | +20 | 构建时真请求一次 `api?ac=list`，有 `class` 返回才算通 |
| 搜索精准 / 合格 | +12 / +6 | 两个关键词实测，命中率至少 70% |
| 搜索杂乱 / 不可用 | −12 / −20 | 不再让弱搜索站仅凭「分类多」坐上首页 |
| 跨源被收录 | +3/源（上限 +6） | 多个源都用同一后端，说明它在多方验证下活着 |
| 爬虫文件 404 | −80 | 脚本都没了，打开必然失败 |
| 未参与聚合搜索 | −6 | 看得到但搜不到，优先级略降 |

两个探活都**只加分或只沉底，不删站点**：`probe_spider` 只把 404/410 判死（网络异常不算），`probe_cms` 不通不扣分——GitHub 海外 runner 连不上国内域名时，排序会退化成纯启发式，而不是把可用站点误杀。当前结果见 `report.md` 的「站点排序（前 20）」。

精选仓在此基础上做五件事（`pick_lite`）：

1. **一个资源库只留一个入口**：HTTP 站按「规范化主机 + 接口路径 + 业务参数」归并（`lib_key`），同域名的不同路径不会误并；`csp_`/`py_` 按「类名 + 完整 ext 的稳定哈希」归并（`lib_of`），不再只比较配置前 120 字。搜索结果完全相同的跨域入口也会再去重。某库的最佳代表因单源上限进不来时，会自动换用该库下一个来源的代表。
2. **类目配额**：名额按 `CATEGORY_QUOTA` 分到各内容类型，电影剧集约占 40%、动漫 17%、4K 14%，72 站的目标约为影视 29–31、动漫 12、4K 10。类目由**站名信号优先**判定，分类清单兜底；综合采集站里的「动漫片」分类不能替代独立动漫库。
3. **单源上限**：同一顶层源最多 `lite_per_source` 个（多仓按父源算），避免一家吃满；小众类目（少儿/戏曲/综艺/纪录片/音乐）豁免。同一作者的系列站同类目最多 3 个，同名品牌只在同类目内去重，不跨类目误删。
4. **必收录白名单**：`sources.json` 的 `build.pin_keys` 里的站点会先钉进精选仓、占掉对应类目名额，再走常规选站。想指定某个库入选时改这里，别去动其它规则。
5. **首页与站名**：首页优先选「电影、电视剧、动漫三类齐全 + CMS 当前可访问 + 搜索实测合格」的综合库。客户端看到 `类目·品牌`，去掉来源前缀、emoji 和营销词；**`key` 不变**，收藏和播放历史不受影响。

`all.json` 仍保留「源前缀·原名」，方便排查「这个站是谁给的」；`lite.json` 是给用户看的成品，两者刻意不同名。

## 为什么不是直接配「多仓地址」

FongMi 的 `urls` 多仓**既不是资源合并，也不是选择器**。源码 `VodConfig.parseDepot()` 只有三步：

1. 把 `urls` 里每一项转成 `Config`；
2. `load(configs.get(0))` —— **只加载第一条**，其余直接丢弃（`completeLoad()` 里只有这一条会 `update()` 入库）；
3. `Config.delete(config.getUrl())` —— 把多仓地址本身从库里删掉。

所以配 `index.json` 等价于配它排在第一的那条（当前是 `lite.json`），既不能选也不能切换。要用分仓就直接填分仓地址；`index.json` 只对带仓库选择器的客户端（如 TVBox 原版）有意义。要实现「一个地址装下所有资源」，只能在**构建期合并**，也就是本目录做的事。

合并能成立的前提是客户端支持多爬虫共存：`JarLoader` 内部用 `ConcurrentHashMap<String, DexClassLoader>` 按 jar 的 md5 缓存加载器，每个站点可以带自己的 `jar`。构建时会把源仓顶层的 `spider` 落到**每个站点**上，避免跨源继承失效。

## 目录结构

```
tvbox/
├── sources.json        唯一维护入口：源清单与构建参数
├── build.py            抓取 → 绝对化 → 去重 → 合并 → 质量排序 → 精选
├── tools/jsonc.py      宽松 JSON 解析（注释 / 尾逗号 / base64 / AES-CBC）
├── tools/validate.py   产物验收：结构约束 + 抽样探活
├── tools/mix_lives.py  各仓直播频道汇总 / 去重 / 探活，并入根目录 m3u
├── tools/mix_lives_ext.py  独立分发 m3u（IPTV 生成类项目）合并工具
├── tools/verify_schema.py  按客户端模型逐字段校验产物，防「一个字段类型错整份配置作废」
├── tools/audit_lite.py 精选内容验收：核心类目 / 重复库 / 首页覆盖与搜索
├── tools/selftest.py   构建规则回归测试（含大响应、XML、缓存与去重边界）
├── tools/relite.py     离线预览精选仓（直接复用 build.py 的规则，不用重新抓源）
├── tools/probe_search.py   实测各站搜索质量：命中率 / wd 是否生效 / 成人内容
├── tools/probe_rules.py    规则站（csp/drpy）体检：jar 完整性 / 规则可解析 / 目标站可达
├── tools/probe_play.py     播放链路体检：首集是否真出流、默认线路能不能播
├── tools/probe_rules.py    规则站（csp/drpy）健康度：jar 完整性 + md5 + 规则目标站可达 + 选择器是否仍命中
├── rule_health.json    规则站体检结果（含 dead_streak；ext 为空等离线不可判定的标 unverifiable，不当死站）
├── play_health.json    采集站播放链路体检（首集地址 / 清单 / 分片；默认线路不可用单列 ok_secondary）
├── search_quality.json 搜索实测结果（构建时按它决定关搜索 / 关快速搜索 / 剔除）
├── api/lite.json       精选仓（一库一入口 + 类目配额 + 站名重写）
├── api/all.json        总聚合仓（全部站点，按质量分排序）
├── api/src-<id>.json   各源单仓快照（排查用；某源本轮抓取失败时保留上一轮，
│                       不会因上游抖动变成 404）
├── index.json          多仓索引（FongMi 只认第一条，TVBox 原版才有选择器）
├── assets/wallpaper.webp  首页壁纸（1920×1080，约 27KB，被 override 引用）
│                       原图不提交（.gitignore 里的 assets/_raw/）
├── status.json         机器可读构建状态
├── cms_alive.json      采集接口探活历史（7 天内成功过即视为可用，用于稳定排序）
├── report.md           人类可读构建报告
└── mirrors.txt         地址清单
```

仓库根的 `.github/workflows/tvbox-build.yml` 负责每日 3 次重建并提交产物。

## 维护方式

只改 `sources.json`，其余全部自动生成。加一个源：

```json
{
  "id": "myrepo",
  "name": "我的仓",
  "tag": "我的",
  "url": "https://example.com/api.json",
  "priority": 50,
  "enabled": true
}
```

- `tag` 会作为站点名前缀（`高天·豆瓣`）。合并后同名站点很多，不区分没法用。
- `priority` 越小越优先。同一个站点被多个源收录时，保留优先级高的那份，URL 与 jar 也以它为准。
- 源失效就把 `enabled` 改成 `false`，或直接删掉。

改完推 GitHub，Actions 自动重建；本地也可以直接跑：

```bash
cd tvbox
pip install -r requirements.txt
python tools/probe_search.py --file api/all.json --merge --max-age 86400
python build.py
python tools/selftest.py
python tools/verify_schema.py && python tools/audit_lite.py
python tools/validate.py  # 可选：额外做网络抽样
```

`build` 段可调参数：

| 键 | 默认 | 作用 |
| --- | --- | --- |
| `lite_size` | 72 | 精选仓站点数 |
| `lite_per_source` | 5 | 精选仓每个顶层源的站点上限 |
| `pin_keys` | `[]` | 必收录的站点 key（不受配额与单源上限约束） |
| `override` | 无 | 固定 `name` / `notice` / `wallpaper` / `logo`，覆盖各源自带的值；写空串等于删掉该字段 |
| `probe_spider` | true | 构建时探活 jar/js 爬虫文件，404/410 的站点移出聚合搜索并沉底 |
| `probe_cms` | true | 构建时探活 CMS 采集接口（`api?ac=list`），通的加分并按响应速度排序，明确 403 的降权 |
| `cms_timeout` | 12 | CMS 探活超时（秒） |
| `min_retain_ratio` | 0.85 | 站点数低于上轮的 85% 就中止，不覆盖旧产物 |

精选仓类目配额在 `build.py` 的 `CATEGORY_QUOTA` 常量里（键=类目，值=目标占比）。要调整「电影剧集」与「短剧」的比例、或给某类加配额，改这里即可。

## 直播源

仓库根目录的 `iptv_filtered.m3u` 除原有的央视/卫视清单外，还会并入各影视仓配置里的 `lives` 频道：

```bash
cd tvbox
python tools/mix_lives.py --refresh --write
```

规则：现有条目不动、只追加到末尾；频道名规范化后去重（`CCTV-1 高清` 与 `CCTV1` 视为同一台）；**每条线路真探活**——IPTV 源死链率极高，实测 1263 条线路只有 166 台存活，不探活等于往播放列表里灌垃圾；央视 > 卫视 > 港澳台 > 地方台，每台最多 2 条线路，且忽略 `?id=` / `?token=` 这类同流变体。写入前自动备份 `iptv_filtered.m3u.bak`。

不加 `--write` 只统计不改文件，可以先看能并入多少。

另有一批项目不分发影视仓配置、只产出整份 m3u（`Guovin/iptv-api` 一类），走独立工具：

```bash
cd tvbox
python tools/mix_lives_ext.py --probe-limit 700            # 先看统计
python tools/mix_lives_ext.py --write --probe-limit 700    # 探活后增量追加
```

与上面的区别：增量追加，上一轮写入的频道原样保留；URL 与频道名双向去重（外部源与本仓现有清单重复率实测 72%）；按分组限量后再探活，避免地方台淹没央视/卫视名额。

## 数据来源

| 来源 | 说明 |
| --- | --- |
| 高天流云 / 老刘备 / 分享者 / 王二小 / 香雅晴 / 短剧专线 / 俊佬 / 无邪 / 肥猫 | 直接接入的独立仓 |
| [kimwang1978/tvbox](https://github.com/kimwang1978/tvbox) | `play.iptv365.org` 多仓，22 家厂商配置逐个接入（该仓 `tvbox.txt` 本身 JSON 有语法错误，无法整体引用） |
| [laoma528/awesome-zhuiju-free](https://github.com/laoma528/awesome-zhuiju-free) | 资源目录，取其中 `tvbox_config` 分类里可解析的 9 个配置；`伦理接口`、图片伪装配置（`.webp`/`.jpg`）不收 |

## 合并规则

| 项目 | 处理方式 |
| --- | --- |
| `sites` | 全部合并；按 `api + ext + type` 判重，跨源重复只留优先级最高的一份 |
| 站点 `key` | 重排为 `源id_原key`，保证跨源不冲突；同一站点每次构建 key 稳定，收藏与历史不会丢 |
| 站点 `jar` | 源仓顶层 `spider` 显式写入每个站点，不同爬虫家族可共存 |
| 相对路径 | `./lib/x.js`、`./jar/x.jar` 在构建期转绝对。客户端 `Decoder.fix()` 按**配置地址**解析相对路径，不提前转，装到本仓后全部 404 |
| 镜像前缀 | 判重前先剥离 `gh-proxy.com/` 等前缀。无邪这类仓会把别家源整体搬运并加前缀，不归一就会重复收录 600+ 条 |
| `parses` | 合并去重，按被多少个源收录排序，取前 36 |
| `flags` | 取并集 |
| `lives` | 合并去重，最多 12 个 |
| `ads` | 默认不合并（各家正则强度不一，混用容易误杀），需要时把 `build.merge_ads` 改成 `true` |
| `wallpaper` / `notice` | 取第一个可用源 |

## 聚合搜索质量

聚合搜索是把**所有 `searchable` 的站点并发发出去**，结果按站点分组呈现。所以「搜出来乱、不匹配」几乎都不是客户端的问题，而是混进了几类坏站点：

| 现象 | 根因 | 处置 |
| --- | --- | --- |
| 搜什么都返回一堆无关内容 | 站点不认 `wd` 参数，直接回整库/热播列表 | `searchable: 0` |
| 同一批结果重复十几遍 | 不同域名挂着同一个内容库（实测 8 个站搜「庆余年」返回**一模一样**的 8 条） | 搜索指纹去重，精选仓只留一个入口 |
| 搜出来是网页或一片空白 | 搜索接口已返回 HTML（域名被劫持、CF 挑战）或明确提示「暂不支持搜索」 | `searchable: 0`，浏览保留 |
| 结果里混进成人内容 | 上游把成人站塞进了影视库 | 整站剔除 + 域名黑名单 |
| 站点点开就报错 | `api` 指向 `127.0.0.1:10079/p/0/proxy/...`，靠本机代理程序工作 | 整站剔除 |

判定不靠猜，由 `tools/probe_search.py` 实测：用两个语义无关的词（庆余年 / 熊出没）各搜一次，看四个指标——

- **命中率**：标题真的含关键词的比例。低于 70% 说明塞了大量无关结果 → 只关快速搜索（`quickSearch: 0`），完整搜索保留
- **两次结果重合度**：≥ 50% 说明 `wd` 根本没生效、返回的是固定列表 → 关搜索
- **是不是有效响应**：支持 CMS JSON 与 `type=0` 的 MacCMS XML；HTML/脚本等客户端无法解析的响应才关搜索，`py_`/JS 爬虫不直接套用 CMS 测法
- **成人特征词**：多条命中且达到明显占比才整站剔除，避免单个普通影片标题造成误杀

```bash
cd tvbox
python tools/probe_search.py                            # 测 api/lite.json，写 search_quality.json
python tools/probe_search.py --file api/all.json --workers 16
python tools/probe_search.py --file api/all.json --merge --max-age 86400  # CI：24h 缓存
```

构建时自动读 `search_quality.json`：`disable` / `quick_off` / `adult` 三种动作分别处置；`build.block_hosts` 里的域名无条件剔除（换 key 也拦得住）。

**一个后端只认一个入口**：同一个 CMS 后端常被几十个源收录，key 和 api 写法各不相同（尾斜杠、`?ac=list`、`/from/xxx`）。质检结论和搜索指纹都按 `api_norm()` 归一化继承；同 key 换 API 时则拒绝复用旧结论。探活缓存同样绑定 API，避免旧分类与速度错套到新站。发布前 `audit_lite.py` 会再次检查重复资源库、核心类目数量及首页三类覆盖，未通过则 CI 不提交产物。

## 规则站体检（csp / drpy）

全量 4546 站里，规则站占 92%（csp/py 2711、drpy JS 1475），但它们没法用 `ac=videolist&wd=` 验活。`tools/probe_rules.py` 用四件事替代执行：

1. **jar 完整性**：能不能下载（失败重试一次）、是不是合法 ZIP、里面有没有 `classes.dex` 或 `.class`
2. **md5 一致性**：`jar;md5;xxx` 声明的值与实际文件是否相符（不符会让客户端缓存键错位）
3. **配置可解析**：规则 JSON/JS 能拉到、能按 JSONC 解析（尾逗号、BOM、JS 里的 `\'`）
4. **目标站还在不在**：XYQHiker/XBPQ 规则里写死的「首页推荐链接 / 搜索链接」请求一次，再用「搜索列表数组规则」的选择器去命中返回 HTML

判决分四级，**`unverifiable` 不算死站**：ext 为空的 csp 站把目标站写死在 jar 里，离线只能验 jar，必须真机复核；403 反爬同理。域名解析失败还会用阿里/腾讯 DoH 复核一次——国内网络对影视站常见 DNS 污染，直接判死会误杀（实测 41 个「解析失败」里 15 个公网仍有 A 记录）。

判死只认硬证据，另外三类一律归 `unverifiable`：

- **网络侧异常**（`TimeoutError`、`RemoteDisconnected`、连接重置）：本机慢不代表站点死，海外 runner 上常常是通的；
- **非标响应**（301 无法收敛、444 静默断开、850）：入口换了或拦了探针，不是没内容；
- **首页 404 但站点根还活着**：规则把首页推荐链接写死成 `/xxx/22.html` 这种固定页号，站点活着、该页被删，客户端表现为「首页空白、分类能用」，判 `weak` 更准确。

```bash
cd tvbox
python tools/probe_rules.py                      # 只测 api/lite.json（约 20 秒）
python tools/probe_rules.py --all --limit 300    # 全量抽样
python tools/probe_rules.py --all --limit 300 --write   # 写 rule_health.json
python tools/probe_rules.py --all --jobs 24 --write --max-age 20   # CI：全量，每天只跑一次
```

全量 4221 个规则站的实测分布：`ok` 996（24%）、`weak` 397（9%）、`dead` 537（13%）、`unverifiable` 2284（54%）；jar 可用率 98.7%，其中 85 个是「200 但不是 ZIP」的假包。`dead` 里 535 个是连续两轮确认的，构建会把它们移出聚合搜索。

### 构建怎么用这份结果

`build.py` 启动时读 `rule_health.json`，只做加减分和一种硬处置，不参与「接口通」判定：

| 体检等级 | 处理 |
|---|---|
| `ok` | 排序 +6 |
| `weak` | −12（主页能开但选择器不命中，典型是站点改版：分类还在、点进去空白） |
| `dead` 连续 1 轮 | −30，只沉底不下架 |
| `dead` 连续 2 轮 | −90，且移出聚合搜索、不进精选 |
| `unverifiable` | 不奖惩 |

两个约束是有意为之：

- **连续两轮才判死。** 大 jar（4 MB、带保护壳）在弱网下必超时，上游也有临时 502；单轮就踢站会误杀，所以 `probe_rules.py` 每次写盘时会把上一轮的 `dead_streak` 接上去，构建只认 `>= 2`。
- **结论 21 天过期。** 域名会复活、上游会修规则，拿一个月前的判定杀站等于把可用资源当垃圾清掉；过期后整份文件不采信，构建照常跑。

规则站 key 变化（上游改品牌前缀）时，按 `api + jar + ext` 的指纹继承结论，不会因为换个名字就丢掉健康记录。抽样跑（`--limit`）写盘时会保留未抽到的旧记录，避免把整份文件覆盖成样本。

### 人工下架

判定回不来的站（域名注销、页面改成 SPA 只剩空壳）不用等两个构建周期，直接写 `sources.json` 的 `retire_keys`：

```json
"retire_keys": {
  "ivxiaosa_冬日动漫": "drdm.fun NXDOMAIN，DoH 无 A 记录（2026-11-12）"
}
```

`retire_keys` 的值是下架依据，不是备注装饰——半年后回看时，唯一能判断「这站该不该放回来」的就是这句话。域名级黑名单（`block_hosts`）只对采集站有效，规则站的站址藏在 `ext`/`jar` 里，所以需要按 key 下架。

## 播放链路体检（采集站）

接口通、搜索有结果，都不代表点开能播。用户反馈的「搜索出结果后闪退」「播放几秒闪退」，
绝大多数落在最后一跳：首集地址、清单、分片。`tools/probe_play.py` 就测这一跳。

```bash
python tools/probe_play.py                     # 只测 api/lite.json（约 18 秒）
python tools/probe_play.py --all --jobs 16     # 全量，规则站直接跳过（约 35 秒）
python tools/probe_play.py --all --write       # 写 play_health.json
```

对每个采集站：搜索一个关键词 → 取详情 → **逐线路**取首集地址 → 请求清单 → 取首个分片。
判决口径：

| 判决 | 含义 | 处置 |
|---|---|---|
| `ok` / `direct` | 清单与分片都取到（或直链 mp4） | 加分 |
| `ok_secondary` | 默认第一条线路播不了，切线路才行 | 降权，不进精选（搜索保留） |
| `share_page` | 首集是网盘分享页，返回 HTML 不是 m3u8 | 移出聚合搜索 |
| `bad_url` | 分集地址含未编码中文，客户端拼 URL 会抛异常 | 移出聚合搜索 |
| `live_format` | 接口返回 `{"class":[...]}`，直播源误入点播 | 移出聚合搜索 |
| `dns_dead` | DoH 无 A 记录（阿里/腾讯双查） | 移出聚合搜索 |
| `dead_link` / `bad_segment` | 清单 4xx / 分片取不到 | 连续两轮才移出 |
| `xml_endpoint` | 接口回 XML，路径里却没有 `/at/xml` | 不进精选 |
| `search_fail` | 搜索不通，但 DoH 有 A 记录 → 本机 DNS 被拦 | 不惩罚，只标注 |
| `search_fail`（DoH 也无 A 记录） | 搜索不通且域名在公共 DNS 上已失效 | 不进精选；全量连轮两轮后移出搜索 |
| `rule_based` / `python_spider` | 解析在客户端执行（jar/JS/py） | 离线判不了，不奖惩 |

三条判据是踩出来的，不要随意放宽：

1. **必须逐线路试。** 实测「非凡」「量子」的线路 1 是 `vip.ffzy-online2.com/share/...`（网盘分享页），
   线路 2 才是 `ffm3u8` 的正常清单。只测第一条会把能播的站判死，只测「有任何一条能播」又会放过
   「默认线路必崩」的站——所以 `ok_secondary` 单独成一级。
2. **DoH 复核不可省。** 10 个 `search_fail` 的精选站里 4 个是 NXDOMAIN 真死，
   3 个 DoH 有正常 A 记录（本机 DNS 被投毒到 `0.0.0.0`），直接判死就是误杀。
3. **相对密钥地址要先解析。** `#EXT-X-KEY:URI="enc.key"` 是相对路径，按清单地址 `urljoin`
   之后再请求，否则拿到的是"未知协议"而不是真正的 404。

### 构建怎么用这份结果

`rule_health.json` 与 `play_health.json` 是两套独立信号，互不替代：

- `PLAY_STRUCTURAL`（分享页 / 中文 URL / 直播格式 / 域名失效）→ 一轮即移出聚合搜索，且不进精选；
- `search_fail` 且 DoH 也拿不到 A 记录 → 不进精选；全量列表要连轮两轮才移出搜索
  （公共 DNS 偶尔 SERVFAIL，单轮就杀会误伤）；DoH 有解析的属于本机被拦，不动；
- `PLAY_SECONDARY`（默认线路不可用 / XML 接口）→ 不进精选，但搜索保留；
- `PLAY_FLAKY`（4xx / 分片失败）→ 连续两轮才定案，单轮只降权；
- 结论 **10 天过期**。播放地址比规则变化快得多，换 CDN、换线路顺序都是常态。

指纹 `play_sig()` 会把功能子域（`api.` `cj.` `app.`）和接口前缀（`api.php/` 与 `api/`）抹平再比对：
同一后端有几十个入口、写法不一，不归一就会「同一个坑换个名字再进精选一次」。

## 已知限制

- **源站会失效。** 构建只保证产物结构合法、链接可达，不代表每个站点的爬虫都能取到内容。`report.md` 记录每个源的抓取状态。
- **同名站点会并存。** 不同源提供的「同一个」站点接口实现往往不同，去重只认完全一致的 `api + ext`，其余按不同站点保留。
- **图片化与加密配置。** 部分源把配置伪装成 `.jpg/.png`，或返回 `2423` 开头的 AES-CBC 密文体。后者构建器已内置解密（依赖 `cryptography`）；前者能直接下载，但内容若是真图片则无法解析，记为抓取失败。
- **CDN 有缓存。** jsDelivr 对 `@main` 最长缓存 12 小时，workflow 推送后会主动调用 purge 接口清理；若手机端仍拿到旧配置，把地址里的 `@main` 换成具体 commit hash 即可锁版。
- **站点数量多 ≠ 加载慢，但会让聚合搜索变慢。** 配置原文约 2.0 MB（4591 站）、gzip 后约 300 KB；`VodConfig.initSite()` 只做本地反序列化，`BaseLoader.parseJar()` 也只登记 jar 的 md5，真正的 `DexClassLoader` 等点进站点才加载，首页只加载 `home` 一个站点——所以 4600 站的启动开销仍在百毫秒量级。真正的代价在聚合搜索：`CollectActivity` 把所有 `searchable` 站点一次性提交给 `Task.largeExecutor()`（`newFixedThreadPool(20)`，单站超时 30 s），当前约 3960 个可搜站点，意味着 **198 轮排队**，全量搜索会明显变慢。日常建议直接用 `api/lite.json`（72 站，约 4 轮），或在搜索页先勾选常用站点再搜。
- **站点列表长。** 4600 项靠 RecyclerView 回收，滑动不卡，但翻找费劲；直接配 `api/lite.json` 只有 72 个，或在「站点管理」里收藏常用站点。
- **排序是实测 + 启发式，不是完整播放评测。** CMS 会真请求分类与两个搜索关键词，但 jar/JS 爬虫必须依赖 Android/对应运行时，无法离线完整验证；「分类可访问、搜索相关」也不等于每部片都清晰、流畅、更新及时。当前自动验收保证结构、去重、核心类目与首页搜索，不把它包装成全量播放保证。

## 免责声明

本项目只做配置的抓取、去重与格式转换，不托管、不转存任何影视内容，所有资源来自第三方公开接口。请自行判断使用场景的合规性。
