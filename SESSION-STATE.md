# Imposer — Linotype 的拼版工（会话状态交接）

> 保存：2026-08-07 02:00 UTC — 第十一轮：归属增强 + 主栏补白 + 垃圾过滤 + 视觉协议修复
> 状态：**全链路打通 + 4 版填充全达标 + 主栏底部填满 + 垃圾素材全剔除**（imposer 回归 58/58 + linotype 30/30；晚刊 P1 101% / P2 98% / P3 96% / P4 96%，autofit 收敛 columns=3/10.3pt + demand 无需求 + pdfcheck 4/4 + 视觉验收双页 PASS；主条/副条/简讯全部带 日期·站点·记者；P1 主栏底部空白 37-41mm → 0.7/0.0mm 且无重叠；26 条 UI/页脚垃圾剔除）
> 完整开发史：`docs/DEVELOPMENT-HISTORY.md`（Phase 0-10 + 08-06 十轮）+ linotype `docs/DEVELOPMENT-HISTORY.md`（Phase 0-6 + bug #1-33）
> 血泪经验：**60 条**（#1-60 连续，含 #46 调研方法论全局规则 + #47-55 几何修复 + #56-60 出报闭环与补白）
> 公开仓库：**https://github.com/8cli/imposer**（MIT，master @ 178ade0）+ **8cli/linotype**（main @ 31ba131）

## 一、项目定位

**Imposer 是 Linotype 排版引擎的拼版工（compositor）**——需求驱动的英文日报编排器：

- Linotype 是**需求方**：版面缺内容时输出补稿单 `demand.json`（fill % / 缺口 pt / 需求规格）
- Imposer 是**供给方**：按单找稿（topic × words × min_kind）→ 压缩改写 → 补稿 → 重排 → 直到"已填满"

**核心差异化**：需求-供给契约（比单向信号更精确——引擎明确说缺什么）。全面亲中（中国官方媒体为主源）、只压缩不扩写（用户铁律）、诚实失败（不编造）。

## 二、完整能力

### 核心组件（skill/scripts/）

| 组件 | 文件 | 能力 |
|---|---|---|
| 信源配置 | `sources.json` | **66 已验证源**（P1 17 / P2 23 / P3 15 / P4 11）；**53 源走本机 RSSHub**（80%：社区现成 + 自定义 12 + fix 10），13 源直抓 |
| 信源抓取器 | `fetch_sources.py` | 并发 RSS+主页（as_completed + 8s 超时，55 源 ~28s）、XML 实体容错、英文过滤 |
| 需求解析器 | `parse_demand.py` | 读 linotype 输出 + demand.json → 健康报告（4 种 Overfull 模式） |
| 需求-供给匹配器 | `supply.py` | 按单匹配（topic×words×min_kind）、rewrite 标注、used 去重 |
| 改写压缩器 | `rewrite.py` | **LLM 压缩兜底**（只压缩不扩写铁律；主路径是 agent 执行） |
| 素材成版器 | `build_plates.py` | 素材 → linotype 字段格式 plates（归属/配比/时效/跨版去重/题材降权） |
| 回归套件 | `tests/run_tests.py` | **54 项**（fetch 10 / demand 4 / supply 16 / build_plates 19 / rewrite 5） |

### 与 linotype 的接口（跨仓库协议）

- linotype `build.py --demand`：autofit 收敛后按 fill 缺口输出 demand.json（Task 3 完成，25/25 回归不破）
- linotype `--docopts fill_min=0.65`：可配置太空阈值（默认 0.45；0.65 严肃报纸标准），从 cls docopts 过滤防 keyval 错误

### 需求-供给契约（demand.json 协议）

```json
{"plates": {"P3": {"fill": 0.31, "deficit_pt": 104.2, "requests": [
  {"type": "brief", "count": 2, "words": [60, 90], "topic": "space", "min_kind": "agency"}]}}}
```

- 需求类型按缺口：`<100pt → brief` / `100-300pt → main` / `>300pt → deep_dive`
- topic/min_kind 按版：P1 world/military+china-official · P2 ai/tech+company · P3 space+agency · P4 china-tech+china-official

### 代理执行改写架构（用户决策，终审落地）

- **主路径**：supply 标注 `needs_rewrite` + `target_words` → **agent 按 SKILL.md 改写规则直接压缩**（agent 本身是 LLM，零 API 调用）
- **兜底**：rewrite.py 保留（headless cron 备胎，Claude API + SSE 兼容）
- 铁律：只压缩不扩写（≤上限逐字返回）、target_words 硬上限、保留归属

## 二点五、08-06 第二轮进展（FreshRSS 经济架构）

**本轮核心**：用户洞察"RSSHub→imposer 实时抓取分析浪费算力"→ 确立 **FreshRSS 聚合 + 全文入库 + 查库选文** 经济架构，并在调研铁律下验证落地。

### 调研铁律（用户决策，写入 ~/.claude/CLAUDE.md）
任何开发前必须全面调研成熟方案，禁止重复造轮子。实例：RSS 全文提取用 Mozilla Readability（readability-lxml）+ FreshRSS af-readability（Fivefilters Readability.php），不手写正则。

### 信源扩充（67 源，41 走 RSSHub）
- P2 23 源：+Meta AI、DeepMind、Google Research、Amazon AWS(EN)、Wired AI、TechCrunch（社区路由实测可用）
- P4 11 源：+The Economist Sci-Tech
- 路由策略：社区现成 22 + 自定义 2（cnsa/esa）+ fix 10（tassfix/cfrfix 等替代失效社区路由）
- 教训：社区路由大量失效（10 空），需 fix 路由补位；反爬是客户端特定（spacenews 403 vs Python 直抓 200）

### fill_min 0.95（严肃报纸标准，用户决策）
留白 ≤5%，每版都要求。SKILL.md 排版命令 + linotype 默认 FILL_MIN 都改 0.95。四版全部触发补稿单（P1 60%/P2 61%/P3 59%/P4 56%）。

### Readability 全文（替换手写正则）
- readability-lxml（Mozilla Readability Python 移植）替换 fetch_fulltext 的 `<p>` 正则 + 长字符串拼接
- 实测：GT 529 词（原 85）、DefenceTalk 359
- 抓取器修复：fetch_page 全候选抓摘要/全文（原 SUMMARY_TOP_N=2 致 P1 131 条 124 空摘要）

