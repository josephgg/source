# 构建报告

生成时间：2026-11-18T10:05:44+08:00

| 指标 | 数值 |
| --- | --- |
| 合并后站点数 | 3809 |
| 参与聚合搜索 | 3286 |
| 稳定精选站点数 | 7 |
| 实体剔除确认失效站 | 712 |
| 解析源数量 | 36 |
| 直播源数量 | 12 |
| 跨源去重丢弃 | 2994 |
| 爬虫文件失效 | 24 |
| 搜索实测：关搜索 | 51 |
| 搜索实测：仅关快速搜索 | 1 |
| 剔除：成人内容 | 0 |
| 剔除：域名黑名单 | 3 |
| 剔除：本机代理地址 | 9 |

## 稳定精选实测证据

仅保留最近 36 小时内连续两轮通过的源；HLS 抽检首/中/尾分片，直链校验媒体签名。

| 站点 | 类型 | 连续通过 | 分片抽检 | 抽检字节 | 耗时 |
| --- | --- | --- | --- | --- | --- |
| 影视·ikun | ok | 9 轮 | 3/1466 | 1297200 | 3358ms |
| 影视·如意 | ok | 15 轮 | 3/41 | 3336812 | 6411ms |
| 影视·分享魔都 | ok | 12 轮 | 3/20 | 2200164 | 3999ms |
| 影视·创享 | ok | 2 轮 | 3/625 | 1055472 | 18655ms |
| 影视·无损云 | ok | 9 轮 | 3/1445 | 816296 | 2040ms |
| 影视·仓 | ok | 15 轮 | 3/337 | 4767079 | 7456ms |
| 动漫·魔都 | ok | 12 轮 | 3/20 | 2200164 | 3997ms |

## 各源状态

