# 聚合影视仓

面向 [FongMi/TV](https://github.com/FongMi/TV)（影视仓）的多源聚合配置。把多个公开影视仓的接口抓下来、去重、合并成一份配置，APP 里只填一个地址就能用上全部站点的资源。

本目录是 `josephgg/source` 仓的 `tvbox/` 子目录，与仓库根目录的 IPTV 直播源互不影响。

## 直接使用

APP「设置 → 配置地址」填（主地址，CDN）：

```
https://fastly.jsdelivr.net/gh/josephgg/source@main/tvbox/api/all.json
```

备用地址，主地址拉不动时换着试：

```
https://cdn.jsdelivr.net/gh/josephgg/source@main/tvbox/api/all.json
https://raw.githubusercontent.com/josephgg/source/main/tvbox/api/all.json
https://gh-proxy.com/https://raw.githubusercontent.com/josephgg/source/main/tvbox/api/all.json
https://ghfast.top/https://raw.githubusercontent.com/josephgg/source/main/tvbox/api/all.json
```

完整清单见 `mirrors.txt`（构建时自动生成）。

想在 APP 内切换仓库而不是一次加载全部，改配多仓索引：

```
https://fastly.jsdelivr.net/gh/josephgg/source@main/tvbox/index.json
```

## 为什么不是直接配「多仓地址」

FongMi 的 `urls` 多仓**不是资源合并，而是仓选择器**。源码 `VodConfig.parseDepot()` 的行为是：

1. 读到 `urls` 后把列表展示给你选；
2. 选中某个仓后，加载该仓的完整配置；
3. 然后 `Config.delete(config.getUrl())` —— 把多仓地址从数据库里删掉。

所以多仓只能让你在几个仓之间切换，不能把几家的站点放进同一个列表。要实现「一个地址装下所有资源」，只能在**构建期合并**，也就是本目录做的事。

合并能成立的前提是客户端支持多爬虫共存：`JarLoader` 内部用 `ConcurrentHashMap<String, DexClassLoader>` 按 jar 的 md5 缓存加载器，每个站点可以带自己的 `jar`。构建时会把源仓顶层的 `spider` 落到**每个站点**上，避免跨源继承失效。

## 目录结构

```
tvbox/
├── sources.json        唯一维护入口：源清单与构建参数
├── build.py            抓取 → 绝对化 → 去重 → 合并
├── tools/jsonc.py      宽松 JSON 解析（注释 / 尾逗号 / base64 / AES-CBC）
├── tools/validate.py   产物验收：结构约束 + 抽样探活
├── api/all.json        总聚合仓（APP 填这个）
├── api/src-<id>.json   各源单仓快照（排查用）
├── index.json          FongMi 多仓索引
├── status.json         机器可读构建状态
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
- **站点数量多。** 当前合并后约 1000 个站点，站点管理页会比较长；首页只加载 `home` 那一个，不影响启动速度。

## 免责声明

本项目只做配置的抓取、去重与格式转换，不托管、不转存任何影视内容，所有资源来自第三方公开接口。请自行判断使用场景的合规性。