### FreshRSS 经济架构（用户决策）
```
RSSHub(标题+链接) → FreshRSS 聚合(41 feed) + af-readability 全文入库(SQLite)
                  → imposer fetch_freshrss.py 直接查库选文（不实时抓取分析）
```
- FreshRSS Docker :1202（持久化卷 + CRON_MIN=0,30 定时刷新），SQLite，50 feed 1322 篇入库
- **直接查 SQLite 优于 API**（用户提醒：API 的 toGReader 不返回 content；SQLite entry 表 content 含全文）
- **af-readability 根因修复（2026-08-06 午后，全文覆盖 11.3% → 94.8%）**：早先"af-readability 只对 P2 成功、P3 太空源失败"的归因**错误**——真相是配置格式坑：`ext_af_readability_categories` 必须是 **JSON 字符串**（`'{"2":true,"3":true,"4":true,"5":true}'`），扩展用 `attributeString()` 读，PHP 数组格式读不到 → 配置全空 → 所有文章静默跳过。加上三次容器重建丢了扩展文件 + `extensions_enabled` 空，两层叠加导致 88.7%（1045/1178）入库无全文。修复：重装 Niehztog/freshrss-af-readability v0.4（⭐103，PHP 8.1+/dom/xml/curl/mbstring 已满足，纯客户端无外部依赖）→ config.php 两处配置（enabled + JSON 字符串）→ 清空 entry + 重置 lastUpdate 全量重灌 → **1091/1151 篇全文（94.8%）**，P1 军事（CFR 66/68、CSIS 66/67、Naval News 15/15）与 P3 太空（NASA/ESA/JAXA 全 100%）短板全消。唯一 0 全文：NYT（付费墙，预期）。**教训**：FreshRSS 扩展的 per-feed 配置存 config.php 顶层 `ext_` 键，值格式是 JSON 字符串不是 PHP 数组；容器重建会丢扩展与配置，重建后必须两步都配（详见 fetch_freshrss.py 头注释）
- 四版主条供给验证：P2 Google Research 1296 词、P3 JAXA 1197、P4 Nature 1222；**P1 军事全文弱（CFR 5 词，待补）**

### 08-06 第三轮：直抓源迁入 RSSHub（用户决策：直抓源进 rsshub 更合理）+ 首期实报

**任务 #74 结论（AI 公司路由 = 调研否决）**：xAI/Moonshot/Zhipu/Alibaba **不写路由，保留直抓**——全是 Next.js SPA（xAI 153 个链接全是字体文件、Alibaba 0 个 news 链接、CGTN 频道页全 404），RSSHub 同样抓不到。这不是"没做"，是调研后正确的工程决策。

**6 个自定义路由**（全部实测 ✅）：
- `/xinhuaenglish/news`（P1/P4，P3 共用）——english.news.cn 首页 23 条（含神舟 21）
- `/globaltimes/news`（P1/P4）——globaltimes.cn 首页 25 条（含独家）
- `/brookings/articles`（P1）——brookings.edu /articles/ 17 条
- `/rand/articles`（P1）——rand.org /pubs/ 7 条
- `/iter/news`（P4）——iter.org 官方 RSS 转发 10 条
- `/isro/news`（P3）——isro.gov.in 首页 200 条

**4 个社区路由接线**：asianmilitaryreview(43)/defencetalk(26)/eurasiantimes(53)/ieeespectrum(20) 全部 ✅

**保留直抓 13 源（诚实说明）**：xAI/Moonshot/Zhipu/Alibaba/CGTN（SPA）、SpaceX/Rocket Lab（JS 渲染）、Blue Origin(429)/SpaceNews(403)/New Scientist(406)（反爬，RSSHub 客户端被拒但 Python 直抓 200）、ABC News（源站 feed 404）

**fetch_freshrss.py 映射升级**：按 **rsshub path** 而非 feed 名映射——P1/P3/P4 共用 Global Times/Xinhua feed 时每版独立取到（源名各自保留）

**首期 2026-08-06 实报（fill_min=0.95 验证填充 ≥95%）**：✅ 跑通
- 4 版全部成版：P1 伊朗战事(DefenceTalk 319词) / P2 NVIDIA 黄仁勋(IEEE 350词) / P3 ISRO Gaganyaan(326词) / P4 贵州漂流(GT 297词)
- 需求-供给闭环 ≤2 轮：P1 63%→达标、P2 61%→95%、P3 59%→95%、P4 56%→95%
- autofit 迭代 5-6 "达标(最小 95%)"，demand.json 无需求
- 视觉验收仅剩 9.7mm 栏平衡微小空白带（非内容不足）

**linotype 统一单一仓库**（用户质疑"所有 linotype 文件应该统一"）：
- `~/news/latex` = 唯一工作目录 + 唯一 git 仓库（8cli/linotype）
- `~/news/linotype-repo` 副本**已删除**——不再双目录手同步
- 开发产物（SESSION-STATE/newspaper.*/archive-*.cls）入 .gitignore 不进公开仓库

### 08-06 第四轮：出报质量修复（用户验收三问题）

**问题 1：P1 左下角大块留白**（用户："第一版左下角一大块留白，达到 95% 以上填充率？"）
- 根因：`split_paragraphs` max_paras=4/8 截断主条——319 词完整主条被截到 108/182 词，main-aside 主栏 2 栏排不满 → 底部全空（视觉实证 0 墨迹）
- 修复：主条完整使用（max_paras=14 覆盖 400 词上限）
- 结果：P1 主栏 **53% → 80%**（左下角大块留白消除）
- 诚实缺口：P1 素材池最长仅 359 词（DefenceTalk 军机坠毁），仍填不满主栏 20% 版底——需补 P1 长文源

**问题 2：HTML 实体字符**（用户："出现了 &#8220 这样的字符，需要内容清洗"）
- 根因：fetch_freshrss.py 提取 content 后没 unescape——af-readability 存纯 ASCII 实体（mb_encode_numericentity），`&#8220;`（"）`&#8217;`（'）`&amp;` 直出到 plates（实测 **571 条**）
- 修复：`html.unescape(text)` + title 同样 unescape
- 结果：**571 条 → 0 条**（plates 层 4 版全零）

**问题 3：P3 标题过大/单词间距不协调**（用户："第三版左上角标题过大"）
- 根因：P3 标题 84 字符 ISRO 全名，3.58× 字号 display 排版过大
- 修复：`_clean_headline` 超长标题截断 60 字符（按词界/括号）；`_clean_deck` 去导航残留（'Home /'）与标题重复
- 结果：P3 标题正常（Perseid 流星雨 38 字符），DECK 无重复无残留

**附带修复：主条按版控制（防溢出）**
- P2-P4 等宽 3 栏容量 ~280 词——P3 327 词 ISRO 实测 753pt > 742pt 溢出 141pt
- 修复：P2-P4 主条截到 280 词（按词界句界），P1 完整（侧栏容量大）
- 结果：全版不再溢出（Plate content 622-728pt 全部 ≤ 版心）

