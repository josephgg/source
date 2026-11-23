# 构建报告

生成时间：2026-11-23T18:10:45+08:00

| 指标 | 数值 |
| --- | --- |
| 合并后站点数 | 4173 |
| 参与聚合搜索 | 3606 |
| 稳定精选站点数 | 6 |
| 实体剔除确认失效站 | 704 |
| 解析源数量 | 36 |
| 直播源数量 | 12 |
| 跨源去重丢弃 | 3037 |
| 爬虫文件失效 | 24 |
| 搜索实测：关搜索 | 39 |
| 搜索实测：仅关快速搜索 | 0 |
| 剔除：成人内容 | 0 |
| 剔除：域名黑名单 | 2 |
| 剔除：本机代理地址 | 9 |

## 稳定精选实测证据

仅保留最近 36 小时内连续两轮通过的源；HLS 抽检首/中/尾分片，直链校验媒体签名。

| 站点 | 类型 | 连续通过 | 分片抽检 | 抽检字节 | 耗时 |
| --- | --- | --- | --- | --- | --- |
| 影视·360 | ok | 12 轮 | 3/958 | 911648 | 9720ms |
| 影视·创享 | ok | 9 轮 | 3/625 | 1055472 | 5894ms |
| 影视·ikun | ok | 21 轮 | 3/1466 | 1300960 | 1678ms |
| 影视·分享魔都 | ok | 24 轮 | 3/20 | 2200164 | 2550ms |
| 动漫·魔都 | ok | 24 轮 | 3/20 | 2200164 | 2553ms |
| 动漫·仓腾讯B站 | ok | 27 轮 | 3/337 | 4767079 | 8588ms |

## 各源状态

