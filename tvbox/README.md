# 聚合影视仓

面向 [FongMi/TV](https://github.com/FongMi/TV)（影视仓）的多源聚合配置。把多个公开影视仓的接口抓下来、去重、合并成一份配置，APP 里只填一个地址就能用上全部站点的资源。

本目录是 `josephgg/source` 仓的 `tvbox/` 子目录，与仓库根目录的 IPTV 直播源互不影响。

## 直接使用

三个仓，按需要选一个填进 APP「设置 → 配置地址」：

| 仓 | 地址后缀 | 站点 | 适合 |
| --- | --- | --- | --- |
| 精选（推荐） | `api/lite.json` | 160 | 列表短、聚合搜索快，每源保底 3 个，接口已验证 |
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

精选仓在此基础上加一条：**每个顶层源保底 3 个**（`build.lite_per_source`），剩余按分数补满。否则采集站多的源会霸榜（实测纯按分数取时高天源被挤到 0 个）；多仓源按**父源**算配额，不然一个 54 子仓的源会吃满 54 份。

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
├── api/lite.json       精选仓（160 站，按质量分 + 每源保底）
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
| `lite_size` | 160 | 精选仓站点数 |
| `lite_per_source` | 3 | 精选仓每（顶层）源保底个数 |
| `override` | 无 | 固定 `name` / `notice` / `wallpaper` / `logo`，覆盖各源自带的值；写空串等于删掉该字段 |
| `probe_spider` | true | 构建时探活 jar/js 爬虫文件，404/410 的站点移出聚合搜索并沉底 |
| `probe_cms` | true | 构建时探活 CMS 采集接口（`api?ac=list`），通了的加分 |
| `cms_timeout` | 12 | CMS 探活超时（秒） |
| `min_retain_ratio` | 0.85 | 站点数低于上轮的 85% 就中止，不覆盖旧产物 |

## 直播源

仓库根目录的 `iptv_filtered.m3u` 除原有的央视/卫视清单外，还会并入各影视仓配置里的 `lives` 频道：

```bash
cd tvbox
python tools/mix_lives.py --refresh --write
```

规则：现有条目不动、只追加到末尾；频道名规范化后去重（`CCTV-1 高清` 与 `CCTV1` 视为同一台）；**每条线路真探活**——IPTV 源死链率极高，实测 1263 条线路只有 166 台存活，不探活等于往播放列表里灌垃圾；央视 > 卫视 > 港澳台 > 地方台，每台最多 2 条线路，且忽略 `?id=` / `?token=` 这类同流变体。写入前自动备份 `iptv_filtered.m3u.bak`。

不加 `--write` 只统计不改文件，可以先看能并入多少。

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

## 已知限制

- **源站会失效。** 构建只保证产物结构合法、链接可达，不代表每个站点的爬虫都能取到内容。`report.md` 记录每个源的抓取状态。
- **同名站点会并存。** 不同源提供的「同一个」站点接口实现往往不同，去重只认完全一致的 `api + ext`，其余按不同站点保留。
- **图片化与加密配置。** 部分源把配置伪装成 `.jpg/.png`，或返回 `2423` 开头的 AES-CBC 密文体。后者构建器已内置解密（依赖 `cryptography`）；前者能直接下载，但内容若是真图片则无法解析，记为抓取失败。
- **CDN 有缓存。** jsDelivr 对 `@main` 最长缓存 12 小时，workflow 推送后会主动调用 purge 接口清理；若手机端仍拿到旧配置，把地址里的 `@main` 换成具体 commit hash 即可锁版。
- **站点数量多 ≠ 加载慢，但会让聚合搜索变慢。** 配置原文约 1.1 MB、gzip 后约 170 KB；`VodConfig.initSite()` 只做本地反序列化，`BaseLoader.parseJar()` 也只登记 jar 的 md5，真正的 `DexClassLoader` 等点进站点才加载，首页只加载 `home` 一个站点——所以 3400 站的启动开销仍在百毫秒量级。真正的代价在聚合搜索：`CollectActivity` 把所有 `searchable` 站点一次性提交给 `Task.largeExecutor()`（`newFixedThreadPool(20)`，单站超时 30 s），当前约 2900 个可搜站点，意味着 **145 轮排队**，全量搜索会明显变慢。日常建议直接用 `api/lite.json`（160 站，约 8 轮），或在搜索页先勾选常用站点再搜。
- **站点列表长。** 3400 项靠 RecyclerView 回收，滑动不卡，但翻找费劲；直接配 `api/lite.json` 只有 150 个，或在「站点管理」里收藏常用站点。
- **排序是启发式，不是评测。** 除了 `probe_cms` 那 82 个采集接口是真请求验过，其余维度（类型、词表、跨源收录）都是经验规则。实测前 40 名里有一半采集接口当时打不通，加探活后头部才变成真能出内容的站点；但「能搜到内容」仍不等于「片源清晰、更新及时」，这部分没法离线判断。

## 免责声明

本项目只做配置的抓取、去重与格式转换，不托管、不转存任何影视内容，所有资源来自第三方公开接口。请自行判断使用场景的合规性。