**填充率诚实状态**（用户质疑"达到 95%？"）：
- 重跑 supply 闭环后：P3 达标、P1 84%、P2 87%、P4 89%——**未到 95%**
- autofit 已到边界（columns=2 最小、字号最大）+ "内容天然短"——素材总量不足
- P1 主条池极限 359 词；P2-P4 短摘要多、长稿靠 supply 全文预取
- **诚实结论**：当前 84-89% 是现有素材的最佳结果，到 95% 需补长文源（P1 军事深度稿）

### 08-06 第五轮：fulltext 选材修复（用户指正"为什么看摘要而不是全文长度？"）+ 视觉阈值对齐

**根因（真正的逻辑缺陷）**：build_plates.py 全程用 `summary` 词数选材/排序，而 fetch 层把
summary 截到 400 字符（≈60-80 词）——**长文全在 `fulltext` 字段**（P1 实测 379 条 ≥200 词
全文躺着未用），主条永远选到短摘要 → 版面填不满（P1 84% 根因）。supply 的全文优先只对
demand 补稿生效，成版器本身不用全文。

**修复（build_plates.py）**：
- 新增 `_content_words(item)`：fulltext 优先（无则回退 summary）
- `_length_key` / `pick_main_stories` / `pick_briefs` 长度轴全部改用 fulltext 词数
  （供给素材 used=True 仍按交付词数 summary 匹配规格距离）
- 主条正文 `main[0].get("fulltext") or summary` + 按版上限截断（P1 400 词 / P2-P4 280 词，
  句界优先）；STORY-B 同样 fulltext + cap（P1 侧栏 200 词 / P2-P4 120 词）
- 简讯数按版差异化（血泪 #22 实测）：P1/P3 3 条已满版，P2/P4 各 4 条
  （+2 条致 P2 溢出 744.5pt > 742.6 且 autofit 压字号拖累 P3 掉 9%）

**结果（fill 84-89% → 4 版全达标）**：
- P1 84% → **98.7%**（STORY-B 81→171 词全文填满侧栏——原先左下角留白彻底解决）
- P2 89% → **100.2%**（+1 条 Gemini Robotics 简讯；vsplit 截断 1.4pt 不可见）
- P3 达标 → **95.6%**（autofit 全局压字号所致，P2 收敛后可再回 99.9%）
- P4 90.7% → **99.85%**（+1 条 GT 中国大使馆简讯）
- **视觉验收 PASS**（两页无空白带）+ demand.json 无需求

**pixelcheck 阈值对齐（linotype）**：
- `min_gap` 8 → **12mm**（与 fill_min=0.95 对齐：12mm = 版心 261mm 的 4.6% < 5%）——
  原先 8mm 会把 95% 达标底边（P3 9mm=4.4%）误报 FAIL；右半版顶部 9.7mm 是 KICKER
  小字（79% 字号 + LetterSpace=12 太稀疏）被墨迹阈值吞的**误报**，12mm 后自然消掉
- build.py 空白带行提取改正则 `^\s*(列\d+|[左右]半版|整页):`——argparse help 行
  （含"空白带"/"mm"字样）不再误入报告
- 教训：pixelcheck 的空白带阈值必须与 autofit 的 fill_min 对齐，否则"像素说空、
  fill 说达标"的矛盾永存

### 08-06 第六轮：全面审计 + multicol 整盒丢失修复（血泪 #25/#26/#27）

**审计发现（4 个并行 agent）**：epoch 秒日期 bug（已修）、max_items 截断 no-op、
16 源静默缺失、Al Jazeera 阿拉伯语路由、mainaside 宽度公式、fill 计量等。

**本次修复的核心 bug——P3 双版正文静默丢失（比留白更严重：内容消失）**：
- 表象：P3（第 2 页首版）只剩版头 53.7mm，但 fill 报 100%（假达标）
- 根因链（全部实证，最小复现 + tracing）：
  1. @colht 动态计算用 `\ht\linotype@platebox`——vbox 构造中读 =0 →
     multicol 用满 contentH → 版头 + multicol 超 contentH
  2. plate 的 vsplit 兜底触发 → vsplit 对 multicol 整盒**全切**（血泪 #5）
     → 整盒丢弃 → 版面只剩版头
  3. `\begin/\end` 的 `\begingroup/\endgroup` 回滚 `\setbox` 和 `\newif`
     赋值 → headerbox=0、multicol flag 丢失（必须 `\global`）
- 修复：`\plateheader` 环境收集版头到独立盒（`\global\setbox` + `\unvcopy`），
  storycolumns `@colht = contentH − 版头 − 4pt`（multicol 盒 ≤ contentH），
  vsplit 兜底跳过含 multicol 的版（`\if@linotype@multicol`，`\global` 防回滚）
  ——multicol 超高时自然溢出 + Overfull 报告（truncated >5% 驱动 autofit
  缩字号，不再静默丢内容）
- 附带：inbrief 栏宽自适应（#25）、TEXINPUTS 锁定引擎目录 cls（#27，
  Kpathsea 优先加载 tex 目录的旧 cls 导致 plateheader undefined）

**结果**：4 版全达标 ≥95%（P1 98.5 / P2 99.1 / P3 101.9 / P4 95.6），
autofit 真收敛（此前假收敛 100% 是内容丢失的假象），视觉 PASS，
demand 无需求。回归 linotype 25/25 + imposer 57/57。

### 08-06 第九轮：博客发布 + CLAUDE.md 上传 8cli/claude（用户收尾）

**博客发布**（pblog 创作模式全链路）：
- 草稿《排版引擎 + 拼版工：我造了一台 AI 日报印刷机》→ eman 阮一峰式润色
  （24 处改动 + 事实待核 2 项确认）→ dry-run → 发布
- **URL**: https://www.clid.net/2026/08/ai.html（post_id 3484617346273784637）
- 覆盖：CSS→LaTeX 选型 / 固定版心不推页战争 / 需求-供给契约（GitHub 0 结果）/
  RSSHub+FreshRSS 经济架构 / 55 条血泪 / 心路历程，结尾诚实"开创≠里程碑，0 star 起点"

**CLAUDE.md 上传 8cli/claude**（用户询问"文档和规则上传没有"）：
- 发现仓库 CLAUDE.md 是旧版（98 行），本地有"开发前调研铁律"整节（含第 6 条）未同步
- 同步最新 CLAUDE.md（114 行）+ README 补 skills 指引 → `7829d5d`
- 修正第 6 条"54 条血泪"→"55 条"
- 三仓库现状：imposer `5852179` / linotype `4c3e105` / claude `7829d5d` 全部推送

### 08-06 第十轮：晚刊出报闭环 + 4 处修复（用户"形成今日报纸"）

