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
https://fastly.jsdelivr.net/gh/josephgg/source@main/tvbox/api/lite.json
```

全部聚合：

```
https://fastly.jsdelivr.net/gh/josephgg/source@main/tvbox/api/all.json
```

备用地址，主地址拉不动时换着试（`api/lite.json` 同理换后缀）：

```
https://cdn.jsdelivr.net/gh/josephgg/source@main/tvbox/api/all.json
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
| 内置爬虫 `csp_*` | +20 | 不用下载额外 jar，但依赖客户端类 |
| JS 爬虫 | +8 | 要起 JS 运行时并下载脚本，最慢也最易失效 |
| 无需 jar / jar / js,zip | +8 / +3 / +1 | 免下载的打开更快 |
| 名称含影视类词 | +10 | 影视、电影、剧集、动漫、采集、资源、4K… |
| 名称含工具类词 | −22 | MV、音乐、网盘、搜索、磁力、直播、豆瓣、央视… |
| 接口探活通过 | +20 | 构建时真请求一次 `api?ac=list`，有 `class` 返回才算通 |
| 跨源被收录 | +3/源（上限 +6） | 多个源都用同一后端，说明它在多方验证下活着 |
| 爬虫文件 404 | −80 | 脚本都没了，打开必然失败 |
| 未参与聚合搜索 | −6 | 看得到但搜不到，优先级略降 |

两个探活都**只加分或只沉底，不删站点**：`probe_spider` 只把 404/410 判死（网络异常不算），`probe_cms` 不通不扣分——GitHub 海外 runner 连不上国内域名时，排序会退化成纯启发式，而不是把可用站点误杀。当前结果见 `report.md` 的「站点排序（前 20）」。

精选仓在此基础上做四件事（`pick_lite`）：

1. **一个资源库只留一个入口**：HTTP 采集站按 api 主机名归并（`lib_key`）；`csp_` 站点同一个爬虫类会被几十个站复用，所以按「类名 + ext」才算一个库（`lib_of`）。某库的最佳代表因单源上限进不来时，会自动换用该库下一个来源的代表——否则会出现「最好的库被同作者的系列站挤掉」。
2. **类目配额**：名额按 `CATEGORY_QUOTA` 分到各内容类型，类目由**站名信号优先**判定（「魔都┃动漫」才是动漫站），分类清单兜底。上一版只看清单，而几乎所有 CMS 的清单里都同时有「电影片」和「动漫片」，结果 80% 的综合库被误判成动漫站。
3. **单源上限**：同一顶层源最多 `lite_per_source` 个（多仓按父源算），避免一家吃满；小众类目（少儿/戏曲/综艺/纪录片/音乐）豁免，否则这部分会被主流源挤空。同一作者的系列站（分享U酷/分享最大/分享猫眼…）同类目最多 3 个。
4. **站名重写**：客户端看到的是 `类目·品牌`（`影视·量子`、`4K·小盒`、`短剧·旺旺`），去掉来源前缀、emoji 和「采集/纯净/多线」这类营销词。取不到可读站名的匿名 jar 站按类目编字母（`戏曲·A`）。**`key` 不变**，改的只是显示名，收藏和播放历史不受影响。

`all.json` 仍保留「源前缀·原名」，方便排查「这个站是谁给的」；`lite.json` 是给用户看的成品，两者刻意不同名。

## 为什么不是直接配「多仓地址」

FongMi 的 `urls` 多仓**既不是资源合并，也不是选择器**。源码 `VodConfig.parseDepot()` 只有三步：

1. 把 `urls` 里每一项转成 `Config`；
2. `load(configs.get(0))` —— **只加载第一条**，其余直接丢弃（`completeLoad()` 里只有这一条会 `update()` 入库）；
3. `Config.delete(config.getUrl())` —— 把多仓地址本身从库里删掉。