| 源 | 站点 | 新增 | 耗时 | 状态 |
| --- | --- | --- | --- | --- |
| 高天流云 | 298 | 295 | 294ms | OK |
| 老刘备 | 234 | 229 | 323ms | OK |
| 分享者 | 168 | 164 | 350ms | OK |
| 王二小放牛娃 | 99 | 98 | 2283ms | OK |
| 香雅晴 | 48 | 46 | 328ms | OK |
| 俊佬 | 24 | 23 | 2948ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃饭太硬线路 | - | 0 | 6528ms | 失败：ValueError: not json | head=����..JFIF..........��.�............ . . .... ................!...!.1&""&18/-/8D==DVQVpp�........... |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃肥猫线路 | 41 | 37 | 6528ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃摸鱼线路 | 109 | 105 | 6528ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃王二小线路 | 99 | 0 | 6528ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃短剧专线 | - | 0 | 6528ms | 失败：URLError: <urlopen error timed out> |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃儿童专线 | - | 0 | 6528ms | 失败：ValueError: not json | head=�PNG  . ... IHDR...x...�.....����....sRGB.��.�....sBIT....|.d�.. .IDATx���Y�e�u��[{8Ýr�.3@....��lY�Z |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃饭太硬备用 | - | 0 | 6528ms | 失败：ValueError: not json | head=����..JFIF..........��.�............ . . .... ................!...!.1&""&18/-/8D==DVQVpp�........... |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃肥猫备用 | 41 | 2 | 6528ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃摸鱼备用 | 109 | 0 | 6528ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃王二小备用 | 99 | 0 | 6528ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃饭太硬线路 | - | 0 | 6528ms | 失败：ValueError: not json | head=����..JFIF..........��.�............ . . .... ................!...!.1&""&18/-/8D==DVQVpp�........... |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃肥猫线路 | 41 | 0 | 6528ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃摸鱼线路 | 109 | 0 | 6528ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃王二小线路 | 99 | 0 | 6528ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃短剧专线 | - | 0 | 6528ms | 失败：URLError: <urlopen error timed out> |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃儿童专线 | - | 0 | 6528ms | 失败：ValueError: not json | head=�PNG  . ... IHDR...x...�.....����....sRGB.��.�....sBIT....|.d�.. .IDATx���Y�e�u��[{8Ýr�.3@....��lY�Z |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃俊佬线路 | 24 | 0 | 6528ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃老刘备线路 | 234 | 142 | 6528ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃分享者线路 | 168 | 1 | 6528ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃高天流云线路 | 298 | 287 | 6528ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃香雅晴线路 | 48 | 35 | 6528ms | OK |
| 肥猫 | 41 | 0 | 3279ms | OK |
| 饭太硬 | 49 | 48 | 89ms | OK |
| 小米 | 36 | 27 | 75ms | OK |
| 肥猫(iptv) | 61 | 37 | 86ms | OK |
| 菜妮丝 | 104 | 85 | 234ms | OK |
| 王二小(iptv) | 86 | 77 | 93ms | OK |
| 小虎斑 | 88 | 85 | 115ms | OK |
| 摸鱼儿 | 107 | 81 | 344ms | OK |
| PG | 106 | 91 | 99ms | OK |
| 欧歌 | 106 | 72 | 96ms | OK |
| 潇洒 | 160 | 105 | 118ms | OK |
| 天微 | 97 | 77 | 106ms | OK |
| 天天开心 | 126 | 90 | 90ms | OK |
| 香雅情(iptv) | 55 | 39 | 96ms | OK |
| 南风 | 78 | 56 | 95ms | OK |
| 骚零 | 37 | 17 | 101ms | OK |
| 白嫖 | 9 | 8 | 62ms | OK |
| OK | 76 | 71 | 103ms | OK |
| 戏曲音乐 | 10 | 10 | 73ms | OK |
| 短剧频道 | 35 | 35 | 81ms | OK |
| 少儿频道 | 30 | 30 | 112ms | OK |
| 动漫频道 | 19 | 16 | 153ms | OK |
| iptv365直播 | 4 | 4 | 83ms | OK |
| 老刘备(liucn) | 234 | 142 | 290ms | OK |
| 小马 | 62 | 35 | 1251ms | OK |
| 创享影视 | 12 | 12 | 411ms | OK |
| 影仓 | 28 | 27 | 597ms | OK |
| 小盒子单仓 | 54 | 34 | 158ms | OK |
| 小盒子4K | 53 | 35 | 93ms | OK |
| 小盒子多仓 / 🚀小盒子 | 54 | 0 | 7592ms | OK |
| 小盒子多仓 / 🐔肥猫 | - | 0 | 7592ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 小盒子多仓 / 🐟 摸 鱼 | 109 | 0 | 7592ms | OK |
| 小盒子多仓 / 🍯毒盒 | - | 0 | 7592ms | 失败：URLError: <urlopen error [Errno -5] No address associated with hostname> |
| 小盒子多仓 / 🍯PG线路 | - | 0 | 7592ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 小盒子多仓 / 🍯影视仓 | - | 0 | 7592ms | 失败：HTTPError: HTTP Error 401:  |
| 小盒子多仓 / 🦆神仙线路 | - | 0 | 7592ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 小盒子多仓 / 🦆俊于 | 24 | 0 | 7592ms | OK |
| 小盒子多仓 / 😹影视资源 | - | 0 | 7592ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html> <html><head> .<meta name="robots" content="noarchive">     <meta http-equiv="Content |
| 小盒子多仓 / 😹玄珠 | - | 0 | 7592ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 小盒子多仓 / 😹吾爱 | - | 0 | 7592ms | 失败：URLError: <urlopen error timed out> |
| 小盒子多仓 / 😹动漫城 | 27 | 23 | 7592ms | OK |
| 小盒子多仓 / 🚀喵影视 | - | 0 | 7592ms | 失败：URLError: <urlopen error [Errno -3] Temporary failure in name resolution> |
| 小盒子多仓 / 🚀摸鱼 | 109 | 0 | 7592ms | OK |
| 小盒子多仓 / 🚀小马 | 62 | 0 | 7592ms | OK |
| 小盒子多仓 / 🦉飘零 | - | 0 | 7592ms | 失败：URLError: <urlopen error [Errno -5] No address associated with hostname> |
| 小盒子多仓 / 🐹dxawi | 48 | 14 | 7592ms | OK |
| 小盒子多仓 / 🍯HG | 10 | 6 | 7592ms | OK |
| 拾光多仓 / SVIP📚在线 | 246 | 201 | 2562ms | OK |
| 拾光多仓 / 备用📚在线 | - | 0 | 2562ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 拾光多仓 / VIP📚在线 | 246 | 154 | 2562ms | OK |
| 拾光多仓 / 小米📚在线 | - | 0 | 2562ms | 失败：URLError: <urlopen error [Errno -3] Temporary failure in name resolution> |
| 拾光多仓 / 动漫城📚在线 | 27 | 0 | 2562ms | OK |
| 拾光多仓 / 喵影视📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 小脑斧📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 401:  |
| 拾光多仓 / 小虎斑📚在线 | - | 0 | 2562ms | 失败：URLError: <urlopen error timed out> |
| 拾光多仓 / 潇洒📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 502: Bad Gateway |
| 拾光多仓 / 肥猫📚在线 | - | 0 | 2562ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html> <html lang="en"> <head> <meta charset="utf-8"> <meta name="viewport" content="width= |
| 拾光多仓 / 欧歌📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 拾光多仓 / 乐哥📚在线 | - | 0 | 2562ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 拾光多仓 / 老虎📚在线 | - | 0 | 2562ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 拾光多仓 / Clun📚在线 | 101 | 84 | 2562ms | OK |
| 拾光多仓 / O  K📚在线 | - | 0 | 2562ms | 失败：URLError: <urlopen error [Errno -5] No address associated with hostname> |
| 拾光多仓 / 俊佬📚在线 | 24 | 0 | 2562ms | OK |
| 拾光多仓 / 短剧📚在线 | - | 0 | 2562ms | 失败：URLError: <urlopen error timed out> |
| 拾光多仓 / 驸马📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 南风📚在线 | 93 | 85 | 2562ms | OK |
| 拾光多仓 / 二小📚在线 | 99 | 0 | 2562ms | OK |
| 拾光多仓 / 毒盒📚在线 | - | 0 | 2562ms | 失败：URLError: <urlopen error [Errno -5] No address associated with hostname> |
| 拾光多仓 / 心魔📚在线 | 151 | 142 | 2562ms | OK |
| 拾光多仓 / D佬📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 401:  |
| 拾光多仓 / 小马📚在线 | 62 | 0 | 2562ms | OK |
| 拾光多仓 / 星辰📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 拾光多仓 / 龙伊📚在线 | - | 0 | 2562ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html> <html lang="en"> .<head> ..<meta name="360-analysis-id" content="1k1c1k1e39331c2v">  |
| 拾光多仓 / 寳盒📚在线 | 77 | 67 | 2562ms | OK |
| 拾光多仓 / 挺好📚在线 | 46 | 22 | 2562ms | OK |
| 拾光多仓 / 传说📚在线 | - | 0 | 2562ms | 失败：URLError: <urlopen error [Errno 104] Connection reset by peer> |
| 拾光多仓 / 多多📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 分享📚在线 | - | 0 | 2562ms | 失败：ValueError: not json | head={ // 每日一言 (随机显示欢迎语) "dairyWords": [{     "name": "rating",     "request": {      "method": "GET",    |
| 拾光多仓 / 蓝天📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 423: Locked |
| 拾光多仓 / 青龙📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 423: Locked |
| 拾光多仓 / 黄金📚在线 | - | 0 | 2562ms | 失败：ValueError: not json | head=�PNG  . ... IHDR...�...�......�1?....sRGB.��.�....sBIT....|.d�.. .IDATx��I�e�u����Ϲ��/��l.I�4�T�T.<� |
| 拾光多仓 / 道长📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / PG📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 拾光多仓 / 真訫📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 拾光多仓 / 琉芸📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 拾光多仓 / 月光📚在线 | 77 | 1 | 2562ms | OK |
| 拾光多仓 / 雷霆📚在线 | 1063 | 1045 | 2562ms | OK |
| 拾光多仓 / 小凯📚在线 | 28 | 15 | 2562ms | OK |
| 拾光多仓 / 公子📚在线 | - | 0 | 2562ms | 失败：URLError: <urlopen error timed out> |
| 拾光多仓 / 短剧📚在线 | - | 0 | 2562ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd"> <h |
| 拾光多仓 / 特别📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 蜂蜜📚在线 | - | 0 | 2562ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html>  <html lang="en">  <head>      <meta charset="UTF-8">      <meta name="viewport" con |
| 拾光多仓 / 传说📚在线 | - | 0 | 2562ms | 失败：ValueError: not json | head=.//资源来自网络，南风的jar加上其他大神资源，介意请联系删除。  {  "sites":[          {"key":"t42直播转点播","name":"♥️Q群621399056","t |
| 拾光多仓 / 多多📚在线 | - | 0 | 2562ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<html> <head><title>404 Not Found</title></head> <body> <center><h1>404 Not Found</h1></center> <hr> |
| 拾光多仓 / 刺刺📚在线 | - | 0 | 2562ms | 失败：TimeoutError: The read operation timed out |
| 拾光多仓 / 剧场📚在线 | - | 0 | 2562ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 拾光多仓 / 听书📚在线 | - | 0 | 2562ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 拾光多仓 / CandyMu📚在线 | 64 | 57 | 2562ms | OK |
| 拾光多仓 / 欧歌备用📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 各种网盘📚在线 | - | 0 | 2562ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 请勿贩卖📚在线 | 19 | 18 | 2562ms | OK |
| 挺好分享多仓 / 📛挺好分享 | 46 | 0 | 4348ms | OK |
| 挺好分享多仓 / 🍳挺好丨讴歌线路 | - | 0 | 4348ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 挺好分享多仓 / 🐯小虎斑线路 | - | 0 | 4348ms | 失败：URLError: <urlopen error timed out> |
| 挺好分享多仓 / 🚀One线路 | - | 0 | 4348ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!-- 508338939653 --> <!DOCTYPE html> <html lang="en"> <head>     <meta charset="utf-8">     <meta n |
| 挺好分享多仓 / 🚀南风线路 | - | 0 | 4348ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 挺好分享多仓 / 🚀刘伟线路 | - | 0 | 4348ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 挺好分享多仓 / 🚀剪影线路 | - | 0 | 4348ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 挺好分享多仓 / 🚀讴歌线路 | - | 0 | 4348ms | 失败：ValueError: not json | head={ "logo":"https://ncstatic-file.clewm.net/rsrc/2025/0930/20/945a6372224243d3f3d63cb309c0b7b1.png", " |
| 挺好分享多仓 / 🚀小虎斑线 | - | 0 | 4348ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 挺好分享多仓 / 🚀小米线路 | - | 0 | 4348ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 挺好分享多仓 / 🚀王二小线 | 99 | 0 | 4348ms | OK |
| 挺好分享多仓 / 🚀潇洒专线 | - | 0 | 4348ms | 失败：HTTPError: HTTP Error 502: Bad Gateway |
| 挺好分享多仓 / 🚀摸鱼线路 | - | 0 | 4348ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!-- 598402364603 --> <!DOCTYPE html> <html lang="en"> <head>     <meta charset="utf-8">     <meta n |
| 挺好分享多仓 / 🚀环宇轩线 | - | 0 | 4348ms | 失败：HTTPError: HTTP Error 401:  |
| 挺好分享多仓 / 🚀小苹果线 | - | 0 | 4348ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 挺好分享多仓 / 🚀驸马线路 | - | 0 | 4348ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 挺好分享多仓 / 🚀拾光线路 | - | 0 | 4348ms | 失败：HTTPError: HTTP Error 401:  |
| 挺好分享多仓 / 🚀宝盒线路 | - | 0 | 4348ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 挺好分享多仓 / 🚀小马线路 | 62 | 0 | 4348ms | OK |
| 挺好分享多仓 / 🚀俊佬在线 | 24 | 0 | 4348ms | OK |
| 挺好分享多仓 / 🚀分享者线 | - | 0 | 4348ms | 失败：ValueError: not json | head={ // 每日一言 (随机显示欢迎语) "dairyWords": [{     "name": "rating",     "request": {      "method": "GET",    |
| 挺好分享多仓 / 🚀老刘线路 | - | 0 | 4348ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 挺好分享多仓 / 🚀传说线路 | - | 0 | 4348ms | 失败：URLError: <urlopen error [Errno 104] Connection reset by peer> |
| 挺好分享多仓 / 🚀蓝天线路 | - | 0 | 4348ms | 失败：HTTPError: HTTP Error 423: Locked |
| 挺好分享多仓 / 🚀高天流云 | 298 | 1 | 4348ms | OK |
| 挺好分享多仓 / 🚀俊佬线路 | 24 | 0 | 4348ms | OK |
| 挺好分享多仓 / 🚀毒盒线路 | - | 0 | 4348ms | 失败：URLError: <urlopen error [Errno -5] No address associated with hostname> |
| 挺好分享多仓 / 📛公众号丨挺好分享 | - | 0 | 4348ms | 失败：URLError: <urlopen error [Errno 111] Connection refused> |
| 挺好分享多仓 / 🌠公众号丨挺好专享 | - | 0 | 4348ms | 失败：URLError: <urlopen error [Errno 111] Connection refused> |
| 挺好分享多仓 / 🚀青龙影线 | - | 0 | 4348ms | 失败：HTTPError: HTTP Error 423: Locked |
| 挺好分享多仓 / 🍨饭硬专线 | - | 0 | 4348ms | 失败：ValueError: not json | head=����..JFIF..........��.�............ . . .... ................!...!.1&""&18/-/8D==DVQVpp�........... |
| 挺好分享多仓 / 🚀短剧大全 | - | 0 | 4348ms | 失败：URLError: <urlopen error timed out> |
| tvbox-probe 精选 | 110 | 6 | 225ms | OK |
| ysc-api 聚合 | 52 | 44 | 337ms | OK |
| 酒店电视 | 8 | 1 | 125ms | OK |

> 49 个站点的爬虫文件返回 404/410，已移出聚合搜索（仍可在站点列表中打开）。

## 站点排序（前 20，即首页与列表头部）

| # | 站点 | 分数 | 依据 |
| --- | --- | --- | --- |
| 1 | 欧歌·🤣魔都┃动漫 | 104.0 | http+34 影视+10 3源+6 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 2 | 创享·🌟 创享影视 | 103.0 | http+34 无jar+8 影视+10 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 3 | 拾光·360｜采集 | 101.0 | http+34 影视+10 3源+6 搜索精准+12 播放实测通过+8 接口通+20 较快+3 |
| 4 | 拾光·❤ikun资源 | 101.0 | http+34 影视+10 2源+3 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 5 | 拾光·ikun | 采集 | 98.0 | http+34 影视+10 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 6 | 拾光·如意｜采集 | 98.0 | http+34 影视+10 2源+3 搜索精准+12 播放实测通过+8 接口通+20 较快+3 |
| 7 | 拾光·创享 | 采集 | 95.0 | http+34 影视+10 搜索精准+12 播放实测通过+8 接口通+20 较快+3 |
| 8 | 小盒4K·🐓┃爱坤┃资源 | 95.0 | http+34 影视+10 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 9 | 分享·💖分享卫士 | 92.5 | http+34 5源+6 搜索精准+12 播放实测通过+8 接口通+20 较快+3 |
| 10 | 分享·💝分享魔都 | 89.5 | http+34 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 11 | 小盒仓·IK | 85.0 | http+34 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 12 | 拾光·影视文件播放 | 73.0 | http+34 影视+10 搜索精准+12 接口通+20 很慢-8 |
| 13 | 分享·💝分享合集 | 69.5 | http+34 接口通+20 极速+6 |
| 14 | 小马·红牛资源(切) | 68.0 | http+34 影视+10 9源+6 搜索精准+12 默认线路播不了-25 接口通+20 极速+6 |
| 15 | 拾光·服务器油管 | 67.0 | http+34 搜索精准+12 接口通+20 偏慢-4 |
| 16 | 拾光·油管播放列表1 | 67.0 | http+34 搜索精准+12 接口通+20 偏慢-4 |
| 17 | 拾光·油管播放列表2 | 67.0 | http+34 搜索精准+12 接口通+20 偏慢-4 |
| 18 | 拾光·采集集合 | 65.0 | http+34 影视+10 接口通+20 偏慢-4 |
| 19 | 拾光·金鹰 | 采集 | 65.0 | http+34 影视+10 搜索精准+12 默认线路播不了-25 接口通+20 极速+6 |
| 20 | 拾光·油管清单播放 | 63.0 | http+34 搜索精准+12 接口通+20 很慢-8 |

排序口径：接口类型 + jar 成本 + 跨源收录 + CMS 探活/速度 + 搜索实测 − 工具类站点 − 搜索杂乱 − 爬虫失效，同分按源优先级。首页另需三类覆盖。
