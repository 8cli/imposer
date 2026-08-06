# Imposer — Linotype 的拼版工（会话状态交接）

> 保存：2026-08-06 13:10 UTC — 第二轮：67 源信源 + FreshRSS 聚合架构 + Readability 全文 + **af-readability 根因修复（全文覆盖 11.3% → 94.8%）**
> 状态：**FreshRSS 经济架构已验证**（imposer 54/54 + linotype 25/25；双仓库已推送；FreshRSS 入库 1151 篇 + 1091 篇全文（94.8%）+ 查库选文打通；P1 军事全文短板已消除）
> 完整开发史：`docs/DEVELOPMENT-HISTORY.md`（Phase 0-10 + 08-06 三轮）
> 公开仓库：**https://github.com/8cli/imposer**（MIT，master @ 6fc39d7）+ **8cli/linotype**（main @ a9e3468）

## 一、项目定位

**Imposer 是 Linotype 排版引擎的拼版工（compositor）**——需求驱动的英文日报编排器：

- Linotype 是**需求方**：版面缺内容时输出补稿单 `demand.json`（fill % / 缺口 pt / 需求规格）
- Imposer 是**供给方**：按单找稿（topic × words × min_kind）→ 压缩改写 → 补稿 → 重排 → 直到"已填满"

**核心差异化**：需求-供给契约（比单向信号更精确——引擎明确说缺什么）。全面亲中（中国官方媒体为主源）、只压缩不扩写（用户铁律）、诚实失败（不编造）。

## 二、完整能力

### 核心组件（skill/scripts/）

| 组件 | 文件 | 能力 |
|---|---|---|
| 信源配置 | `sources.json` | **67 已验证源**（P1 18 / P2 23 / P3 15 / P4 11）；**41 源走本机 RSSHub**（dev 模式 @1201：社区现成 + 自定义 cnsa/esa + fix 10），26 源直抓 |
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
- FreshRSS Docker :1202（持久化卷 + CRON_MIN=0,30 定时刷新），SQLite，1178 篇入库
- **直接查 SQLite 优于 API**（用户提醒：API 的 toGReader 不返回 content；SQLite entry 表 content 含全文）
- **af-readability 根因修复（2026-08-06 午后，全文覆盖 11.3% → 94.8%）**：早先"af-readability 只对 P2 成功、P3 太空源失败"的归因**错误**——真相是配置格式坑：`ext_af_readability_categories` 必须是 **JSON 字符串**（`'{"2":true,"3":true,"4":true,"5":true}'`），扩展用 `attributeString()` 读，PHP 数组格式读不到 → 配置全空 → 所有文章静默跳过。加上三次容器重建丢了扩展文件 + `extensions_enabled` 空，两层叠加导致 88.7%（1045/1178）入库无全文。修复：重装 Niehztog/freshrss-af-readability v0.4（⭐103，PHP 8.1+/dom/xml/curl/mbstring 已满足，纯客户端无外部依赖）→ config.php 两处配置（enabled + JSON 字符串）→ 清空 entry + 重置 lastUpdate 全量重灌 → **1091/1151 篇全文（94.8%）**，P1 军事（CFR 66/68、CSIS 66/67、Naval News 15/15）与 P3 太空（NASA/ESA/JAXA 全 100%）短板全消。唯一 0 全文：NYT（付费墙，预期）。**教训**：FreshRSS 扩展的 per-feed 配置存 config.php 顶层 `ext_` 键，值格式是 JSON 字符串不是 PHP 数组；容器重建会丢扩展与配置，重建后必须两步都配（详见 fetch_freshrss.py 头注释）
- 四版主条供给验证：P2 Google Research 1296 词、P3 JAXA 1197、P4 Nature 1222；**P1 军事全文弱（CFR 5 词，待补）**

### 08-06 提交（12 个，imposer @ 6fc39d7）
739d9a5 P2+4 → e2d9691 P2+2 → db8f358 P4+1 → 0b3fdda 文档同步 → 15b66bf P1 主条放宽+GT 全文 → e731a80 路由修正 → 287ee94 路由备份 → fb985fb Phase10 文档 → 1f08435 Readability+fill_min+FreshRSS 部署 → 6fc39d7 FreshRSS SQLite 查询器

## 三、验证状态

- ✅ **终审 CLEAN**（opus 终审 → fix wave → 2 轮 re-review → 独立重跑实证全过）
- ✅ 回归：imposer **44/44** + linotype **25/25**
- ✅ E2E 实证（真实缓存重跑）：0 归档 URL（2017 旧闻过滤）、0 跨版重复、供给 NASA 简讯真正进版
- ✅ agent 架构：SKILL.md 8 步引导式闭环 + 改写规则章节，PYEOF 零遗留
- ✅ 文档诚实化：README×2 / HISTORY 声明与产物逐项比对通过（上轮虚假实证教训已纠正）
- ✅ 公开仓库推送：imposer @ 4d6d39a、linotype @ 74d5890（含 --demand + fill_min）
- ✅ 持久化：linotype-repo 从 /tmp 迁到 ~/news/linotype-repo（重启不丢）
- ✅ 首期样报：~/news/daily/2026-08-05/out.pdf（2 页 A3 横版 4 版）

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