**晚刊完整出报**（全部修复落地后重跑 2026-08-06 报纸）：
- 抓取 389 条素材（全文覆盖 331/85%）→ 审料门 → 成版 → autofit → 供给闭环 3 轮
- **最终收敛**：columns=3 / bodyfontsize=10.84pt，fill **P1 95% / P2 104% / P3 100% / P4 102%**，
  demand 无需求，pdfcheck **5/5**（Overfull 0 / Error 0 / MediaBox 420x297 / 6 字体 / 2 页）
- 视觉：第 2 页 PASS；第 1 页版底留白 13-21mm（内容天然短，fill 达标，可接受）
- agent 改写 4 条（AWS ACME 81 词 / AWS 投诉分类 74 词 / AWS HPC 70 词 / NASA TEMPO 70 词），
  P4 中国科技缺口诚实报告（Xinhua 全 0 词、西方科技补充）

**出报发现 4 处真实 bug（全部修复 + 提交）**：

| # | 症状 | 根因 | 修复 |
|---|---|---|---|
| 56 | P2 主条 162/280 词，fill 84.7% | split_paragraphs 按句切段 + max_paras 硬截断——短句体全文（Cloudflare 每句一行）切 20+ 短段只留 12 | 动态目标段长 ceil(词数/max_paras)：词数全保留 + 段数用满（build_plates 8dca6a9） |
| 57 | P3/P4 3 轮供给 fill 纹丝不动 | 固定 n 简讯槽 + 补稿排最前 → 新补稿挤掉同槽旧简讯（替换空转） | 补稿全保留追加 + 普通简讯补足 n（append-not-replace） |
| 58 | 补稿后 P2 溢出 5.4% 反逼全局降字号拖垮 P1 | BRIEFS 输出 [:n_briefs] 再截断 + 补稿累积无上限（P2 10 条简讯 782pt） | 统一上限 n_briefs + 2 |
| 59 | demand/visual 误读溢出数据假 FAIL | autofit 收敛 best_bs==lo 用内存缓存，out.log/out.pdf 停在最后一次实际编译（二分上界试探 10.92pt 溢出 106%） | 收敛统一重编译 lo（build.py 34b32c0）；测试断言对齐 ≤5% 微小截断语义（25/25） |

**实测提升**：P2 84.7% → 94.8% → 收敛 95-104%（autofit 收敛点 66% → 92% 基础 fill）。

### 08-06 提交（imposer 6fc39d7 → a62e018 + linotype 69cfe27 → b314744）
imposer 完整链（第八轮后）: 6fc39d7 → 0fb273c → cd0d4c5 → f49940b → 6f2ddaf → 02eb47b →
  88cdf12 → dde4ee9 → 353dca1 → 6f868f3 → 68a8413 → ad2b785 → b73d667 → 22a031e →
  97c67bb → 2400731 → 620d6c8 → 6a7d82b → 08b5773 → 999599d → 72e7886 → d1df310 →
  bb0fc2a → e887d58 → a62e018
linotype 完整链: 69cfe27 → 2e4450c → aa7635d → d4ecb3e → 7f819b7 → 3feecf2 → 6fd5763 →
  45d51de → 4a9e897 → 74d5890 → 1fc7da9 → a9e3468 → 61ac1b2 → ca16c17 → 981eb2c →
  3d2120b → 090fc9b → 1c3ccfd → 891f0c9 → 49fbe14 → 3db6d05 → d3648ea → b9a03de →
  0077a90 → 81dfd09 → e3baeb2 → b314744

## 三、验证状态

- ✅ **终审 CLEAN**（opus 终审 → fix wave → 2 轮 re-review → 独立重跑实证全过）
- ✅ 回归：imposer **54/54** + linotype **25/25**
- ✅ E2E 实证（真实缓存重跑）：0 归档 URL（2017 旧闻过滤）、0 跨版重复、供给 NASA 简讯真正进版
- ✅ agent 架构：SKILL.md 8 步引导式闭环 + 改写规则章节，PYEOF 零遗留
- ✅ 文档诚实化：README×2 / HISTORY 声明与产物逐项比对通过（上轮虚假实证教训已纠正）
- ✅ 公开仓库推送：imposer @ dde4ee9、linotype @ ca16c17（含 --demand + fill_min + inbrief 多组）
- ✅ 持久化：linotype 统一单一仓库 ~/news/latex（副本 linotype-repo 已删，重启不丢）
- ✅ 首期实报：~/news/daily/2026-08-06/out.pdf（2 页 A3 横版 4 版，**P1 98.7% / P2 100.2% / P3 95.6% / P4 99.85% 全达标 ≥95%**，视觉验收 PASS，demand.json 无需求）
- ✅ 出报质量修复：HTML 实体 0 残留、标题截断、主条按版控制（P1 主栏 53%→80%）
- ✅ **第五轮 fulltext 选材修复**：fill 84-89% → 4 版全达标（选材长度轴 summary → fulltext；主条/STORY-B 正文全文优先 + 按版截断；简讯 P2/P4 4 条）+ pixelcheck 阈值对齐（min_gap 12mm）

## 四、关键架构决策

### 需求-供给契约（项目灵魂）

Linotype 缺内容时下补稿单（demand.json），Imposer 按单找稿。比单向信号更精确——引擎精确告诉你补什么。

### Agent 执行改写（用户洞察，终审落地）

imposer 是 skill，skill 由 agent 调用——agent 本身就是 LLM，改写应由 agent 直接执行。拆除了 rewrite.py 调 API 的绕路（anthropic 包/PEP 668/SSE 解析/CLI 污染一堆坑）。

### 严肃报纸标准（用户决策）

只允许正常留白，空白多就增报道/简讯。fill_min 0.65（可配置）触发补稿单。

### 只压缩不扩写铁律（用户决策）

允许压缩长报道，不允许扩写（质量 + 版面控制）。短素材原样使用，宁缺毋滥。

### 全面亲中（用户决策）

中国官方媒体（GT/Xinhua/CGTN/China Daily）为主源；西方媒体仅补充；智库每期一篇深度。

## 五、终审血泪经验（勿重蹈覆辙）

