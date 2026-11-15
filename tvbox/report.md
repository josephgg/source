# 构建报告

生成时间：2026-11-15T17:45:17+08:00

| 指标 | 数值 |
| --- | --- |
| 合并后站点数 | 3967 |
| 参与聚合搜索 | 3444 |
| 稳定精选站点数 | 14 |
| 实体剔除确认失效站 | 603 |
| 解析源数量 | 36 |
| 直播源数量 | 12 |
| 跨源去重丢弃 | 3211 |
| 爬虫文件失效 | 24 |
| 搜索实测：关搜索 | 41 |
| 搜索实测：仅关快速搜索 | 10 |
| 剔除：成人内容 | 0 |
| 剔除：域名黑名单 | 3 |
| 剔除：本机代理地址 | 9 |

## 稳定精选实测证据

仅保留最近 36 小时内连续两轮通过的源；HLS 抽检首/中/尾分片，直链校验媒体签名。

| 站点 | 类型 | 连续通过 | 分片抽检 | 抽检字节 | 耗时 |
| --- | --- | --- | --- | --- | --- |
| 影视·百度 | ok | 6 轮 | 3/1309 | 505720 | 8285ms |
| 影视·虎牙 | ok | 6 轮 | 3/625 | 1055472 | 9531ms |
| 影视·360 | ok | 6 轮 | 3/958 | 911648 | 10471ms |
| 影视·无尽 | ok | 6 轮 | 3/3633 | 810656 | 8299ms |
| 影视·天堂 | ok | 6 轮 | 3/681 | 2374440 | 11063ms |
| 影视·如意 | ok | 6 轮 | 3/40 | 3336812 | 11638ms |
| 影视·优质 | ok | 6 轮 | 3/669 | 2341352 | 11340ms |
| 影视·分享猫眼 | ok | 6 轮 | 3/477 | 2669488 | 3924ms |
| 影视·飘零天涯 | ok | 6 轮 | 3/3633 | 810656 | 7949ms |
| 影视·分享魔都 | ok | 3 轮 | 3/20 | 2200164 | 10650ms |
| 影视·巨量 | ok | 6 轮 | 3/92 | 1974940 | 10095ms |
| 影视·A | ok | 6 轮 | 3/970 | 2574352 | 12632ms |
| 影视·仓 | ok | 6 轮 | 3/337 | 4767079 | 6179ms |
| 动漫·魔都 | ok | 3 轮 | 3/20 | 2200164 | 9352ms |

## 各源状态

