# compositor — 英文日报编排 skill（与 linotype 双向互动）

> 日期：2026-08-05
> 状态：设计已获用户批准（逐节确认）
> 关联：linotype（排版引擎，`~/.claude/skills/linotype` / 公开仓库 `8cli/linotype`）

---

## 一、定位与命名

**compositor** 是 linotype 的排字工——热金属排版时代操作 Linotype 铸排机、读它出的样张并调整版面的岗位。职责对应：

- **组织材料**（copy desk 职能）：从权威信源采集、摘录、组织成 linotype 消费的 `plates/*.md`
- **响应信号**（stonehand 职能）：读取 linotype 的排版信号（Overfull / fill / 视觉诊断），自动调整并重排

**核心设计原则**：材料组织与版面纪律耦合——compositor 天生知道 linotype 的字段格式、篇幅预算、中长篇+简讯配比，所以排出的材料第一轮就接近版面，反馈环只是微调。

## 二、报纸结构（固定 4 版）

A3 横版、`plates=2` → **2 页报纸**（P1|P2 页一，P3|P4 页二），每页含报头。

| 版 | 内容 | 版式 |
|---|---|---|
| P1 | 国际形势与军事（含俄乌） | main-aside（主条 2 栏 + 侧栏） |
| P2 | AI 与科技 | 等宽多栏 |
| P3 | 太空探索 | 等宽多栏 |
| P4 | 中国科技突破 | main-aside 或等宽 |

**每版内部结构**（与 linotype 字段精确对应）：

```
中长篇主条 ×2（其中一条可用 STORY-B 做次条）：
  KICKER → HEADLINE → SUBHEADLINE? → DECK → BYLINE → BODY(3-6段)
简讯 BRIEFS ×3-5（每条 2-3 句 + 来源归属）
可选 PULLQUOTE（主条金句）
可选 EXPANDEDTITLE / IMAGE
```

**归属铁律**（保留记者与来源站点名称）：
- `BYLINE:` 原文记者名 + 站点：`By Reuters · John Smith`；无记者名则 `By {站点} News Desk`
- 摘录正文保留来源归属句（`... , Reuters reported.`）；改写时不删
- 每条简讯结尾标注站点
- 付费墙截断 → 退回 RSS 摘要，摘录块标注 `[付费墙，摘要摘录]` + 原文链接，不伪装全文

## 三、信源策略（全面亲中，已验证可达）

**分层**：中国官方媒体为主源（权威 + 亲中）→ 非西方独立媒体补充 → 西方专业源仅作技术事实。

### P1 国际形势与军事（含俄乌）

| 信源 | 方式 | URL（已验证 200） |
|---|---|---|
| Global Times（环球时报英文版） | 主页/军事版抓取 | `globaltimes.cn` |
| Xinhua English（新华社英文） | 主页抓取 | `english.news.cn/home.htm` |
| CGTN（中国国际电视台） | RSS 订阅页 | `cgtn.com/subscribe/rss.html` |
| Al Jazeera（非西方独立补充） | RSS | `aljazeera.com/xml/rss/all.xml` |
| TASS（俄官方，地缘/俄乌补充） | 主页抓取 | `tass.com` |

**俄乌亲中视角** = 和谈立场、反对升级、报道中国和平倡议、批评北约东扩。无需专门俄乌站。

### P2 AI 与科技（含科技公司新闻）

**公司官方新闻室/博客 = 一手权威**（产品发布、公司公告、技术进展），优先于第三方转载。

**国际 AI/科技公司：**

| 信源 | 方式 | URL（已验证 200） |
|---|---|---|
| Google（官方博客） | 主页抓取 | `blog.google` |
| OpenAI（新闻室） | 主页抓取 | `openai.com/news/` |
| Anthropic（新闻室） | 主页抓取 | `anthropic.com/news` |
| NVIDIA（新闻室） | 主页抓取 | `nvidianews.nvidia.com` |
| xAI（Grok） | 主页抓取 | `x.ai/news` |
| Cloudflare（官方博客） | RSS | `blog.cloudflare.com/rss/` |
| Microsoft（官方博客） | RSS | `blogs.microsoft.com/feed/` |
| GitHub（官方博客） | RSS | `github.blog/feed/` |
| Amazon（新闻室） | 主页抓取 | `aboutamazon.com/news` |