1. **SKILL.md 闭环脚本必须每轮 build_plates 再生成**——supply 回填缓存后不重成版，plates 永不更新 → 循环空转
2. **used 标记必须持久化**——supply 的 used 是局部集合，回写缓存不带标记 → 第 2 轮重复供给同一批素材
3. **按单供给的素材要槽位优先**——pick 只按 kind_rank 会忽略 request 规格（NASA 简讯被 china-official 压掉）
4. **主条最低词数门槛**——38 词素材不应拿主条头条（MIN_MAIN_WORDS=100）
5. **时效过滤三层兜底**——date 为空时用 URL 日期路径（`/201712/12/`）+ 标题旧年份保守排除
6. **跨版去重要池级**——P3/P4 共用 China Daily RSS、P1/P4 共用 GT/Xinhua，版内去重不够
7. **fix 报告实证必须可复现**——上轮 fix 报告"14 条唯一/P3 全 NASA/2017 不进版"与产物矛盾被否，教训深刻
8. **本地代理返回 SSE 字符串**——ANTHROPIC_BASE_URL 指向转发代理时 messages.create 返回原始 SSE，需解析 `data: {json}` 行
9. **Claude CLI --print 会话污染**——输出混入会话系统提示；stream-json + verbose 才可靠
10. **fill_min 不过 cls**——是 build.py 阈值不是 LaTeX keyval，不过滤会 keyval error + 空 fills 假收敛
11. **空 fills = 假收敛**——编译失败无 Plate content 行，autofit 以空 fills 收敛；必须验证日志有内容
12. **并发抓取用 as_completed**——ex.map 阻塞在最慢线程；as_completed 逐个返回 + 8s 超时
13. **supply 回填必须按 URL 替换而非 append**——append 致同 URL 双条目（原始短摘要 + 供给长摘要），_dedup 保留第一条原始版 → 供给素材永不进版（2026-08-06 出报实证：plates 不更新、fill 卡 59%）
14. **FreshRSS 扩展配置值格式是 JSON 字符串不是 PHP 数组**——attributeString() 只读 string；`ext_af_readability_categories` 写成 PHP 数组 → 配置静默全空 → 所有文章跳过（88.7% 无全文根因）
15. **容器重建丢扩展文件 + extensions_enabled**——三次重建后 FreshRSS 回到干净状态，扩展全丢；重建后必须重装扩展 + 两步配置
16. **inbrief 宏只渲染 3 条简讯**——linotype build.py `p['briefs'][:3]` 硬编码截断；P2/P3 主条池不足时填充上不去，需按版差异化简讯数（P1/P4=3 达标，P2/P3=6 补填充）
17. **HTML 实体必须 unescape**——af-readability 存纯 ASCII 实体（mb_encode_numericentity），fetch 层不 unescape 则 &#8220; 等直出到 plates（实测 571 条）；加 html.unescape 一次解决
18. **主条截断是 P1 左下角留白根因**——split_paragraphs max_paras=4/8 把 319 词截到 108/182 词，main-aside 主栏排不满；主条必须完整（max_paras=14）
19. **3 栏布局主条上限 ~280 词**——P3 327 词实测 753pt > 742pt 溢出 141pt；P2-P4 主条需按词界截断到 280，P1 main-aside 容量大才可完整 400 词
20. **超长标题要截断**——84 字符 ISRO 全名在 3.58× display 字号排版过大、单词间距不协调；_clean_headline 截 60 字符
21. **选材必须看 fulltext 不看 summary**——fetch 层 summary 截 400 字符（≈60-80 词）无区分度，长文全在 fulltext（P1 实测 379 条 ≥200 词全文躺着未用）；按 summary 选主条永远填不满版面（P1 84% 根因）。_content_words 全文优先是成版第一原则
22. **简讯数按版差异化，加多了适得其反**——P2/P4 缺 44/32pt 各 +1 条（4 条）即达标；+2 条（5 条）致 P2 溢出 744.5pt > 742.6，且 autofit 压字号拖累 P3 从 99.9% 掉到 90.6%。每次改版后看 autofit 收敛，别凭感觉加内容
23. **pixelcheck min_gap 必须与 fill_min 对齐**——8mm 会把 95% 达标底边（9mm=4.4% < 5%）误报 FAIL；对齐 12mm（= 版心 261mm 的 4.6%）后"像素说空、fill 说达标"矛盾消除。KICKER 小字（79% 字号）稀疏也会被墨迹阈值吞成"空白带"——先放大确认再动内容
24. **argparse help 含 % 需 %% 转义**（argparse 的 help 是 % 格式化字符串）+ build.py 提取报告行须用正则精确匹配（`^\s*(列\d+|[左右]半版|整页):`）——help 文本含"空白带"/"mm"字样会误入视觉报告
25. **inbrief 是通栏设计（3×0.319\contentW 并排），进 multicol 栏内必溢出 348pt**——\linewidth 自适应：栏内单列堆叠（同 \asidebriefs），通栏保留 3 栏并排。血泪：全版宽宏不能直接搬进栏内
26. **vsplit 对 multicol 整盒是全切——内容超高时整盒被丢，fill 虚高假达标**。根因链：① @colht 动态计算用 \ht\platebox（vbox 构造中=0）→ multicol 满版 → 版头+multicol 超 contentH → vsplit 触发；② vsplit 切不动 multicol 整盒 → 整盒丢弃 → 版面只剩版头（P3 双版实测 53.7mm，fill 报 100%）；③ \begin/\end 的 \begingroup/\endgroup 回滚 \setbox 和 \newif 赋值（需 \global）。修复：\plateheader 收集版头（\global\setbox + \unvcopy），storycolumns @colht = contentH − 版头 − 4pt，vsplit 跳过含 multicol 的版（\global flag）——超高自然溢出 + Overfull 报告（truncated >5% 驱动 autofit 缩字号）
27. **Kpathsea 优先加载 tex 文件目录的 cls**——产物目录残留旧版 linotype.cls 会静默覆盖引擎目录新版（实测 plateheader undefined，编译用了 daily 目录旧 cls）。compile_tex 设 `TEXINPUTS=引擎目录:` 锁定
28. **mainaside 宽度公式**——mainW = 2c/3 − g/3、asideW = c/3 − 2g/3（原 +g 每版水平溢出 10.6pt、两栏不对称）
29. **fetch_freshrss max_items 截断 no-op**——continue 只跳内层循环，每版拉全库 477 条；改按 feed 配额（每源最新 8 条），低量智库源不被高量源挤掉
30. **配置源 vs 已订阅 feed 无对照**——/xinhuaenglish/news 未订阅致 P1/P3/P4 三源全空零告警；加启动校验逐源告警
31. **Al Jazeera rsshub 指向阿拉伯语站**——英文源形同虚设 + 30 条阿拉伯语占位污染 P1 候选；删 rsshub 回退英文 RSS
32. **fetch_sources title 不 unescape**——RSSHub 双编码 &amp;amp; 直出到版面；对称修复
33. **fetch_freshrss 不写信源归档**——审料门（人工复核 sources/pN.md）失去输入；补写同格式归档
34. **\end{plate} 后缺 %**——换行被 TeX 读为空格，两版间 2.51pt 空格胶水 → 每张双版页 1.67pt Overfull
35. **tex_escape 不转义反斜杠**——正文含 \ 编译失败；占位符方案（\x00 → \textbackslash{}）避免二次转义
36. **expandedtitle 固定字号**——26pt 不随 bodyfontsize 缩放，比例 3.06×→2.36× 失调；改 \linotype@bs*274/100
37. **typeout 双单位 ptpt**——\the\dimexpr 已含 pt 再拼 pt；三处修复
38. **_kind_for_feed 硬编码路径**——用自定义 sources 跑 kind 全回退 tech-media；改用传入 sources
39. **DeepSeek rsshub 是中文 API 文档**——changelog 当新闻进 P2；删 rsshub 回退官网直抓
40. **fetch_fulltext 无 unescape**——与 fetch_freshrss 不对称（&nbsp;→\xa0 残留）；对称修复
41. **write_demand 按 truncated>5% 判定**——原 re.search("Overfull") 误杀微超版的需求单（P2 76.9% 补稿被吞）
42. **P1 题材负向词为空**——长度优先把 Brookings 医保论文推上主条；加 medicare/hospital 等降权
43. **main-aside 版头预算 60pt 假设错误**——实际版头 275pt（DECK 250 字符 90pt）；DECK 截 120 字符版头降 213pt，main 栏空间释放
44. **mainstory colH 反复调试教训**——vsplit 截断 vs vtop 自然高的栏平衡反复横跳；main 栏短于 aside 是版面平衡特性（fill 达标），接受列尾空隙，不强制等高
45. **P2 等宽栏简讯数决定填充**——4/5 条 93.8%、6 条 98.2%；简讯数按版实测微调
46. **调研方法论（全局规则 #6，2026-08-06）**——技术选型调研不能只看"它赢在什么"，还要评估"我们要对抗它的什么"。linotype 选 LaTeX 时评估了排版质量（赢），没充分评估"固定版心不推页"是 LaTeX 流水排版的设计反例——54 条血泪中约 30 条是纯 TeX 语义坑（boxed multicol/vsplit/topskip/\dimexpr 吞 \fi），大部分本可通过预先通读 multicol.sty/TeXbook 发现。调研深度标准：**至少能列出"我们要对抗的默认行为清单 + 预估代价"再定选型**。已写入 ~/.claude/CLAUDE.md 调研铁律第 6 条
47. **\vtop to\colH 是强制盒高，内容超高时溢出而非截断**——vsplit 切 264pt 内容在 vtop 重排后可能超高 → main 栏底部溢出。vsplit 只切行边界（按旧行距），vtop 重排（新行距）高度不同
48. **mainstory 两栏并排的视觉高度 = 单栏高度，不是两栏之和**（几何模型）——colH 上限 = contentH − 版头，版头 + 单栏 = contentH 精确填满
49. **mainstory colH 根本修复**——版头收集到 \linotype@headerbox（\global\setbox + \unvcopy + \storybody 设字体防 \deck/\byline 继承默认 11pt），colH = min(自然高/2, contentH − 版头)。P1 main 左栏 193.7→254.5mm，底部空白消除
50. **plate fill 计量幻影 dp**——vsplit 对含 hbox 两栏的 vbox 切分产生幻影 dp（P1 749.4pt 微超触发 vsplit 后 fill 虚报 1479pt=199%）。修复：\unvcopy 后量自然高（真实渲染高度），Overfull truncated 也基于自然高
51. **P1 主条 cap 340 防下边距溢出**——cap 355 实测微超 1.2%（内容延伸到 287mm > 版心底 281mm，下边距剩 10mm）；340 → 版头 + 单栏 = 723pt ≈ 97.4%，下边距恢复 16.4mm
52. **parse_demand 阈值对齐 linotype**——FILL_MIN 0.45→0.95（原旧默认误报健康）；Overfull 判定只认 plate 级 truncated>5%（原 re.search 字样把 0.9% 微截断也报 overfull → "✅ 版面健康"永不出现）
53. **demand.json 残留清空**——write_demand 无需求返回 None 不覆盖 → 旧补稿单残留（实测 P2 实际 98.2% 但旧文件报 93.8%），闭环步骤 7 白跑一轮；无需求时删除旧文件
54. **\topskip(11pt) 侵蚀页边距**——plate 是页面第一个盒子（minipage[t] 首元素 0 高规则），页面级 \topskip 胶 = 11pt 插在纸顶 → 每条版整体下移 3.9mm（顶 23.8 vs 设计 20、底 12.2 vs 16，底边小于左右违反报纸惯例）。\setlength{\topskip}{0pt} 实测顶边恢复 20.09mm
55. **aside column 截断接入 autofit**——P1 侧栏 792.4pt vsplit 截到 732.6pt（丢 49.8pt ≈ 21mm），截断后 plate content < contentH → 不触发 Overfull plate → fill 97.4% 假达标（内容静默丢失）。补解析 (main|aside) column 截断 >5% 即 overfull + P1 简讯 3→2 消除根源
56. **split_paragraphs 按句切段 + max_paras 硬截断丢主条词数**——"每句一行"的短句体全文（Cloudflare 等科技博客）把 280 词切成 20+ 短段，max_paras=12 截断后只剩 162/280 词（P2 fill 84.7% 虚低）。修复：动态目标段长 = ceil(词数/max_paras)——词数全保留 + 段数用满；散文体（句长 ≥ 目标）每句一段等价原逻辑
57. **固定简讯槽 + 补稿排最前 = 替换空转**——pick_briefs 选满固定 n 后新补稿挤掉同槽旧简讯，若新旧长度相近 fill 恒定不涨（P3/P4 3 轮供给 fill 纹丝不动）。修复：补稿（tier ≤1）全保留追加 + 普通简讯补足 n（append-not-replace 语义）
58. **补稿累积无上限过冲**——BRIEFS 输出 [:n_briefs] 再截断丢补稿（第 2 截断点）+ 补稿无限累积（P2 10 条简讯 → 782pt > 742pt 溢出 5.4%），反逼 autofit 全局降字号拖垮 P1（95.4%→89%）。统一为上限 n_briefs + 2