~/news/rsshub-src/                 ← RSSHub 源码（dev 模式 @1201，自定义路由 cnsa/esa + fix）
~/news/rsshub-dev/start.sh         ← RSSHub 启动脚本（crontab @reboot 自启）
~/news/linotype-repo/              ← linotype 公开仓库（持久，含 --demand + fill_min=0.95）
~/news/daily/2026-08-05/           ← 首期样报（out.pdf + plates + demand.json + 归档）

服务（Docker）：
  freshrss  @ :1202  ← RSS 聚合（41 feed，SQLite 1178 篇，af-readability 全文入库，CRON_MIN=0,30）
  卷: freshrss-data  ← 持久化（--restart unless-stopped）

GitHub：
  8cli/linotype  @ a9e3468  main   （排版引擎，需求方，fill_min=0.95）
  8cli/imposer   @ 6fc39d7  master （拼版工，供给方，FreshRSS 查询器）
```

## 七、未来方向（可选增强）

- ✅ **全文优先供给**（2026-08-05 晚间落地）：`fetch_fulltext()` + `supply.py fulltext_fn`——主条/深度规格（≥250 词）缓存只有短摘要时自动抓全文压缩（摘要兜底），实测 66 词摘要 → 272 词全文。缓存 `fulltext` 字段跨轮复用
- ✅ **P4 放宽**（2026-08-05 晚间落地）：中国科技 + 国际科技突破（核聚变等）——linotype 发 `topic:"tech"`/`min_kind:"tech-media"`，sources.json 加 ITER/Phys.org/TechXplore/Nature/IEEE Spectrum/New Scientist（实测 P4 池 80 条）；`_tech_gate` 正向题材门挡国际金融稿
- ✅ **本机 RSSHub 全量接入**（2026-08-06 早落地）：**源码 dev 模式**（`~/news/rsshub-dev/start.sh`，端口 1201 局域网监听 `*:1201`，crontab @reboot 自启）——dev 模式动态加载 `lib/routes/` 路由。**34 源走 RSSHub**：社区现成 22（OpenAI/Anthropic/NYT/VOA/CSIS/NVIDIA 等）+ **自定义 2**（`/cnsa/news` P3 中国航天官方最大缺源补齐、`/esa/newsroom` ESA 新闻稿带日期）+ **fix 10**（社区路由失效的 tassfix/cfrfix/microsoftfix/githubfix/nasafix/chinadailyfix/scmpfix/naturefix/yahoofix/washingtonpostfix，RSS proxy 带浏览器 UA，全部实测可用）。26 源直抓（GT/Xinhua/CSIS 等无社区路由，或 spacenews/newscientist 反爬 RSSHub 客户端但 Python 直抓可行）。**路由备份**：全部自定义路由在 `docs/rsshub-routes/`（76 文件 + README），仓库自包含。Docker 容器/镜像/卷已全部清除。**教训**：官方 Docker 镜像只带 prod 构建（路由编译进 dist）；可扩展的是源码 dev 模式 / npm 包 registerRoute；社区路由常失效（10 个空）需 fix 路由补位；反爬是客户端特定（RSSHub got 403 vs Python 200）；新增路由目录需重启 dev server
- ✅ **FreshRSS 经济架构**（2026-08-06 落地）：Docker :1202（持久化卷 + CRON_MIN=0,30）聚合 41 RSSHub feed，af-readability（Fivefilters Readability.php）全文入库 SQLite（1178 篇）；`fetch_freshrss.py` 直接查库选文（用户洞察：API 不返回 content，SQLite 直查最可靠）。**08-06 午后根因修复**：全文覆盖 11.3% → **94.8%**（见上"af-readability 根因修复"条目）——P1 军事全文弱、P3 af-readability 失败两个待办**已解决**，NYT 付费墙 0 全文属预期
- **P1 军事全文**（✅ 已解决，2026-08-06 午后）：CFR 66/68、CSIS 66/67、Naval News 15/15、Asia Times 112/112——配置格式修复后全量提取成功
- **P3 中国航天新源**：P3 新鲜 china-official 素材仍为零（全被 2017 归档过滤）——需补充活跃中国航天英文源（CNSA 英文站更新慢）
- **topic 信号增强**：综合 RSS 仍会泄漏非科技稿（题材门已兜底主要路径）——可进一步按版块重整 sources.json
- **审料门自动化**：agent 引导式闭环已就位，可进一步自动预审（URL 合法性/题材/时效）减少人工
- **CI 集成**：GitHub Actions 跑 54 项回归（仿 linotype CI）
- **更多主题/版式**：随 linotype 演进

## 八、诚实的话

Imposer 的核心价值——需求-供给闭环——**机制完整、实证可复现、文档诚实**。08-06 第二轮把供给从"实时抓取分析"升级为 **FreshRSS 聚合 + 全文入库 + 查库选文** 的经济架构，方向正确且已验证。午后的 af-readability 根因修复（配置格式 JSON 字符串 + 容器重建丢配置两步坑）把全文覆盖从 11.3% 拉到 **94.8%**——早先"P1 军事全文弱、P3 太空源失败"两个待办**已消除**（真实归因：扩展从未生效，而非源站问题）。**诚实短板更新为两条**：**① NYT 付费墙全文 0**（Readability 提取不了，P1 需换源或接受摘要）；**② 素材质量仍受源站活跃度约束**。审料门（agent 引导）是质量兜底。真正的完善需要每日真实产出积累反馈，如同 linotype 的 0 star 起点——社区验证是下一步。**下一重点：首期 2026-08-06 实报跑通（fill_min=0.95 验证填充 ≥95%）**。