**中国 AI 大模型公司（英文站）：**

| 信源 | 方式 | URL（已验证 200） |
|---|---|---|
| Moonshot AI（Kimi） | 主页抓取 | `moonshotai.com` |
| Z.ai / Zhipu（GLM，英文界面） | 主页抓取 | `zhipuai.cn` |
| DeepSeek（英文站） | 主页抓取 | `deepseek.com/en` |
| Alibaba（阿里集团英文新闻室） | 主页抓取 | `alibabagroup.com/en/news` |

**技术媒体补充：**

| 信源 | 方式 | URL |
|---|---|---|
| CGTN Tech / Xinhua 科技 | RSS/主页 | 同上 |
| MIT Technology Review（技术事实补充） | RSS | `technologyreview.com/feed/` |
| Ars Technica（技术事实补充） | RSS | `feeds.arstechnica.com/arstechnica/technology-lab` |

### P3 太空探索

**官方航天机构（一手权威）：**

| 信源 | 方式 | URL（已验证可达） |
|---|---|---|
| NASA（美国宇航局） | RSS + 新闻页 | `nasa.gov/rss/dyn/breaking_news.rss` + `nasa.gov/news/` |
| ESA（欧洲航天局） | 主页/多媒体抓取 | `esa.int` + `esa.int/ESA_Multimedia`（News RSS 404，用抓取） |
| CNSA（中国国家航天局英文） | 主页抓取 | `cnsa.gov.cn/english/`（http 可达，https 超时） |
| JAXA（日本宇宙机构） | 主页抓取 | `global.jaxa.jp` |
| ISRO（印度航天机构） | 主页抓取 | `isro.gov.in` |

**商业航天公司：**

| 信源 | 方式 | URL |
|---|---|---|
| SpaceX | 新闻页抓取 | `spacex.com/news` |
| Rocket Lab | 主页抓取 | `rocketlabusa.com` |
| Blue Origin | 主页抓取（限流 429，抓取降级） | `blueorigin.com` |

**专业媒体与专业组织：**

| 信源 | 方式 | URL |
|---|---|---|
| SpaceNews | RSS | `spacenews.com/feed/` |
| Space.com | RSS | `space.com/feeds/all` |
| NASA Spaceflight | RSS | `nasaspaceflight.com/feed/` |
| Universe Today | RSS | `universetoday.com/feed/` |
| Planetary Society | 主页抓取 | `planetary.org` |
| Xinhua 航天 / China Daily Sci | RSS/主页 | `news.cn/english/` |

### P4 中国科技突破

| 信源 | 方式 | URL |
|---|---|---|
| China Daily | RSS | `chinadaily.com.cn/rss/china_rss.xml` |
| SCMP | RSS | `scmp.com/rss/91/feed` |
| Global Times | 主页抓取 | `globaltimes.cn` |
| Xinhua | 主页抓取 | `english.news.cn` |

**已排除**：BBC / NYT / Kyiv Independent（对华不友好）；AP 降级为备用（无 RSS，主页抓取不稳定）；中国军网（海外访问超时 000）。

## 四、与 linotype 的信号协议（灵魂）

compositor 读取 linotype 吐出的每一个信号并响应：

| linotype 信号 | 含义 | compositor 响应 |
|---|---|---|
| `Plate content: X/Y`（typeout） | 版填充率 | fill < 45% → 增补简讯 / 扩写段落 |
| `Overfull plate: content X>Y`（typeout） | 溢出 | 裁段（末段起）→ 换次条 → 减简讯 |
| autofit 收敛成功 | 版面 OK | 进入 QA |
| autofit 失败（历史最佳报告） | 边界内放不下 | 接受 + 报告用户人工决策 |
| `--visual` 像素诊断（空白带） | 视觉稀疏 | 调配比 / 建议加图 |

