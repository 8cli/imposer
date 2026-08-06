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