所以配 `index.json` 等价于配它排在第一的那条（当前是 `all.json`），既不能选也不能切换。要用分仓就直接填分仓地址；`index.json` 只对带仓库选择器的客户端（如 TVBox 原版）有意义。要实现「一个地址装下所有资源」，只能在**构建期合并**，也就是本目录做的事。

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
├── tools/relite.py     离线预览精选仓（直接复用 build.py 的规则，不用重新抓源）
├── tools/probe_search.py   实测各站搜索质量：命中率 / wd 是否生效 / 成人内容
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
python build.py && python tools/validate.py
```

`build` 段可调参数：

| 键 | 默认 | 作用 |
| --- | --- | --- |
| `lite_size` | 72 | 精选仓站点数 |
| `lite_per_source` | 5 | 精选仓每个顶层源的站点上限 |
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
- **是不是 JSON**：不是 JSON 说明客户端也解析不了 → 关搜索
- **成人特征词**：命中即剔除

```bash
cd tvbox
python tools/probe_search.py                            # 测 api/lite.json，写 search_quality.json
python tools/probe_search.py --file api/all.json --workers 16
```

构建时自动读 `search_quality.json`：`disable` / `quick_off` / `adult` 三种动作分别处置；`build.block_hosts` 里的域名无条件剔除（换 key 也拦得住）。

**一个后端只认一个入口**：同一个 CMS 后端常被几十个源收录，key 和 api 写法各不相同（尾斜杠、`?ac=list`、`/from/xxx`）。质检结论先按 `key` 精确匹配，再用 `api_norm()` 归一化匹配，覆盖同后端的其他入口——否则只关掉测过的那一个，剩下几十个照样在搜索里捣乱。

## 已知限制

- **源站会失效。** 构建只保证产物结构合法、链接可达，不代表每个站点的爬虫都能取到内容。`report.md` 记录每个源的抓取状态。
- **同名站点会并存。** 不同源提供的「同一个」站点接口实现往往不同，去重只认完全一致的 `api + ext`，其余按不同站点保留。
- **图片化与加密配置。** 部分源把配置伪装成 `.jpg/.png`，或返回 `2423` 开头的 AES-CBC 密文体。后者构建器已内置解密（依赖 `cryptography`）；前者能直接下载，但内容若是真图片则无法解析，记为抓取失败。
- **CDN 有缓存。** jsDelivr 对 `@main` 最长缓存 12 小时，workflow 推送后会主动调用 purge 接口清理；若手机端仍拿到旧配置，把地址里的 `@main` 换成具体 commit hash 即可锁版。
- **站点数量多 ≠ 加载慢，但会让聚合搜索变慢。** 配置原文约 1.1 MB、gzip 后约 170 KB；`VodConfig.initSite()` 只做本地反序列化，`BaseLoader.parseJar()` 也只登记 jar 的 md5，真正的 `DexClassLoader` 等点进站点才加载，首页只加载 `home` 一个站点——所以 3400 站的启动开销仍在百毫秒量级。真正的代价在聚合搜索：`CollectActivity` 把所有 `searchable` 站点一次性提交给 `Task.largeExecutor()`（`newFixedThreadPool(20)`，单站超时 30 s），当前约 2900 个可搜站点，意味着 **145 轮排队**，全量搜索会明显变慢。日常建议直接用 `api/lite.json`（72 站，约 4 轮），或在搜索页先勾选常用站点再搜。
- **站点列表长。** 3400 项靠 RecyclerView 回收，滑动不卡，但翻找费劲；直接配 `api/lite.json` 只有 72 个，或在「站点管理」里收藏常用站点。
- **排序是启发式，不是评测。** 除了 `probe_cms` 那 82 个采集接口是真请求验过，其余维度（类型、词表、跨源收录）都是经验规则。实测前 40 名里有一半采集接口当时打不通，加探活后头部才变成真能出内容的站点；但「能搜到内容」仍不等于「片源清晰、更新及时」，这部分没法离线判断。

## 免责声明

本项目只做配置的抓取、去重与格式转换，不托管、不转存任何影视内容，所有资源来自第三方公开接口。请自行判断使用场景的合规性。