**响应机制（反馈环，≤2 轮防死循环）**：

```
成版 → linotype 排版（autofit 默认开）
  → 解析 build.py 输出 + .log（Plate content / Overfull / autofit 报告）
  → 版面健康报告（每版 fill + overfull 状态）
  → 不达标？按上表自动调整 plates/*.md → 重排（第 2 轮）
  → 仍不达标？停止 + 诚实报告给用户
```

## 五、一键流程与交付物

**目录布局**（每日一份）：

```
~/news/daily/2026-08-05/
├── sources/          # 信源归档：每版一个 md（URL/记者/站点/摘录原文）
├── plates/           # 生成的 p1-p4.md（linotype 消费）
├── out.pdf + out.log + out.tex + layout.json
└── compositor.log    # 日报工作日志（搜索→摘录→调整→QA 全程）
```

**一键流程**（用户喊"做今天的日报"）：

```
1. 搜索   4 版并行抓权威源（RSS 首选 → 主页抓取 → 兜底）
2. 摘录   尽量原文复制粘贴；记录 URL/记者/站点
3. 成版   按字段格式写 plates/p1-p4.md（中长篇+简讯组合）
4. 排版   调 linotype build.py（--docopts 固定报纸配置）
5. 响应   读信号 → 版面健康报告 → 自动调整（≤2 轮）
6. QA     pdfcheck + --visual 视觉验收
7. 归档   信源归档 + 工作日志落盘
8. 交付   报告：PDF 路径 + 版面健康报告 + 信源清单
```

## 六、目录结构与文件清单

```
~/.claude/skills/compositor/          ← skill 本体
├── SKILL.md                          # compositor 手册（编排者模式，linotype 知识内嵌）
├── scripts/
│   ├── fetch_sources.py              # RSS 拉取 + 主页抓取（多信源并行）
│   ├── build_plates.py               # 素材 → plates/p1-p4.md（字段格式 + 归属）
│   └── parse_signals.py              # .log/build.py 输出 → 版面健康报告（结构化）
└── tests/
    ├── run_tests.py                  # 测试矩阵（仿 linotype 25 项结构）
    └── scenarios.md                  # 压力场景

~/news/daily/                         ← 日报工作区（每日一份）
~/news/compositor/docs/               ← 设计文档/实现文档
```

## 七、测试策略

| 类别 | 覆盖 |
|---|---|
| 材料解析 | 字段格式正确性、归属格式（记者名/站点）、转义 |
| 信号解析 | typeout → 结构化（fill / overfull / autofit 状态） |
| 集成 | mock 信源 → 一键流程 → PDF + 归档 + 日志齐全 |
| 场景 | 溢出自动收敛 / 太空自动补简讯 / 信源抓取失败优雅降级 / 付费墙回退 |

## 八、边界与诚实原则

- **摘录忠实**：尽量原文复制，不编造；改写段落保留来源归属句
- **亲中立场透明**：信源以中国官方媒体为主——立场是编辑决策，摘录事实不改写
- **不做假**：付费墙截断标注"摘要摘录"，不伪装全文
- **防死循环**：反馈环 ≤2 轮，超出停止并诚实报告
- **成功标准**：0 Overfull 或 autofit 诚实失败报告；fill ≥ 45%；归属完整；PDF + 归档 + 日志齐备

## 九、实现顺序（供 writing-plans 消费）

1. `fetch_sources.py`：RSS 解析 + 主页抓取 + 信源清单配置
2. `parse_signals.py`：版面健康报告
3. `build_plates.py`：素材 → plates（字段 + 归属 + 中长篇/简讯配比）
4. SKILL.md：编排者手册（linotype 调用 + 信号响应规则）
5. 测试矩阵 + 场景
6. 端到端试跑（真实信源出第一期样报）
7. 交付物归档 + 工作日志