60. **\setbox\A=\B 中 \B 是盒号整数不合法**（2026-08-07 主栏补白重叠）——RHS 需 \box\B 前缀（\box 引用盒），否则 'A <box> was supposed to be here' 中断执行（\linotype@cutbox 是 \chardef 整数）。同类：leftbrief/rightbrief 共用一盒——\def 执行时才 \unvbox，此时盒已被 rightbrief 覆盖 → 两栏都显示右简讯。修复：独立盒 briefbox/briefboxR + \box\cutbox 引用。
59. **autofit 收敛不重编译最终配置 = 产物与判定脱节**——二分搜索 best_bs == lo 时用内存缓存 fills 判定收敛，out.log/out.pdf 停在最后一次实际编译（二分上界试探，可能溢出）——实测迭代 5 达标 10.84pt 但 out.log 是迭代 6 的 10.92pt 溢出 106%，demand/visual 误读溢出数据假 FAIL。修复：收敛确认统一重编译 lo（最终配置），产物与收敛点一致；测试断言对齐 ≤5% 微小截断语义（vsplit 兜底是设计内行为）

### 08-07 第十一轮：新闻报道归属增强（用户"加日期/站点/记者"）

**用户要求**：新闻报道加上日期、来源站点、记者名字。三要素在素材 JSON 里齐全（author/date/source），缺的是成版写入逻辑。

