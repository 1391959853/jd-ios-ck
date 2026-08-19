# QX 规则文件说明

> 最后更新：2026-08-20 06:12:15

---

## rewrite/（重写规则）

| 文件名 | 对应 App | 规则条数 |
|--------|----------|----------|
| FanQieNovel.qxrewrite | 番茄小说 | 17 |
| MyAdBlock.qxrewrite | 有兔阅读(米兔)去羞耻的开屏 | 70 |
| MyJsRewrite_lite.qxrewrite | 京东比价 by yichahucha | 10 |
| Qsearch.qxrewrite | wk (Wikipedia中文) | 22 |
| QsearchMac.qxrewrite | Safari Firefox Edge | 35 |
| baiduAd.qxrewrite | 百度地图开屏 | 29 |
| bilibili.qxrewrite | 番剧地区自动切换 | 16 |
| googleRedirect.qxrewrite | Google搜索中国，香港，日本重定向 | 4 |
| kuwo.qxrewrite | 酷我音乐去开屏 | 6 |
| youtube.qxrewrite | by 神机 | 7 |

## rules/（分流/筛选规则）

| 文件名 | 对应 App | 规则条数 |
|--------|----------|----------|
| AdBlock.list | AdBlock rules refresh time: 2024-01-22 01:41:55 | 78537 |
| AdBlock_lite.list | AdBlock rules refresh time: 2024-01-22 01:41:57 | 12819 |
| Apple.list | Apple | 1872 |
| AppleIOSUpdate.list | Block iOS Update | 4 |
| CMedia.list | CMedia rules refresh time: 2024-11-18 02:10:34 | 435 |
| FanQieNovel.list | 番茄小说 | 30 |
| GMedia.list | GMedia rules refresh time: 2024-11-18 02:10:35 | 2349 |
| Mainland.list | Mainland rules refresh time: 2024-11-18 02:10:36 | 3786 |
| Microsoft.list | Microsoft | 711 |
| Netflix.list | Netflix rules refresh time: 2024-11-18 02:10:35 | 1158 |
| Outside.list | Outside rules refresh time: 2024-11-18 02:10:36 | 6569 |
| ReFix.list | 有兔阅读 | 151 |
| YouTube.list | YouTube | 196 |

## snippet/（QX 规则配置片段）

| 文件名 | 对应 App | 规则条数 |
|--------|----------|----------|
| FanQieNovel.snippet | 番茄小说 | 30 行 |
| QMusicAd.snippet | QQ音乐 | 19 行 |
| ad_uni.snippet | 广告联盟 | 73 行 |
| backiee.snippet | backiee | 7 行 |
| baiduApp.snippet | 百度App | 8 行 |

---

> 📌 说明：
> - **规则条数**：每个文件自身的有效规则行数（不去重）
> - **snippet 文件**：显示为文件行数（含注释），非规则条数
> - 上游规则来源：[zqzess/rule_for_quantumultX](https://github.com/zqzess/rule_for_quantumultX)