# Imposer 自定义 RSSHub 路由备份

本目录是 imposer 为 RSSHub 编写的**自定义路由**（TypeScript），备份自
`~/news/rsshub-src/lib/routes/`（本机 dev 模式实例 @ localhost:1201）。

## 路由清单

### 自定义（社区没有，imposer 首创）
| 路由 | 源 | 说明 |
|---|---|---|
| `/cnsa/news` | 中国国家航天局 | P3 中国航天官方新闻（最大的缺源补齐） |
| `/esa/newsroom` | 欧洲航天局 | ESA 新闻稿，data-date → pubDate |

### 补位（社区路由失效/反爬，imposer 重写）
| 路由 | 源 | 说明 |
|---|---|---|
| `/tassfix/news` | TASS | 社区 `/tass/news` 空，一般锚文本选择器 |
| `/cfrfix/news` | CFR | 社区 `/cfr/news` 空，h2/h3 选择器 |
| `/microsoftfix/news` | Microsoft | 社区 `/microsoft/news` 空，RSS proxy |
| `/githubfix/news` | GitHub | 社区 `/github/news` 空 |
| `/nasafix/news` | NASA | 社区 `/nasa/news` 空 |
| `/chinadailyfix/news` | China Daily | 社区 `/chinadaily/news` 空 |
| `/scmpfix/news` | SCMP | 社区 `/scmp/news` 空 |
| `/naturefix/news` | Nature | 社区 `/nature/news` 空 |
| `/yahoofix/news` | Yahoo | 社区 `/yahoo/news` 空 |
| `/washingtonpostfix/news` | WaPo | 社区空，RSS proxy（直抓超时） |

### 社区已覆盖（直接复用，未改）
OpenAI/Anthropic/Al Jazeera/Asia Times/Naval News/CSIS/NVIDIA/AOL/JAXA/Cloudflare/VOA/NYT/Ars/Phys.org/TechXplore/Space.com/NASA Spaceflight/Universe Today/DeepSeek/Planetary 等。

## 部署

```bash
# 路由文件放进 RSSHub 源码 lib/routes/ 即可（dev 模式自动加载，新增目录需重启）
# 接入 imposer：sources.json 加 "rsshub": "/<name>/<route>" 字段
```

## 2026-08-06 新增 6 自定义路由（直抓源迁移）

| 路由 | 源 | 版块 | 数据源 |
|---|---|---|---|
| `/xinhuaenglish/news` | Xinhua English | P1/P4（P3 共用） | english.news.cn 首页（/20260805/<hash>/c.html 模式） |
| `/globaltimes/news` | Global Times | P1/P4 | globaltimes.cn 首页（/page/202608/<id>.shtml 模式） |
| `/brookings/articles` | Brookings | P1 | brookings.edu /articles/<slug>/ |
| `/rand/articles` | RAND | P1 | rand.org /pubs/articles/2026/<slug>.html |
| `/iter/news` | ITER | P4 | iter.org/rss.xml 官方 RSS 转发 |
| `/isro/news` | ISRO | P3 | isro.gov.in 首页（相对 .html 文章） |

### 保留直抓（SPA/反爬，RSSHub 同样抓不到，Python urllib 反而可行）
- xAI/Moonshot/Zhipu/Alibaba：Next.js SPA，无静态文章链接
- CGTN：SPA，/news/ 频道全 404
- SpaceX/Rocket Lab：JS 渲染
- Blue Origin：429 限流；SpaceNews：403；New Scientist：406