| # | 改动 | 内容 |
|---|---|---|
| 1 | `build_plates.py` | `clean_author` 清洗 RSS `;` 多作者（';A; B'→'A, B'）；`fmt_date` epoch/ISO/RFC2822 → `Aug 6, 2026`（URL 兜底，失败省略不伪造）；`byline_of` 补日期 → `By {记者} · {站点} · {日期}`；STORY-B 加 `BYLINE-B:` 独立署名；简讯归属 `— {站点}, {日期}.`（多作者压缩"首名 et al."防单行膨胀） |
| 2 | `build.py` | 解析 `BYLINE-B:` → story['byline']；main-aside 传 `\asidestory` 3 参、等宽栏渲染 `\storybyline` |
| 3 | `linotype.cls` | `\asidestory` 改 3 参 {标题}{署名}{正文}；新增 `\storybyline` 小字署名宏（74-76% 字号，栏窄紧凑） |
| 4 | 验证 | 重生成晚刊：主条/副条/简讯全带归属；autofit 收敛 columns=3/10.61pt；fill P1 98% / P2 104% / P3 100% / P4 100%；demand 无需求；pdfcheck 4/4；视觉验收双页 PASS；imposer 58/58 + linotype **28/28**（新增 test_story_byline：BYLINE-B 解析→渲染→编译全链） |

**要点**：`\byline` 渲染为全大写（字体特征），PDF 提取文本需大小写不敏感匹配；简讯归属在 PDF 中跨行连字符断开（FER-GUSON）是提取噪声，渲染正常。副条署名新增后 P1 填充 95.4%→98%（署名行增加版头高度）。

### 08-07 第十一轮（续）：主栏补白 + 垃圾过滤 + 视觉协议修复（用户"P1 左下角有空间为什么没补"）

**用户质疑**：P1 主栏底部空 37-41mm（像素实测），fill 98% 达标但"最深油墨"测量掩盖了列内空白（侧栏 BRIEFS 垫底）。且主栏补的简讯是 VOA 播放器 UI 文案垃圾。

| # | 改动 | 内容 |
|---|---|---|
| 5 | `linotype.cls` | `\mainstory` 改 7 参 {…}{左补白}{右补白} + 新增 `\mainbrief`（栏底小字简讯）；colH 修复——有补白时栏高 = contentH − 版头（正文 + \vss 弹性 + 简讯贴底），切分仍按正文/2（内容平衡）；vtop dp 预留 12pt 防 descender 溢出截断 |
| 6 | `build.py` | 解析 `MAINBRIEFS:` 段 → p['mainbriefs'] → \mainstory 6/7 参 |
| 7 | `build_plates.py` | P1 简讯 2→4（2 主栏 MAINBRIEFS + 2 侧栏 BRIEFS）；主栏补白 fulltext 前 400 字符（summary 只 400 字符截断，更满）；`_is_junk` UI/页脚垃圾过滤（VOA 播放器文案/TASS 页脚/CSIS 栏目页/订阅引导，`\xa0` 归一化），剔除 26 条打印审计 |
| 8 | `pixelcheck.py` + `build.py` | **视觉协议断裂修复**：layout.json sheets 按页分（front=[页1两版] back=[页2两版]，旧版 4 版塞 front）+ PNG 页码映射（out-v-N → front/back）+ analyze 跳过每列首个 ≥min_gap 空白带（版头左对齐右侧留白是正常设计）——此前协议不匹配回退像素启发式，main-aside 版头右侧被误报（实测墨 9.5% 却报空） |
| 9 | 验证 | P1 主栏底部空白 37-41mm → **0.7/0.0mm**；fill P1 98%→**101%**（P2 98/P3 96/P4 96 全达标）；Overfull plate 0 条（简讯填充后自然高 ≤ contentH）；视觉双页 PASS；imposer 58/58 + linotype **30/30**（新增 test_mainbriefs） |

**根因链**：主栏底部空白 = colH 用 `min(正文/2, contentH−版头)`——短正文时 colH=正文/2，\vss 无空间，栏底空；简讯加在 vtop 里被 colH 截断。修复 = 有补白时 colH 放宽到 contentH−版头 + \vss 弹性贴底。垃圾进版 = fetch 层把播放器/页脚/栏目页当文章摘要（VOA 'Embed...clipboard' 8 条、TASS 页脚 6 条、CSIS 部门页 4 条）。

## 六、目录状态

```
~/news/imposer/                    ~/.claude/skills/imposer/ (symlink)
├── SKILL.md  (根, 由 skill/SKILL.md 提供)   ← 编排手册 (agent 面向)
├── README.md / README.zh-CN.md    ← 双语手册
├── LICENSE (MIT)
├── docs/
│   ├── ARCHITECTURE.md            ← 架构决策 + 18 条教训
│   ├── DEVELOPMENT-HISTORY.md     ← 完整开发史 + bug 日志 #1-34（含 Phase 0-10 + 08-06）
│   ├── rsshub-routes/             ← 自定义 RSSHub 路由备份（cnsa/esa + 10 fix + 社区复用，76 文件）
│   └── superpowers/               ← 设计文档 + 实现计划（开发过程产物）
├── skill/
│   ├── SKILL.md                   ← 8 步引导式闭环 + 改写规则（fill_min=0.95）
│   ├── scripts/                   ← sources.json(67源) + 7 脚本（含 fetch_freshrss.py）
│   └── tests/                     ← run_tests.py + 5 测试文件（54 项）
├── SESSION-STATE.md               ← 本文件
└── .superpowers/sdd/              ← SDD 工作区（gitignored）

~/news/rsshub-src/                 ← RSSHub 源码（dev 模式 @1201，自定义路由 cnsa/esa/globaltimes/xinhuaenglish 等 12 个）
~/news/rsshub-dev/start.sh         ← RSSHub 启动脚本（crontab @reboot 自启）
~/news/latex/                      ← linotype 唯一仓库（8cli/linotype，含 --demand + fill_min=0.95 + inbrief 多组）
~/news/daily/2026-08-06/           ← 首期实报（out.pdf + plates + demand.json + fetch_results.json + supply_rewritten.json）

服务（Docker）：
  freshrss  @ :1202  ← RSS 聚合（50 feed，SQLite 1322 篇，af-readability 全文入库，CRON_MIN=0,30）
  卷: freshrss-data  ← 持久化（--restart unless-stopped）

GitHub：
  8cli/linotype  @ 31ba131  main   （排版引擎，需求方，fill_min=0.95，单一仓库 ~/news/latex；BYLINE-B 解析 + \storybyline）
  8cli/imposer   @ 178ade0  master （拼版工，供给方，FreshRSS 查询器 + 66 源 53 走 RSSHub；第十一轮归属增强 + 血泪 #56-59）
  8cli/claude    @ 7829d5d  main   （Claude 全局规则 CLAUDE.md + 配置记录，含调研铁律 6 条）
  博客            https://www.clid.net/2026/08/ai.html（Linotype+Imposer 技术回顾）
```