| 源 | 站点 | 新增 | 耗时 | 状态 |
| --- | --- | --- | --- | --- |
| 高天流云 | 298 | 295 | 385ms | OK |
| 老刘备 | 234 | 229 | 375ms | OK |
| 分享者 | 168 | 164 | 416ms | OK |
| 王二小放牛娃 | 63 | 61 | 798ms | OK |
| 香雅晴 | 48 | 45 | 289ms | OK |
| 短剧专线 | 35 | 35 | 201ms | OK |
| 俊佬 | 24 | 23 | 89ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃饭太硬线路 | - | 0 | 585ms | 失败：ValueError: not json | head=����..JFIF..........��.�............ . . .... ................!...!.1&""&18/-/8D==DVQVpp�........... |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃肥猫线路 | - | 0 | 585ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃摸鱼线路 | 111 | 109 | 585ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃王二小线路 | 63 | 0 | 585ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃短剧专线 | 35 | 0 | 585ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃儿童专线 | - | 0 | 585ms | 失败：ValueError: not json | head=�PNG  . ... IHDR...x...�.....����....sRGB.��.�....sBIT....|.d�.. .IDATx���Y�e�u��[{8Ýr�.3@....��lY�Z |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃饭太硬备用 | - | 0 | 585ms | 失败：ValueError: not json | head=����..JFIF..........��.�............ . . .... ................!...!.1&""&18/-/8D==DVQVpp�........... |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃肥猫备用（失效） | 41 | 35 | 585ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃摸鱼备用 | 111 | 0 | 585ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃王二小备用 | 100 | 91 | 585ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃饭太硬线路 | - | 0 | 585ms | 失败：ValueError: not json | head=����..JFIF..........��.�............ . . .... ................!...!.1&""&18/-/8D==DVQVpp�........... |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃肥猫线路 | - | 0 | 585ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃摸鱼线路 | 111 | 0 | 585ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃王二小线路 | 63 | 0 | 585ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃短剧专线 | 35 | 0 | 585ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃儿童专线 | - | 0 | 585ms | 失败：ValueError: not json | head=�PNG  . ... IHDR...x...�.....����....sRGB.��.�....sBIT....|.d�.. .IDATx���Y�e�u��[{8Ýr�.3@....��lY�Z |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃俊佬线路 | 24 | 0 | 585ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃老刘备线路 | 234 | 0 | 585ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃分享者线路 | 168 | 1 | 585ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃高天流云线路 | 298 | 1 | 585ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃香雅晴线路 | 48 | 0 | 585ms | OK |
| 肥猫 | 41 | 1 | 977ms | OK |
| 饭太硬 | 49 | 47 | 212ms | OK |
| 小米 | 36 | 27 | 250ms | OK |
| 肥猫(iptv) | 61 | 37 | 226ms | OK |
| 菜妮丝 | 104 | 85 | 298ms | OK |
| 王二小(iptv) | 86 | 26 | 232ms | OK |
| 小虎斑 | 88 | 85 | 229ms | OK |
| 摸鱼儿 | 107 | 81 | 249ms | OK |
| PG | 106 | 91 | 285ms | OK |
| 欧歌 | 106 | 72 | 264ms | OK |
| 潇洒 | 160 | 105 | 235ms | OK |
| 天微 | 97 | 77 | 276ms | OK |
| 天天开心 | 126 | 90 | 458ms | OK |
| 香雅情(iptv) | 55 | 39 | 235ms | OK |
| 南风 | 78 | 56 | 331ms | OK |
| 骚零 | 37 | 17 | 273ms | OK |
| 白嫖 | 9 | 8 | 189ms | OK |
| OK | 76 | 71 | 344ms | OK |
| 戏曲音乐 | 10 | 10 | 273ms | OK |
| 短剧频道 | 35 | 33 | 322ms | OK |
| 少儿频道 | 30 | 30 | 261ms | OK |
| 动漫频道 | 19 | 16 | 239ms | OK |
| iptv365直播 | 4 | 4 | 311ms | OK |
| 老刘备(liucn) | 234 | 142 | 280ms | OK |
| 小马 | 62 | 35 | 101ms | OK |
| 创享影视 | 12 | 12 | 695ms | OK |
| 影仓 | 37 | 29 | 115ms | OK |
| 小盒子单仓 | 54 | 34 | 1054ms | OK |
| 小盒子4K | 53 | 35 | 632ms | OK |
| 小盒子多仓 / 🚀小盒子 | 54 | 0 | 5565ms | OK |
| 小盒子多仓 / 🐔肥猫 | - | 0 | 5565ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 小盒子多仓 / 🐟 摸 鱼 | - | 0 | 5565ms | 失败：URLError: <urlopen error [WinError 10060] 由于连接方在一段时间后没有正确答复或连接的主机没有反应，连接尝试失败。> |
| 小盒子多仓 / 🍯毒盒 | - | 0 | 5565ms | 失败：URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| 小盒子多仓 / 🍯PG线路 | - | 0 | 5565ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html> <html class="devise-layout-html"> <head prefix="og: http://ogp.me/ns#"> <meta charse |
| 小盒子多仓 / 🍯影视仓 | - | 0 | 5565ms | 失败：HTTPError: HTTP Error 401:  |
| 小盒子多仓 / 🦆神仙线路 | - | 0 | 5565ms | 失败：URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| 小盒子多仓 / 🦆俊于 | 24 | 0 | 5565ms | OK |
| 小盒子多仓 / 😹影视资源 | - | 0 | 5565ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html> <html><head> .<meta name="robots" content="noarchive">     <meta http-equiv="Content |
| 小盒子多仓 / 😹玄珠 | - | 0 | 5565ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 小盒子多仓 / 😹吾爱 | - | 0 | 5565ms | 失败：URLError: <urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。> |
| 小盒子多仓 / 😹动漫城 | 27 | 23 | 5565ms | OK |
| 小盒子多仓 / 🚀喵影视 | - | 0 | 5565ms | 失败：URLError: <urlopen error [Errno 11002] getaddrinfo failed> |
| 小盒子多仓 / 🚀摸鱼 | - | 0 | 5565ms | 失败：URLError: <urlopen error [WinError 10060] 由于连接方在一段时间后没有正确答复或连接的主机没有反应，连接尝试失败。> |
| 小盒子多仓 / 🚀小马 | 62 | 0 | 5565ms | OK |
| 小盒子多仓 / 🦉飘零 | - | 0 | 5565ms | 失败：URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| 小盒子多仓 / 🐹dxawi | 48 | 14 | 5565ms | OK |
| 小盒子多仓 / 🍯HG | 10 | 6 | 5565ms | OK |
| 拾光多仓 / SVIP📚在线 | 246 | 201 | 1867ms | OK |
| 拾光多仓 / 备用📚在线 | - | 0 | 1867ms | 失败：URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| 拾光多仓 / VIP📚在线 | 246 | 154 | 1867ms | OK |
| 拾光多仓 / 小米📚在线 | - | 0 | 1867ms | 失败：URLError: <urlopen error [Errno 11002] getaddrinfo failed> |
| 拾光多仓 / 动漫城📚在线 | 27 | 0 | 1867ms | OK |
| 拾光多仓 / 喵影视📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 小脑斧📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 401:  |
| 拾光多仓 / 小虎斑📚在线 | 117 | 115 | 1867ms | OK |
| 拾光多仓 / 潇洒📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 404:  |
| 拾光多仓 / 肥猫📚在线 | - | 0 | 1867ms | 失败：URLError: <urlopen error [WinError 10060] 由于连接方在一段时间后没有正确答复或连接的主机没有反应，连接尝试失败。> |
| 拾光多仓 / 欧歌📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 拾光多仓 / 乐哥📚在线 | - | 0 | 1867ms | 失败：URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| 拾光多仓 / 老虎📚在线 | - | 0 | 1867ms | 失败：URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| 拾光多仓 / Clun📚在线 | 101 | 84 | 1867ms | OK |
| 拾光多仓 / O  K📚在线 | - | 0 | 1867ms | 失败：URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| 拾光多仓 / 俊佬📚在线 | 24 | 0 | 1867ms | OK |
| 拾光多仓 / 短剧📚在线 | - | 0 | 1867ms | 失败：URLError: <urlopen error [WinError 10060] 由于连接方在一段时间后没有正确答复或连接的主机没有反应，连接尝试失败。> |
| 拾光多仓 / 驸马📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 南风📚在线 | 93 | 82 | 1867ms | OK |
| 拾光多仓 / 二小📚在线 | 63 | 0 | 1867ms | OK |
| 拾光多仓 / 毒盒📚在线 | - | 0 | 1867ms | 失败：URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| 拾光多仓 / 心魔📚在线 | 151 | 142 | 1867ms | OK |
| 拾光多仓 / D佬📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 401:  |
| 拾光多仓 / 小马📚在线 | 62 | 0 | 1867ms | OK |
| 拾光多仓 / 星辰📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 拾光多仓 / 龙伊📚在线 | - | 0 | 1867ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html> <html lang="en"> .<head> ..<meta name="360-analysis-id" content="1k1c1k1e39331c2v">  |
| 拾光多仓 / 寳盒📚在线 | 77 | 67 | 1867ms | OK |
| 拾光多仓 / 挺好📚在线 | 46 | 22 | 1867ms | OK |
| 拾光多仓 / 传说📚在线 | - | 0 | 1867ms | 失败：URLError: <urlopen error [WinError 10054] 远程主机强迫关闭了一个现有的连接。> |
| 拾光多仓 / 多多📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 分享📚在线 | - | 0 | 1867ms | 失败：ValueError: not json | head={ // 每日一言 (随机显示欢迎语) "dairyWords": [{     "name": "rating",     "request": {      "method": "GET",    |
| 拾光多仓 / 蓝天📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 423: Locked |
| 拾光多仓 / 青龙📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 423: Locked |
| 拾光多仓 / 黄金📚在线 | - | 0 | 1867ms | 失败：ValueError: not json | head=�PNG  . ... IHDR...�...�......�1?....sRGB.��.�....sBIT....|.d�.. .IDATx��I�e�u����Ϲ��/��l.I�4�T�T.<� |
| 拾光多仓 / 道长📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / PG📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 拾光多仓 / 真訫📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 拾光多仓 / 琉芸📚在线 | - | 0 | 1867ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html> <html class="devise-layout-html"> <head prefix="og: http://ogp.me/ns#"> <meta charse |
| 拾光多仓 / 月光📚在线 | 77 | 1 | 1867ms | OK |
| 拾光多仓 / 雷霆📚在线 | 1063 | 1045 | 1867ms | OK |
| 拾光多仓 / 小凯📚在线 | 28 | 15 | 1867ms | OK |
| 拾光多仓 / 公子📚在线 | - | 0 | 1867ms | 失败：URLError: <urlopen error [WinError 10060] 由于连接方在一段时间后没有正确答复或连接的主机没有反应，连接尝试失败。> |
| 拾光多仓 / 短剧📚在线 | - | 0 | 1867ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd"> <h |
| 拾光多仓 / 特别📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 蜂蜜📚在线 | - | 0 | 1867ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html>  <html lang="en">  <head>      <meta charset="UTF-8">      <meta name="viewport" con |
| 拾光多仓 / 传说📚在线 | - | 0 | 1867ms | 失败：ValueError: not json | head=.//资源来自网络，南风的jar加上其他大神资源，介意请联系删除。  {  "sites":[          {"key":"t42直播转点播","name":"♥️Q群621399056","t |
| 拾光多仓 / 多多📚在线 | - | 0 | 1867ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<html> <head><title>404 Not Found</title></head> <body> <center><h1>404 Not Found</h1></center> <hr> |
| 拾光多仓 / 刺刺📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 404:  |
| 拾光多仓 / 剧场📚在线 | - | 0 | 1867ms | 失败：URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| 拾光多仓 / 听书📚在线 | - | 0 | 1867ms | 失败：URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| 拾光多仓 / CandyMu📚在线 | 64 | 57 | 1867ms | OK |
| 拾光多仓 / 欧歌备用📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 各种网盘📚在线 | - | 0 | 1867ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 请勿贩卖📚在线 | 19 | 18 | 1867ms | OK |
| 挺好分享多仓 / 📛挺好分享 | 46 | 0 | 3116ms | OK |
| 挺好分享多仓 / 🍳挺好丨讴歌线路 | - | 0 | 3116ms | 失败：ConnectionResetError: [WinError 10054] 远程主机强迫关闭了一个现有的连接。 |
| 挺好分享多仓 / 🐯小虎斑线路 | 117 | 0 | 3116ms | OK |
| 挺好分享多仓 / 🚀One线路 | - | 0 | 3116ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!-- 302202102975 --> <!DOCTYPE html> <html lang="en"> <head>     <meta charset="utf-8">     <meta n |
| 挺好分享多仓 / 🚀南风线路 | - | 0 | 3116ms | 失败：URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| 挺好分享多仓 / 🚀刘伟线路 | - | 0 | 3116ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html> <html class="devise-layout-html"> <head prefix="og: http://ogp.me/ns#"> <meta charse |
| 挺好分享多仓 / 🚀剪影线路 | - | 0 | 3116ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html> <html class="devise-layout-html"> <head prefix="og: http://ogp.me/ns#"> <meta charse |
| 挺好分享多仓 / 🚀讴歌线路 | - | 0 | 3116ms | 失败：ConnectionResetError: [WinError 10054] 远程主机强迫关闭了一个现有的连接。 |
| 挺好分享多仓 / 🚀小虎斑线 | - | 0 | 3116ms | 失败：URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| 挺好分享多仓 / 🚀小米线路 | - | 0 | 3116ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 挺好分享多仓 / 🚀王二小线 | 63 | 0 | 3116ms | OK |
| 挺好分享多仓 / 🚀潇洒专线 | - | 0 | 3116ms | 失败：HTTPError: HTTP Error 404:  |
| 挺好分享多仓 / 🚀摸鱼线路 | - | 0 | 3116ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!-- 927641808700 --> <!DOCTYPE html> <html lang="en"> <head>     <meta charset="utf-8">     <meta n |
| 挺好分享多仓 / 🚀环宇轩线 | - | 0 | 3116ms | 失败：HTTPError: HTTP Error 401:  |
| 挺好分享多仓 / 🚀小苹果线 | - | 0 | 3116ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 挺好分享多仓 / 🚀驸马线路 | - | 0 | 3116ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 挺好分享多仓 / 🚀拾光线路 | - | 0 | 3116ms | 失败：HTTPError: HTTP Error 401:  |
| 挺好分享多仓 / 🚀宝盒线路 | - | 0 | 3116ms | 失败：URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| 挺好分享多仓 / 🚀小马线路 | 62 | 0 | 3116ms | OK |
| 挺好分享多仓 / 🚀俊佬在线 | 24 | 0 | 3116ms | OK |
| 挺好分享多仓 / 🚀分享者线 | - | 0 | 3116ms | 失败：ValueError: not json | head={ // 每日一言 (随机显示欢迎语) "dairyWords": [{     "name": "rating",     "request": {      "method": "GET",    |
| 挺好分享多仓 / 🚀老刘线路 | - | 0 | 3116ms | 失败：URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| 挺好分享多仓 / 🚀传说线路 | - | 0 | 3116ms | 失败：URLError: <urlopen error [WinError 10054] 远程主机强迫关闭了一个现有的连接。> |
| 挺好分享多仓 / 🚀蓝天线路 | - | 0 | 3116ms | 失败：HTTPError: HTTP Error 423: Locked |
| 挺好分享多仓 / 🚀高天流云 | 298 | 0 | 3116ms | OK |
| 挺好分享多仓 / 🚀俊佬线路 | 24 | 0 | 3116ms | OK |
| 挺好分享多仓 / 🚀毒盒线路 | - | 0 | 3116ms | 失败：URLError: <urlopen error [Errno 11001] getaddrinfo failed> |
| 挺好分享多仓 / 📛公众号丨挺好分享 | - | 0 | 3116ms | 失败：URLError: <urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。> |
| 挺好分享多仓 / 🌠公众号丨挺好专享 | - | 0 | 3116ms | 失败：URLError: <urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。> |
| 挺好分享多仓 / 🚀青龙影线 | - | 0 | 3116ms | 失败：HTTPError: HTTP Error 423: Locked |
| 挺好分享多仓 / 🍨饭硬专线 | - | 0 | 3116ms | 失败：ValueError: not json | head=����..JFIF..........��.�............ . . .... ................!...!.1&""&18/-/8D==DVQVpp�........... |
| 挺好分享多仓 / 🚀短剧大全 | - | 0 | 3116ms | 失败：URLError: <urlopen error [WinError 10060] 由于连接方在一段时间后没有正确答复或连接的主机没有反应，连接尝试失败。> |
| tvbox-probe 精选 | 104 | 17 | 158ms | OK |
| ysc-api 聚合 | 52 | 44 | 180ms | OK |
| 酒店电视 | 8 | 0 | 146ms | OK |

> 70 个站点的爬虫文件返回 404/410，已移出聚合搜索（仍可在站点列表中打开）。

## 站点排序（前 20，即首页与列表头部）

| # | 站点 | 分数 | 依据 |
| --- | --- | --- | --- |
| 1 | 老刘·🎏百度┃采集 | 108.0 | http+34 影视+10 4源+6 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 2 | 老刘·🐯虎牙采集 | 108.0 | http+34 影视+10 3源+6 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 3 | 拾光·360｜采集 | 104.0 | http+34 影视+10 3源+6 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 4 | 拾光·无尽｜采集 | 104.0 | http+34 影视+10 3源+6 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 5 | 欧歌·🤣魔都┃动漫 | 104.0 | http+34 影视+10 3源+6 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 6 | OK·🎞️天堂┃采集 | 104.0 | http+34 影视+10 5源+6 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 7 | 拾光·如意｜采集 | 101.0 | http+34 影视+10 2源+3 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 8 | 拾光·❤光速资源 | 98.0 | http+34 影视+10 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 9 | 拾光·❤无尽资源 | 98.0 | http+34 影视+10 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 10 | 拾光·创享 | 采集 | 98.0 | http+34 影视+10 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 11 | 创享·🌟 创享影视 | 97.0 | http+34 无jar+8 影视+10 搜索精准+12 播放实测通过+8 接口通+20 |
| 12 | 分享·💖分享卫士 | 95.5 | http+34 5源+6 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 13 | 拾光·优质 | 采集 | 95.0 | http+34 影视+10 搜索精准+12 播放实测通过+8 接口通+20 较快+3 |
| 14 | 影仓·🍀┃如意┃资源 | 95.0 | http+34 影视+10 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 15 | 分享·💖分享如意 | 92.5 | http+34 2源+3 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 16 | 分享·💝分享猫眼 | 92.5 | http+34 2源+3 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 17 | 分享·🥀飘零天涯 | 92.5 | http+34 2源+3 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 18 | 小马·百度 | 91.0 | http+34 4源+6 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 19 | 分享·💝分享百度 | 89.5 | http+34 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 20 | 分享·💝分享魔都 | 89.5 | http+34 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |

排序口径：接口类型 + jar 成本 + 跨源收录 + CMS 探活/速度 + 搜索实测 − 工具类站点 − 搜索杂乱 − 爬虫失效，同分按源优先级。首页另需三类覆盖。
