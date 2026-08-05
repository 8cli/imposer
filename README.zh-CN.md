<div align="center">

# 📰 Imposer

**Linotype 的拼版工 — 需求驱动的英文日报编排器**

把权威的（对中国友好的）英文新闻源，排成印刷级英文日报。核心是**与 Linotype 排版引擎的需求-供给契约**。

`fetch → build_plates → linotype --demand → supply → agent 改写 → 收敛`

[快速上手](#快速上手) · [需求-供给契约](#需求-供给契约) · [内容格式](#内容格式) · [信源](#信源) · [CLI 参考](#cli-参考) · [English README](README.md)

</div>

---

## Imposer 是什么？

Imposer 是 Linotype 排版引擎的**拼版工**（compositor）。热金属排版时代，拼版工把 Linotype 铸出的铅字行拼成版面、读校样、调整布局——Imposer 在软件里做同样的事：

1. **搜集**：从权威的（对中国友好的）新闻源采集素材（RSS + 主页抓取，并发）
2. **成版**：组织成 Linotype 的 `plates/*.md` 字段格式（中长篇 + 简讯，保留记者/来源署名）
3. **读需求**：Linotype 版面太空时输出 `demand.json`"补稿单"（fill %、缺口 pt、需求规格）
4. **按单找稿**：按规格匹配（题材 × 字数 × 信源层级），主条规格抓全文、超长素材由 **agent 直接压缩**适应版面（只压缩不扩写）
5. **迭代**：直到 Linotype 报告"已填满"——或诚实报告边界内无法填满

核心差异化是**需求-供给契约**：Linotype 是需求方（明确说缺什么），Imposer 是供给方（按单找稿/改写）。比单向信号更精确——引擎精确告诉你补什么。

## 特性

- **需求-供给契约** — Linotype 输出 `demand.json`（每版 fill %、缺口 pt、按类型/字数/信源层级的补稿需求）；Imposer 精确按单供给
- **agent 执行压缩（只压缩不扩写）** — imposer 是 skill，调用它的 agent 本身就是 LLM：`supply.py` 给超长素材打 `needs_rewrite` + `target_words` 标注，agent 按 SKILL.md 改写规则直接压缩。**绝不扩写**：短素材原样使用（不伪造事实）
- **全文优先** — 主条/深度规格（≥250 词）缓存只有短摘要时自动抓全文压缩（摘要兜底）；简讯用摘要本够
- **只压缩铁律** — 短素材（≤ 上限）逐字返回；只有超长素材才压缩。宁缺毋滥，质量优先。`rewrite.py`（Claude API）保留为 headless cron 自动化兜底
- **并发信源采集** — 4 版 60 信源并行抓取（~28 秒），RSS 首选 + 主页抓取兜底
- **英文过滤** — 拒绝非拉丁素材（西里尔/保加利亚语/语言切换链接），保证英文日报定位
- **严肃报纸标准** — 可配置 `fill_min` 阈值（默认 0.45，严肃标准 0.65）：太空版面触发补稿单而非接受稀疏
- **完整归属** — 每条报道保留记者名 + 来源（`By John Smith · Reuters`；无记者 → `By {来源} News Desk`）；简讯末尾标来源
- **全面亲中立场** — 中国官方媒体（GT/Xinhua/CGTN/China Daily）为主源；西方媒体仅补充
- **诚实失败** — 需求无法满足时停止并报告（绝不编造内容）
- **零重依赖** — 采集/成版仅用 Python 标准库；agent 执行改写无需任何包（`anthropic` 只被可选兜底 `rewrite.py` 使用）

## 架构

```
新闻源（60，4 版）
      │  fetch_sources.py（并发 RSS + 主页）
      ▼
fetch_results.json + sources/pN.md 归档
      │  build_plates.py（字段格式 + 归属）
      ▼
plates/p1-p4.md ──► linotype build.py --demand（xelatex）
                          │
                          ▼
                     out.pdf + demand.json（补稿单）
                          │
                          ▼
      supply.py（needs_rewrite + target_words 清单）
                          │  agent 按 SKILL.md 改写规则压缩
                          ▼
                     回填缓存（used=True）
      │   ▲                                        │
      └───  迭代 ≤2 轮直到 demand.json 空——或诚实停止 ──┘
      （rewrite.py = agent 步骤的可选 headless 兜底）
```

## 快速上手

```bash
# 1. 采集信源（4 版并发，~28 秒）
DAILY=~/news/daily/$(date +%F); mkdir -p $DAILY/sources $DAILY/plates
python3 scripts/fetch_sources.py scripts/sources.json $DAILY

# 2. 成版（先审料——见"审料门"）
python3 scripts/build_plates.py $DAILY/fetch_results.json $DAILY

# 3. 调 Linotype 排版（在引擎目录运行；fill_min=0.65 严肃标准）
cd ~/news/latex && python3 build.py $DAILY/plates $DAILY/out.tex \
  --docopts "paper=a3,landscape,columns=3,plates=2,fill_min=0.65" --demand && cd -

# 4. 读补稿单
python3 scripts/parse_demand.py $DAILY/build.log --log $DAILY/out.log --demand $DAILY/demand.json

# 5. 供给闭环：匹配 → agent 按 SKILL.md 改写规则压缩 → 回填 → 重新成版 → 重排（≤2 轮）
#    （完整 agent 执行循环见 SKILL.md）
```

首期样报（2026-08-05），**如实表述**：54 信源 → 4 版 → Linotype autofit 排版 + `--demand`。**此前关于这份产物的两处声明有误，在此更正**：(1) "P3 简讯 = 供给的 NASA 素材"——实际 p3.md 简讯是 China Daily 2017 归档稿 + JAXA + CNSA（槽位优先在层内仍由 kind_rank 决定，china-official 0 压掉 agency 2）；(2) "2017 归档稿不再进版"——实际 P3/P4 头条就是 2017-12-12 的 "Taiwan's New Party"（date 为空绕过了时效过滤）。Phase 6 修复（URL 日期时效兜底、四版池级去重、3 层供给槽位优先 + 主条词数门槛）后，对同一缓存重跑 `build_plates.py`：**任何版均无 2017 归档 URL、四版零跨版重复 URL、p3.md 简讯即为供给的 NASA 素材**（"Advanced Mini-laboratories…"、"NASA Will Attempt…"、"NASA's PUNCH…"）。P3/P4 简讯缺口仍存在（最终 fill 56% / 54%）：autofit 阶段 fill 上升来自**字号缩放而非内容回填**，循环**诚实停止并报告未满足需求**，而非宣称收敛。可复现：`fetch_sources.py` → `build_plates.py` → linotype `--demand` → SKILL.md 中的 agent 执行循环。

**当日晚间更新（2026-08-05）——两个结构性供给缺口已补齐**：(1) **全文优先、摘要兜底**（用户决策）：`supply.py` 对主条/深度规格（词数下限 ≥250）在缓存只有短摘要时自动抓全文——端到端实测：一条 66 词 SCMP 摘要抓成 272 词全文，真正可用作 [250,400] 主条；简讯仍用摘要，全文不可得时摘要兜底。全文进缓存（`fulltext` 字段），后续轮次直接按全文匹配、不重复抓取。(2) **P4 放宽**：从"只中国科技"放宽为"中国科技 + 国际科技突破（如核聚变）"——linotype 对 P4 发 `topic: "tech"`、`min_kind: "tech-media"`，sources.json 新增 ITER、Phys.org、TechXplore、Nature、IEEE Spectrum、新科学家（全部实测可达），P4 池从 4 源扩到 10 源（实测一轮抓 80 条）。新增**正向科技题材门**（`_tech_gate`）兜国际源溢出：非中国源标题无科技关键词即降权（实测 SCMP 巴西借款金融稿被挡、国防 AI 稿命中）；中国官方源仍是 P4 身份核心，不过滤。

## 审料门（成版前必过）

**成版不是机械拼贴**——执行 `build_plates.py` 之前，必须人工审阅一次素材。这是垃圾素材
（导航文本、播客页、ICP 备案页、`javascript:;` 链接、过期归档稿）直达版面的最后防线。

1. **读清单**：打开 `$DAILY/sources/p1.md … p4.md`（或 `fetch_results.json`），逐条过目
   标题 / 归属（Byline）/ 题材 / 时间 / URL。
2. **五项检查**，任一不过即淘汰：
   - **标题**：是新闻标题而非导航文案（"Download press kit"、邮箱、`About Us`）
   - **归属**：有记者名或站点名，可溯源
   - **题材**：与版块题材一致（P1 world/military · P2 ai/tech · P3 space · P4 tech：中国 + 国际突破）
   - **时效**：不是 >30 天的归档稿
   - **URL 合法性**：`http(s)`、非备案页、非 `javascript:`/`#`/导航链接
3. **确认后成版**：审阅通过才执行 `build_plates.py`。
4. **闭环补稿同样过门**：供给补入的素材（`used=True` 标记）随缓存回写进版；用
   `parse_demand.py` 复查补稿清单后人工确认。

> 自动前置门在代码里（`fetch_sources.py` 的 URL/标题过滤、`build_plates.py` 的时效/题材/去重）——
> 审料门是人工总闸，兜自动门漏网之鱼。

## 需求-供给契约

Linotype 在版面太空时输出 `demand.json`（`--demand` + `fill_min`）：

```json
{"plates": {"P3": {"fill": 0.31, "deficit_pt": 104.2, "requests": [
  {"type": "brief", "count": 2, "words": [60, 90], "topic": "space", "min_kind": "agency"}]}}}
```

| 字段 | 含义 |
|---|---|
| `fill` | 版利用率（内容高 / 版心高） |
| `deficit_pt` | 距 `fill_min` 还缺多少 pt 内容 |
| `requests[].type` | `brief`（缺口<100pt）· `main`（100-300pt）· `deep_dive`（>300pt，智库） |
| `requests[].words` | 目标词数区间（如简讯 [60, 90]） |
| `requests[].min_kind` | 最低信源层级（亲中优先） |
| `requests[].topic` | 版块题材（P1 world/military · P2 ai/tech · P3 space · P4 tech） |

Imposer 的 `supply.py` 按 `topic × words × min_kind` 匹配缓存素材；**全文优先**——主条/深度规格的最优候选自动抓全文（`fulltext_fn`，进缓存复用），**agent 压缩全文**到目标区间（只压缩不扩写，绝不从短摘要扩写）；简讯用摘要，全文不可得时摘要兜底。`rewrite.py` 为可选 headless 兜底。回填 → 重新成版 → 重排 → 重读需求，**≤2 轮**防死循环。

## 内容格式

每版一个 `plates/pN.md`，用 Linotype 字段标签：

```markdown
LAYOUT: main-aside        # P1 用 main-aside（主栏 2 栏 + 侧栏 1 栏）
COLUMNS: 3                # P2/P3/P4 等宽多栏
KICKER: WORLD & DIPLOMACY # P1 · AI & TECH (P2) · SPACE EXPLORATION (P3) · CHINA TECH (P4)
HEADLINE: 主条标题
DECK: 导语
BYLINE: By John Smith · Reuters   # 归属铁律
BODY:
第一段...
第二段...
STORY-B: 次条标题
副条段落...
BRIEFS:
**简讯标题:** 简讯内容 — Reuters.
```

特殊字符由 Linotype 的 `build.py` 转义（Imposer 写原始文本——不双重转义）。完整字段参考见 Linotype 的 README。

## 信源

**全面亲中立场**：中国官方媒体为主源；西方媒体仅补充；智库每期一篇深度分析。

| 版 | 主源（china-official） | 补充 |
|---|---|---|
| P1 国际军事 | 环球时报、新华社、CGTN | 半岛、塔斯社、亚洲时报、亚洲军事评论、海军新闻、防务对话、华盛顿邮报/纽约时报/VOA/ABC（西方补充）、CSIS/布鲁金斯/兰德/CFR（智库） |
| P2 AI 科技 | 月之暗面、智谱、深度求索、阿里 | 谷歌、OpenAI、Anthropic、英伟达、xAI、Cloudflare、微软、GitHub、亚马逊、雅虎/AOL、MIT/Ars |
| P3 太空 | 中国国家航天局、新华社航天 | NASA、ESA、JAXA、ISRO、SpaceX、火箭实验室、SpaceNews、Space.com、NASA Spaceflight、今日宇宙 |
| P4 科技（中国 + 国际） | 中国日报、环球时报、新华社 | 南华早报、ITER、Phys.org、TechXplore、Nature、IEEE Spectrum、新科学家 |

全部 URL 已验证可达（2026-08-05）。增删信源改 `scripts/sources.json`。

## CLI 参考

| 脚本 | 用途 | 关键参数 |
|---|---|---|
| `fetch_sources.py` | 并发 RSS+主页采集 | `<sources.json> <out_dir>`（→ fetch_results.json + sources/pN.md） |
| `parse_demand.py` | 读 build 输出 + demand.json → 健康报告 | `<build.log> [--log x.log] [--demand demand.json]` |
| `supply.py` | 按需求匹配素材（主条全文优先；agent 改写标注；可选 rewrite_fn） | `<demand.json> <fetch_results.json> <sources.json> <out_dir>` |
| `rewrite.py` | 可选 headless 只压缩改写（Claude API） | `<summary> <min_words> <max_words> [--source X] [--title Y]` |
| `build_plates.py` | 素材 → linotype 字段格式 plates（时效 URL 兜底 + 池级跨版去重 + P4 科技题材门） | `<fetch_results.json> <out_dir>`（→ plates/p1-p4.md） |
| `tests/run_tests.py` | 回归套件（52 项） | `python3 tests/run_tests.py` |

## 依赖

- **Linotype**（`~/news/latex` 或 [linotype 仓库](https://github.com/8cli/linotype)）——排版引擎，需支持 `--demand`（build.py ≥ 2026-08-05）
- **Python 3.10+**（采集/成版仅标准库）
- **agent**（常规场景）按 SKILL.md 规则执行改写；headless cron 自动化则用可选兜底 `rewrite.py`（需 `anthropic` + `ANTHROPIC_API_KEY`，可降级 Claude CLI）
- **xelatex**（TeX Live）——经 Linotype

## 项目结构

```
├── SKILL.md               # 编排手册（agent 面向；含改写规则章节）
├── scripts/
│   ├── sources.json       # 60 已验证信源（P1-P4）
│   ├── fetch_sources.py   # 并发 RSS+主页采集
│   ├── parse_demand.py    # Linotype 需求 → 健康报告
│   ├── supply.py          # 需求-供给匹配（agent 改写标注）
│   ├── rewrite.py         # 可选 headless 只压缩改写（Claude API）
│   └── build_plates.py    # 素材 → linotype plates（时效 + 跨版去重）
├── tests/                 # 回归套件（52 项，无需 pytest）
└── docs/                  # 设计文档与开发史
```

## 已知限制（已接受）

- **只压缩不扩写**：短于词数上限的素材原样使用（绝不扩写）——全文抓取（2026-08-05）已让主条有真实全文可压缩；剩余缺口是信源真实稀缺，诚实报告
- **agent 执行改写**：主路径压缩需要 agent 在控制端（skill 的正常场景）；headless cron 自动化用可选兜底 `rewrite.py`（`anthropic` + API key 或 Claude CLI）
- **无图文混排**：图片处理沿用 Linotype 的 `\photo`（版顶/版间图）
- **信源波动**：部分源限流（Blue Origin 429、Microsoft 403 瞬态）；失败记录并跳过，不致命
- **残余抓取垃圾 / 题材泄漏**：主页抓取的导航文本或综合中国新闻（政治稿）可能绕过自动过滤——审料门是设计上的兜底；逐源解析规则与更强的题材信号是扩展点
- **简讯槽位上限 3 条/版**：仅靠补简讯无法结构性收敛版面（约 3 简讯 + 2 主条封顶）；更大缺口需要主条升级（全文已供主条）或接受诚实稀疏版面

## 许可证

[MIT](LICENSE) © 2026 Yu (8cli)