## 七、未来方向（可选增强）

- ✅ **全文优先供给**（2026-08-05 晚间落地）：`fetch_fulltext()` + `supply.py fulltext_fn`——主条/深度规格（≥250 词）缓存只有短摘要时自动抓全文压缩（摘要兜底），实测 66 词摘要 → 272 词全文。缓存 `fulltext` 字段跨轮复用
- ✅ **P4 放宽**（2026-08-05 晚间落地）：中国科技 + 国际科技突破（核聚变等）——linotype 发 `topic:"tech"`/`min_kind:"tech-media"`，sources.json 加 ITER/Phys.org/TechXplore/Nature/IEEE Spectrum/New Scientist（实测 P4 池 80 条）；`_tech_gate` 正向题材门挡国际金融稿
- ✅ **本机 RSSHub 全量接入**（2026-08-06 早落地）：**源码 dev 模式**（`~/news/rsshub-dev/start.sh`，端口 1201 局域网监听 `*:1201`，crontab @reboot 自启）——dev 模式动态加载 `lib/routes/` 路由。**34 源走 RSSHub**：社区现成 22（OpenAI/Anthropic/NYT/VOA/CSIS/NVIDIA 等）+ **自定义 2**（`/cnsa/news` P3 中国航天官方最大缺源补齐、`/esa/newsroom` ESA 新闻稿带日期）+ **fix 10**（社区路由失效的 tassfix/cfrfix/microsoftfix/githubfix/nasafix/chinadailyfix/scmpfix/naturefix/yahoofix/washingtonpostfix，RSS proxy 带浏览器 UA，全部实测可用）。26 源直抓（GT/Xinhua/CSIS 等无社区路由，或 spacenews/newscientist 反爬 RSSHub 客户端但 Python 直抓可行）。**路由备份**：全部自定义路由在 `docs/rsshub-routes/`（76 文件 + README），仓库自包含。Docker 容器/镜像/卷已全部清除。**教训**：官方 Docker 镜像只带 prod 构建（路由编译进 dist）；可扩展的是源码 dev 模式 / npm 包 registerRoute；社区路由常失效（10 个空）需 fix 路由补位；反爬是客户端特定（RSSHub got 403 vs Python 200）；新增路由目录需重启 dev server
- ✅ **FreshRSS 经济架构**（2026-08-06 落地）：Docker :1202（持久化卷 + CRON_MIN=0,30）聚合 50 RSSHub feed，af-readability（Fivefilters Readability.php）全文入库 SQLite（1322 篇）；`fetch_freshrss.py` 直接查库选文（用户洞察：API 不返回 content，SQLite 直查最可靠）。**08-06 午后根因修复**：全文覆盖 11.3% → **94.8%**（见上"af-readability 根因修复"条目）——P1 军事全文弱、P3 af-readability 失败两个待办**已解决**
- ✅ **直抓源迁入 RSSHub**（2026-08-06 午后落地，用户决策）：66 源 53 走 RSSHub（80%）——6 自定义路由（xinhuaenglish/globaltimes/brookings/rand/iter/isro）+ 4 社区接线 + 保留 13 直抓（SPA/反爬，调研否决写路由——任务 #74 结论）
- ✅ **首期 2026-08-06 实报**（2026-08-06 跑通）：4 版全部成版，autofit 达标 ≥95%，demand.json 无需求（见"二点五"第三轮）
- **P1 军事全文**（✅ 已解决，2026-08-06 午后）：CFR 66/68、CSIS 66/67、Naval News 15/15、Asia Times 112/112——配置格式修复后全量提取成功
- **P3 中国航天新源**：P3 新鲜 china-official 素材仍为零（全被 2017 归档过滤）——需补充活跃中国航天英文源（CNSA 英文站更新慢）
- **topic 信号增强**：综合 RSS 仍会泄漏非科技稿（题材门已兜底主要路径）——可进一步按版块重整 sources.json
- **审料门自动化**：agent 引导式闭环已就位，可进一步自动预审（URL 合法性/题材/时效）减少人工
- **CI 集成**：GitHub Actions 跑 54 项回归（仿 linotype CI）
- **更多主题/版式**：随 linotype 演进

## 八、诚实的话

Imposer 的核心价值——需求-供给闭环——**机制完整、实证可复现、文档诚实**。08-06 五轮把供给从"实时抓取分析"升级为 **FreshRSS 聚合 + 全文入库 + 查库选文** 的经济架构，方向正确且已验证。af-readability 根因修复（全文覆盖 11.3% → 94.8%）、直抓源迁入 RSSHub（53/66 源走聚合）、首期实报跑通、linotype 统一单一仓库、出报质量修复（实体清洗/标题截断/主条控制）、**第五轮 fulltext 选材修复**——机制与质量都已打磨。**填充率已达 95% 目标**（P1 98.7 / P2 100.2 / P3 95.6 / P4 99.85，视觉验收 PASS）——第五轮把"P1 素材池极限 359 词"的旧结论推翻：**素材池长文一直充足（P1 379 条 ≥200 词全文），短板不是源而是选材逻辑看错了字段**。剩余诚实短板：**① P3 95.6% 是 autofit 全局压字号的下限**（P2 溢出 1.4pt 微超所致，P2 收敛可回 99.9%）；**② 素材质量仍受源站活跃度约束**（physorg/techxplore 曾 429 限流；13 源保留直抓）；**③ 简讯补版依赖 supply 改写**（本轮的 Gemini Robotics/GT 大使馆是 agent 按 60-90 词压缩交付）。审料门（agent 引导）是质量兜底。真正的完善需要每日真实产出积累反馈，如同 linotype 的 0 star 起点——社区验证是下一步。**下一重点：每日实报常态化 + 检验 P2 溢出微调（换更短简讯消除 1.4pt 截断）**。