| 源 | 站点 | 新增 | 耗时 | 状态 |
| --- | --- | --- | --- | --- |
| 高天流云 | 298 | 295 | 153ms | OK |
| 老刘备 | 234 | 229 | 96ms | OK |
| 分享者 | 168 | 164 | 153ms | OK |
| 王二小放牛娃 | - | 0 | 56128ms | 失败：HTTPError: HTTP Error 504: Gateway Time-out |
| 香雅晴 | 48 | 45 | 77ms | OK |
| 短剧专线 | - | 0 | 117370ms | 失败：URLError: <urlopen error timed out> |
| 俊佬 | 24 | 23 | 1044ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃饭太硬线路 | - | 0 | 12240ms | 失败：ValueError: not json | head=����..JFIF..........��.�............ . . .... ................!...!.1&""&18/-/8D==DVQVpp�........... |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃肥猫线路 | 41 | 37 | 12240ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃摸鱼线路 | 111 | 107 | 12240ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃王二小线路 | - | 0 | 12240ms | 失败：HTTPError: HTTP Error 504: Gateway Time-out |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃短剧专线 | - | 0 | 12240ms | 失败：URLError: <urlopen error timed out> |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃儿童专线 | - | 0 | 12240ms | 失败：ValueError: not json | head=�PNG  . ... IHDR...x...�.....����....sRGB.��.�....sBIT....|.d�.. .IDATx���Y�e�u��[{8Ýr�.3@....��lY�Z |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃饭太硬备用 | - | 0 | 12240ms | 失败：ValueError: not json | head=����..JFIF..........��.�............ . . .... ................!...!.1&""&18/-/8D==DVQVpp�........... |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃肥猫备用 | 41 | 1 | 12240ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃摸鱼备用 | 111 | 0 | 12240ms | OK |
| 无邪 / 💚无邪优选仓🍭热门推荐🍭 / 🚀无邪┃王二小备用 | - | 0 | 12240ms | 失败：URLError: <urlopen error timed out> |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃饭太硬线路 | - | 0 | 12240ms | 失败：ValueError: not json | head=����..JFIF..........��.�............ . . .... ................!...!.1&""&18/-/8D==DVQVpp�........... |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃肥猫线路 | - | 0 | 12240ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃摸鱼线路 | 111 | 0 | 12240ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃王二小线路 | - | 0 | 12240ms | 失败：HTTPError: HTTP Error 504: Gateway Time-out |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃短剧专线 | - | 0 | 12240ms | 失败：URLError: <urlopen error timed out> |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃儿童专线 | - | 0 | 12240ms | 失败：ValueError: not json | head=�PNG  . ... IHDR...x...�.....����....sRGB.��.�....sBIT....|.d�.. .IDATx���Y�e�u��[{8Ýr�.3@....��lY�Z |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃俊佬线路 | 24 | 0 | 12240ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃老刘备线路 | 234 | 0 | 12240ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃分享者线路 | 168 | 1 | 12240ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃高天流云线路 | 298 | 1 | 12240ms | OK |
| 无邪 / 💛无邪聚合仓🍭聚合全网🍭 / 💎无邪┃香雅晴线路 | 48 | 0 | 12240ms | OK |
| 肥猫 | 41 | 0 | 1396ms | OK |
| 饭太硬 | 49 | 48 | 151ms | OK |
| 小米 | 36 | 27 | 281ms | OK |
| 肥猫(iptv) | 61 | 37 | 93ms | OK |
| 菜妮丝 | 104 | 85 | 185ms | OK |
| 王二小(iptv) | 86 | 83 | 135ms | OK |
| 小虎斑 | 88 | 85 | 180ms | OK |
| 摸鱼儿 | 107 | 81 | 289ms | OK |
| PG | 106 | 91 | 201ms | OK |
| 欧歌 | 106 | 72 | 140ms | OK |
| 潇洒 | 160 | 105 | 154ms | OK |
| 天微 | 97 | 77 | 130ms | OK |
| 天天开心 | 126 | 90 | 138ms | OK |
| 香雅情(iptv) | 55 | 39 | 145ms | OK |
| 南风 | 78 | 56 | 111ms | OK |
| 骚零 | 37 | 17 | 213ms | OK |
| 白嫖 | 9 | 8 | 183ms | OK |
| OK | 76 | 71 | 170ms | OK |
| 戏曲音乐 | 10 | 10 | 141ms | OK |
| 短剧频道 | 35 | 35 | 138ms | OK |
| 少儿频道 | 30 | 30 | 152ms | OK |
| 动漫频道 | 19 | 16 | 145ms | OK |
| iptv365直播 | 4 | 4 | 208ms | OK |
| 老刘备(liucn) | 234 | 142 | 378ms | OK |
| 小马 | 62 | 35 | 4360ms | OK |
| 创享影视 | 12 | 12 | 1748ms | OK |
| 影仓 | 28 | 27 | 767ms | OK |
| 小盒子单仓 | 54 | 34 | 541ms | OK |
| 小盒子4K | 53 | 35 | 417ms | OK |
| 小盒子多仓 / 🚀小盒子 | 54 | 0 | 14266ms | OK |
| 小盒子多仓 / 🐔肥猫 | - | 0 | 14266ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 小盒子多仓 / 🐟 摸 鱼 | 111 | 0 | 14266ms | OK |
| 小盒子多仓 / 🍯毒盒 | - | 0 | 14266ms | 失败：URLError: <urlopen error [Errno -5] No address associated with hostname> |
| 小盒子多仓 / 🍯PG线路 | - | 0 | 14266ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 小盒子多仓 / 🍯影视仓 | - | 0 | 14266ms | 失败：URLError: <urlopen error timed out> |
| 小盒子多仓 / 🦆神仙线路 | - | 0 | 14266ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 小盒子多仓 / 🦆俊于 | 24 | 0 | 14266ms | OK |
| 小盒子多仓 / 😹影视资源 | - | 0 | 14266ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html> <html><head> .<meta name="robots" content="noarchive">     <meta http-equiv="Content |
| 小盒子多仓 / 😹玄珠 | - | 0 | 14266ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 小盒子多仓 / 😹吾爱 | - | 0 | 14266ms | 失败：URLError: <urlopen error [Errno 111] Connection refused> |
| 小盒子多仓 / 😹动漫城 | 27 | 23 | 14266ms | OK |
| 小盒子多仓 / 🚀喵影视 | - | 0 | 14266ms | 失败：URLError: <urlopen error [Errno -3] Temporary failure in name resolution> |
| 小盒子多仓 / 🚀摸鱼 | 111 | 0 | 14266ms | OK |
| 小盒子多仓 / 🚀小马 | 62 | 0 | 14266ms | OK |
| 小盒子多仓 / 🦉飘零 | - | 0 | 14266ms | 失败：URLError: <urlopen error [Errno -5] No address associated with hostname> |
| 小盒子多仓 / 🐹dxawi | 48 | 14 | 14266ms | OK |
| 小盒子多仓 / 🍯HG | 10 | 6 | 14266ms | OK |
| 拾光多仓 / SVIP📚在线 | 246 | 201 | 4942ms | OK |
| 拾光多仓 / 备用📚在线 | - | 0 | 4942ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 拾光多仓 / VIP📚在线 | 246 | 154 | 4942ms | OK |
| 拾光多仓 / 小米📚在线 | - | 0 | 4942ms | 失败：URLError: <urlopen error [Errno -3] Temporary failure in name resolution> |
| 拾光多仓 / 动漫城📚在线 | 27 | 0 | 4942ms | OK |
| 拾光多仓 / 喵影视📚在线 | - | 0 | 4942ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 小脑斧📚在线 | - | 0 | 4942ms | 失败：URLError: <urlopen error timed out> |
| 拾光多仓 / 小虎斑📚在线 | 117 | 115 | 4942ms | OK |
| 拾光多仓 / 潇洒📚在线 | - | 0 | 4942ms | 失败：URLError: <urlopen error timed out> |
| 拾光多仓 / 肥猫📚在线 | - | 0 | 4942ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html> <html lang="en"> <head> <meta charset="utf-8"> <meta name="viewport" content="width= |
| 拾光多仓 / 欧歌📚在线 | - | 0 | 4942ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 拾光多仓 / 乐哥📚在线 | - | 0 | 4942ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 拾光多仓 / 老虎📚在线 | - | 0 | 4942ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 拾光多仓 / Clun📚在线 | 101 | 84 | 4942ms | OK |
| 拾光多仓 / O  K📚在线 | - | 0 | 4942ms | 失败：URLError: <urlopen error [Errno -5] No address associated with hostname> |
| 拾光多仓 / 俊佬📚在线 | 24 | 0 | 4942ms | OK |
| 拾光多仓 / 短剧📚在线 | - | 0 | 4942ms | 失败：URLError: <urlopen error timed out> |
| 拾光多仓 / 驸马📚在线 | - | 0 | 4942ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 南风📚在线 | 93 | 85 | 4942ms | OK |
| 拾光多仓 / 二小📚在线 | - | 0 | 4942ms | 失败：HTTPError: HTTP Error 504: Gateway Time-out |
| 拾光多仓 / 毒盒📚在线 | - | 0 | 4942ms | 失败：URLError: <urlopen error [Errno -5] No address associated with hostname> |
| 拾光多仓 / 心魔📚在线 | 151 | 142 | 4942ms | OK |
| 拾光多仓 / D佬📚在线 | - | 0 | 4942ms | 失败：URLError: <urlopen error timed out> |
| 拾光多仓 / 小马📚在线 | 62 | 0 | 4942ms | OK |
| 拾光多仓 / 星辰📚在线 | - | 0 | 4942ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 拾光多仓 / 龙伊📚在线 | - | 0 | 4942ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html> <html lang="en"> .<head> ..<meta name="360-analysis-id" content="1k1c1k1e39331c2v">  |
| 拾光多仓 / 寳盒📚在线 | 77 | 67 | 4942ms | OK |
| 拾光多仓 / 挺好📚在线 | 46 | 22 | 4942ms | OK |
| 拾光多仓 / 传说📚在线 | - | 0 | 4942ms | 失败：URLError: <urlopen error [Errno 104] Connection reset by peer> |
| 拾光多仓 / 多多📚在线 | - | 0 | 4942ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 分享📚在线 | - | 0 | 4942ms | 失败：ValueError: not json | head={ // 每日一言 (随机显示欢迎语) "dairyWords": [{     "name": "rating",     "request": {      "method": "GET",    |
| 拾光多仓 / 蓝天📚在线 | - | 0 | 4942ms | 失败：HTTPError: HTTP Error 423: Locked |
| 拾光多仓 / 青龙📚在线 | - | 0 | 4942ms | 失败：HTTPError: HTTP Error 423: Locked |
| 拾光多仓 / 黄金📚在线 | - | 0 | 4942ms | 失败：ValueError: not json | head=�PNG  . ... IHDR...�...�......�1?....sRGB.��.�....sBIT....|.d�.. .IDATx��I�e�u����Ϲ��/��l.I�4�T�T.<� |
| 拾光多仓 / 道长📚在线 | - | 0 | 4942ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / PG📚在线 | - | 0 | 4942ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 拾光多仓 / 真訫📚在线 | - | 0 | 4942ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 拾光多仓 / 琉芸📚在线 | - | 0 | 4942ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 拾光多仓 / 月光📚在线 | 77 | 1 | 4942ms | OK |
| 拾光多仓 / 雷霆📚在线 | 1063 | 1045 | 4942ms | OK |
| 拾光多仓 / 小凯📚在线 | 28 | 15 | 4942ms | OK |
| 拾光多仓 / 公子📚在线 | - | 0 | 4942ms | 失败：URLError: <urlopen error timed out> |
| 拾光多仓 / 短剧📚在线 | - | 0 | 4942ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd"> <h |
| 拾光多仓 / 特别📚在线 | - | 0 | 4942ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 蜂蜜📚在线 | - | 0 | 4942ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!DOCTYPE html>  <html lang="en">  <head>      <meta charset="UTF-8">      <meta name="viewport" con |
| 拾光多仓 / 传说📚在线 | - | 0 | 4942ms | 失败：ValueError: not json | head=.//资源来自网络，南风的jar加上其他大神资源，介意请联系删除。  {  "sites":[          {"key":"t42直播转点播","name":"♥️Q群621399056","t |
| 拾光多仓 / 多多📚在线 | - | 0 | 4942ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<html> <head><title>404 Not Found</title></head> <body> <center><h1>404 Not Found</h1></center> <hr> |
| 拾光多仓 / 刺刺📚在线 | - | 0 | 4942ms | 失败：URLError: <urlopen error timed out> |
| 拾光多仓 / 剧场📚在线 | - | 0 | 4942ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 拾光多仓 / 听书📚在线 | - | 0 | 4942ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 拾光多仓 / CandyMu📚在线 | 64 | 57 | 4942ms | OK |
| 拾光多仓 / 欧歌备用📚在线 | - | 0 | 4942ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 各种网盘📚在线 | - | 0 | 4942ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 拾光多仓 / 请勿贩卖📚在线 | 19 | 18 | 4942ms | OK |
| 挺好分享多仓 / 📛挺好分享 | 46 | 0 | 8073ms | OK |
| 挺好分享多仓 / 🍳挺好丨讴歌线路 | - | 0 | 8073ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 挺好分享多仓 / 🐯小虎斑线路 | 117 | 0 | 8073ms | OK |
| 挺好分享多仓 / 🚀One线路 | - | 0 | 8073ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!-- 125424554968 --> <!DOCTYPE html> <html lang="en"> <head>     <meta charset="utf-8">     <meta n |
| 挺好分享多仓 / 🚀南风线路 | - | 0 | 8073ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 挺好分享多仓 / 🚀刘伟线路 | - | 0 | 8073ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 挺好分享多仓 / 🚀剪影线路 | - | 0 | 8073ms | 失败：HTTPError: HTTP Error 403: Forbidden |
| 挺好分享多仓 / 🚀讴歌线路 | - | 0 | 8073ms | 失败：ValueError: not json | head={ "logo":"https://ncstatic-file.clewm.net/rsrc/2025/0930/20/945a6372224243d3f3d63cb309c0b7b1.png", " |
| 挺好分享多仓 / 🚀小虎斑线 | - | 0 | 8073ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 挺好分享多仓 / 🚀小米线路 | - | 0 | 8073ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 挺好分享多仓 / 🚀王二小线 | - | 0 | 8073ms | 失败：HTTPError: HTTP Error 504: Gateway Time-out |
| 挺好分享多仓 / 🚀潇洒专线 | - | 0 | 8073ms | 失败：URLError: <urlopen error timed out> |
| 挺好分享多仓 / 🚀摸鱼线路 | - | 0 | 8073ms | 失败：ValueError: not json（返回的是图片/二进制，不是配置） | head=<!-- 670761960085 --> <!DOCTYPE html> <html lang="en"> <head>     <meta charset="utf-8">     <meta n |
| 挺好分享多仓 / 🚀环宇轩线 | - | 0 | 8073ms | 失败：URLError: <urlopen error timed out> |
| 挺好分享多仓 / 🚀小苹果线 | - | 0 | 8073ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 挺好分享多仓 / 🚀驸马线路 | - | 0 | 8073ms | 失败：HTTPError: HTTP Error 404: Not Found |
| 挺好分享多仓 / 🚀拾光线路 | - | 0 | 8073ms | 失败：URLError: <urlopen error timed out> |
| 挺好分享多仓 / 🚀宝盒线路 | - | 0 | 8073ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 挺好分享多仓 / 🚀小马线路 | 62 | 0 | 8073ms | OK |
| 挺好分享多仓 / 🚀俊佬在线 | 24 | 0 | 8073ms | OK |
| 挺好分享多仓 / 🚀分享者线 | - | 0 | 8073ms | 失败：ValueError: not json | head={ // 每日一言 (随机显示欢迎语) "dairyWords": [{     "name": "rating",     "request": {      "method": "GET",    |
| 挺好分享多仓 / 🚀老刘线路 | - | 0 | 8073ms | 失败：URLError: <urlopen error [Errno -2] Name or service not known> |
| 挺好分享多仓 / 🚀传说线路 | - | 0 | 8073ms | 失败：URLError: <urlopen error [Errno 104] Connection reset by peer> |
| 挺好分享多仓 / 🚀蓝天线路 | - | 0 | 8073ms | 失败：HTTPError: HTTP Error 423: Locked |
| 挺好分享多仓 / 🚀高天流云 | 298 | 0 | 8073ms | OK |
| 挺好分享多仓 / 🚀俊佬线路 | 24 | 0 | 8073ms | OK |
| 挺好分享多仓 / 🚀毒盒线路 | - | 0 | 8073ms | 失败：URLError: <urlopen error [Errno -5] No address associated with hostname> |
| 挺好分享多仓 / 📛公众号丨挺好分享 | - | 0 | 8073ms | 失败：URLError: <urlopen error [Errno 111] Connection refused> |
| 挺好分享多仓 / 🌠公众号丨挺好专享 | - | 0 | 8073ms | 失败：URLError: <urlopen error [Errno 111] Connection refused> |
| 挺好分享多仓 / 🚀青龙影线 | - | 0 | 8073ms | 失败：HTTPError: HTTP Error 423: Locked |
| 挺好分享多仓 / 🍨饭硬专线 | - | 0 | 8073ms | 失败：ValueError: not json | head=����..JFIF..........��.�............ . . .... ................!...!.1&""&18/-/8D==DVQVpp�........... |
| 挺好分享多仓 / 🚀短剧大全 | - | 0 | 8073ms | 失败：URLError: <urlopen error timed out> |
| tvbox-probe 精选 | 103 | 93 | 115ms | OK |
| ysc-api 聚合 | 52 | 44 | 118ms | OK |
| 酒店电视 | 8 | 0 | 114ms | OK |

> 105 个站点的爬虫文件返回 404/410，已移出聚合搜索（仍可在站点列表中打开）。

## 站点排序（前 20，即首页与列表头部）

| # | 站点 | 分数 | 依据 |
| --- | --- | --- | --- |
| 1 | 欧歌·🤣魔都┃动漫 | 104.0 | http+34 影视+10 3源+6 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 2 | 拾光·ikun | 采集 | 98.0 | http+34 影视+10 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 3 | 拾光·❤ikun资源 | 98.0 | http+34 影视+10 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 4 | 拾光·如意｜采集 | 98.0 | http+34 影视+10 2源+3 搜索精准+12 播放实测通过+8 接口通+20 较快+3 |
| 5 | 小盒4K·🐓┃爱坤┃资源 | 95.0 | http+34 影视+10 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 6 | 拾光·360｜采集 | 93.0 | http+34 影视+10 3源+6 搜索精准+12 接口通+20 较快+3 |
| 7 | 分享·💖分享如意 | 89.5 | http+34 2源+3 搜索精准+12 播放实测通过+8 接口通+20 较快+3 |
| 8 | 分享·💝分享魔都 | 89.5 | http+34 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 9 | 创享·🌟 创享影视 | 89.0 | http+34 无jar+8 影视+10 搜索精准+12 播放实测通过+8 接口通+20 很慢-8 |
| 10 | 小盒仓·IK | 85.0 | http+34 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 11 | 探针·🈚无损云(12.8万)·2150ms | 85.0 | http+34 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 12 | 探针·🎯猫眼(3.5万)·202ms | 85.0 | http+34 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 13 | 探针·🏙魔都(9.2万)·928ms | 85.0 | http+34 搜索精准+12 播放实测通过+8 接口通+20 极速+6 |
| 14 | 拾光·创享 | 采集 | 84.0 | http+34 影视+10 搜索精准+12 播放实测通过+8 接口通+20 很慢-8 |
| 15 | 分享·💖分享卫士 | 81.5 | http+34 5源+6 搜索精准+12 接口通+20 |
| 16 | 老刘·🦊火狐采集 | 75.0 | http+34 影视+10 5源+6 搜索精准+12 默认线路播不了-25 接口通+20 极速+6 |
| 17 | 拾光·影视文件播放 | 73.0 | http+34 影视+10 搜索精准+12 接口通+20 很慢-8 |
| 18 | 探针·🦚360(7.5万)·582ms | 73.0 | http+34 播放实测通过+8 接口通+20 极速+6 |
| 19 | 拾光·极速｜采集 | 71.0 | http+34 影视+10 5源+6 搜索精准+12 默认线路播不了-25 接口通+20 极速+6 |
| 20 | 分享·️✈️极速采集 | 69.5 | http+34 影视+10 2源+3 搜索精准+12 默认线路播不了-25 接口通+20 极速+6 |

排序口径：接口类型 + jar 成本 + 跨源收录 + CMS 探活/速度 + 搜索实测 − 工具类站点 − 搜索杂乱 − 爬虫失效，同分按源优先级。首页另需三类覆盖。
