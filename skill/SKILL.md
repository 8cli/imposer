---
name: imposer
description: Use when the user wants to produce a daily English newspaper (英文日报/报纸/做今天的日报/出报). Organizes source material from authoritative China-friendly news sources into presswire plates, runs presswire typesetting, reads its demand signals (demand.json requests for briefs/deep-dives to fill blank space) and supplies matching stories by topic/word-count/source-rank. Companion to the presswire typesetting skill.
---

# imposer — 英文日报编排

## 定位

imposer 是 presswire 的**拼版工**：组织 4 版素材 → 调用 presswire 排版 → **接收 presswire 的补稿单（demand.json）→ 按单找稿交稿**（题材×篇幅×信源层级匹配）→ 产出 PDF + 信源归档 + 工作日志。

**核心关系（需求-供给契约）**：presswire 是需求方（版面缺内容时下补稿单），imposer 是供给方（按单找稿）。比单向信号更精确、更良性。

> 2026-08-08 切换：默认引擎从 linotype（LaTeX）→ **presswire（Typst）**。D2 红线保证契约
> （plates 格式 / demand.json / layout.json / CLI 参数面）字节兼容，imposer 的
> build_plates/supply/rewrite 零改动；仅引擎调用段 + parse_demand 改为 presswire 分支
> （linotype 分支保留向后兼容）。切换收益：autofit 单次编译收敛（3-16 次 xelatex → 1 次
> typst）、fill 从日志正则 → eval JSON 结构化、严重溢出 panic 硬门禁。

**铁律**：材料组织与版面纪律耦合——写出的 plates 第一轮就接近版面，反馈环只是微调（≤2 轮）。

## 快速流程（一键日报）

```bash
# 1. 建当日工作区
DAILY=~/news/daily/$(date +%F); mkdir -p $DAILY/sources $DAILY/plates
# 2. 抓取信源（2026-08-06 经济架构主路径: 查 FreshRSS 库而非实时抓取）
#    默认 fetch_freshrss.py（直查 SQLite 全文）；直抓源（13 个 SPA/反爬）
#    需 fetch_sources.py 补抓时再跑
python3 ~/.claude/skills/imposer/scripts/fetch_freshrss.py \
  ~/.claude/skills/imposer/scripts/sources.json $DAILY > $DAILY/fetch.log
# 3. 组织成版（需人工审查素材后执行——见"审料门"）
#    出版日期（2026-08-07）: P1 版顶 \dateline 日期线（期次识别）。
#    缺省 = 本地今天（与 $DAILY=$(date +%F) 一致）；重建旧刊显式传 --date "Aug 6, 2026"
python3 ~/.claude/skills/imposer/scripts/build_plates.py $DAILY/fetch_results.json $DAILY
# 4. 调 presswire 排版（render_presswire 一键: 编译+fills+demand+健康报告）
#    内存通讯（2026-08-08）: 自动走 typstpy 进程内编译（.venv312）——无 typst
#    CLI subprocess、无日志正则；build.json 即结构化报告（含 article_mismatch
#    信号，imposer 按"选/改文章"响应；--demand 照写 demand.json 审计）
#    注意: --root ~/news 让 output（$DAILY/out.pdf）与模板资产（presswire_typst/）
#    同处 Typst 沙箱内（$DAILY 在 ~/news/daily/ 下，模板在 ~/news/presswire/ 下）
#    fill_min=0.95 严肃报纸标准：空白多则发补稿单（默认 0.45 宽松）
python3 ~/.claude/skills/imposer/scripts/render_presswire.py $DAILY/plates $DAILY/out.pdf \
  --root ~/news --docopts "paper=a3,landscape,columns=3,plates=2,fill_min=0.95" \
  --demand > $DAILY/build.json 2>&1
# 5. 读需求 → 版面健康报告 + 补稿单（build.json 即报告；parse_demand 兼容旧流程可省略）
cat $DAILY/build.json
# 6. 需求-供给闭环（agent 执行改写——主路径）→ 见下节"闭环循环（agent 执行）"
#    直到 presswire 返回"已填满"（demand.json 无需求或 ≤2 轮上限）。
```

## 闭环循环（agent 执行改写——主路径）

**架构决策（2026-08-05）**：imposer 是 skill，skill 由 agent 调用——**agent 本身就是 LLM**，
改写应由 agent 直接执行，而不是脚本再调一次 Claude API（那条路踩了 anthropic 包/PEP 668/
SSE 解析/CLI 污染一堆坑，且是绕路）。`supply.py` 输出 `needs_rewrite` 素材清单（含
`target_words`），agent 按下述改写规则直接压缩回填。`rewrite.py` 降级为可选兜底
（headless cron 自动化备胎），主路径不再依赖它的 API 调用。

每轮执行（≤2 轮防死循环；每轮必须重新成版，否则 plates 不更新、demand.json 永不变化、
循环空转——终审 C-1a；supply 输出带 `used=True`，回写缓存即持久化，第 2 轮不会重复
供给同一批素材——终审 C-1b）：

1. **读需求**：`cat $DAILY/build.json`（或 demand.json）——build.json 即
   完整报告（converged/article_mismatch/requests_by_plate）。无 `plates` 需求
   → 已填满，停止并报 ✅。
2. **按单找稿**：
   ```bash
   python3 ~/.claude/skills/imposer/scripts/supply.py \
     $DAILY/demand.json $DAILY/fetch_results.json \
     ~/.claude/skills/imposer/scripts/sources.json $DAILY
   ```
   输出 `{plate: [素材]}`。带 `"needs_rewrite": true` + `"target_words": [lo, hi]`
   的素材 = **需 agent 压缩改写的清单**（`used: true` 已标记）。主条/深度规格
   （target 下限 ≥250 词）的素材可能带 `"fulltext"` 字段——supply 已自动抓取全文
   （全文优先铁律，见下）；改写用全文，摘要是全文不可得时的兜底。
3. **agent 逐条压缩**（按下方"改写规则"章节执行）：对每条 `needs_rewrite` 素材，
   **优先用其 `fulltext`（全文）压缩**到 `target_words` 硬上限内，无 `fulltext` 才用
   `summary`——**只压缩不扩写，绝不从短摘要扩写**；改写后替换该条的 summary 字段
   （保留 author/source/url/date/used/request 原样）。
4. **回填缓存**：将供给结果（含改写后的 summary）追加回 `$DAILY/fetch_results.json`
   对应版块数组（携带 used=True，防第 2 轮重复供给）。
5. **重新成版**：`python3 ~/.claude/skills/imposer/scripts/build_plates.py $DAILY/fetch_results.json $DAILY`
   （关键步骤：先重新成版，plates 才反映补稿）。
6. **重排 + 重读需求**（render_presswire 一步，内存通讯）：
   ```bash
   python3 ~/.claude/skills/imposer/scripts/render_presswire.py $DAILY/plates $DAILY/out.pdf \
     --root ~/news --docopts "paper=a3,landscape,columns=3,plates=2,fill_min=0.95" \
     --demand > $DAILY/build.json 2>&1
   ```
   build.json 即新报告（含 requests_by_plate + article_mismatch 信号），
   不再需要 parse_demand 步骤（保留兼容旧流程）。
7. demand.json 仍有需求 → 回到第 1 步（≤2 轮）。
8. **诚实报告**（终审 C-1d）：2 轮后仍未满足 → 列出每版 fill 与未满足请求
   （count/规格/词数），不静默退出；全文已自动尝试（fulltext_fn 优先、摘要兜底），
   仍不足 → 提示人工接受版面或补充信源。

## 改写规则（agent 执行时遵循——替代 rewrite.py 的 API 调用）

压缩改写是**硬纪律**，逐条执行：

0. **全文优先（用户决策 2026-08-05）**：素材带 `fulltext` 字段时，从全文压缩——
   全文比摘要更能满足排版需求（250-600 词主条/深度规格），摘要是全文不可得时
   （抓取失败/文章本就短）的兜底。`supply.py` 对主条/深度规格自动抓全文并附
   `fulltext`；缓存富集后跨轮直接按全文匹配，不重复抓取。
1. **只压缩不扩写（铁律）**：素材（全文或摘要）词数 ≤ 需求上限（`target_words[1]`）
   时**原样返回**，不调用任何 LLM；只有超长素材才压缩。**绝不新增事实、不编造来源**。
2. **硬词数上限**：改写后词数 ≤ `target_words[1]`（硬上限，宁可少不可超）；
   尽量落在 `[target_words[0], target_words[1]]` 区间内。
3. **保留归属**：保留记者名（Byline）、站点名、以及 "according to Xinhua"、
   "Reuters reported" 类归属短语——压缩可以删细节，不能丢出处。
4. **保导语**：保留首段核心信息（who/what/where/when）。
5. **输出纯文本**：只输出压缩后的报道文本，不加前言、不加引号、不改字段结构。
6. **回填**：改写结果写回该条素材的 `summary` 字段。

**兜底（可选，非主路径）**：`rewrite.py` 保留用于 headless cron 自动化（无 agent
场景），铁律与上述一致，机械强制（词数硬钳制）：
```bash
python3 ~/.claude/skills/imposer/scripts/rewrite.py "<summary>" <min_words> <max_words> --source X --title Y
```

## 审料门（成版前必过，终审 I-5）

**成版不是机械拼贴——抓取素材进版面之前，必须人工审阅一次。** 这是垃圾素材
（导航文本、播客页、ICP 备案页、`javascript:;` 链接、过期归档稿）直达版面的最后防线。

1. **读清单**：打开 `$DAILY/sources/p1.md … p4.md`（或直接看 `fetch_results.json`），
   逐条过目每条素材的标题 / 归属（Byline）/ 题材 / 时间 / URL。
2. **五项检查**，任一不过即淘汰：
   - **标题**：是新闻标题而非导航文案（"Download press kit"、邮箱、`About Us`）
   - **归属**：有记者名或站点名，可溯源
   - **题材**：与版块题材一致（P1 world/military · P2 ai/tech · P3 space · P4 china-tech）；
     纪念稿/体育稿等明显不相关者淘汰（build_plates 已自动降权并打印记录，人工复核）
   - **时效**：date 字段明显过期（>30 天）的归档稿淘汰（build_plates 已自动排除）
   - **URL 合法性**：`http(s)`、非备案页、非 `javascript:` / `#` / 导航链接
     （fetch_sources 已前置过滤，人工抽查）
3. **确认后成版**：审阅通过才执行 `build_plates.py`。
4. **闭环补稿同样过门**：供给补入的素材（`used=True` 标记）随缓存回写进版，若对
   供给结果有疑问，重跑 `parse_demand.py` 查看补稿清单后人工确认。

> 说明：`fetch_sources.py` 的 URL 合法性过滤、`build_plates.py` 的题材降权/时效过滤
> 是**自动前置门**；审料门是**人工总闸**——自动门挡常规垃圾，人工门挡漏网之鱼。

## 需求-供给契约（灵魂）

presswire 在 `--demand` 模式下输出 `demand.json`——每版缺什么（结构与 linotype 字节兼容，D2 红线）：

```json
{"plates": {"P3": {"fill": 0.31, "deficit_pt": 84.2, "requests": [
  {"type": "brief", "count": 2, "words": [60, 90], "topic": "space", "min_kind": "agency"}]}}}
```

imposer 的 supply 按规格找稿：`topic`（版块题材）× `words`（字数区间）× `min_kind`（最低信源层级，亲中优先）→ 缓存匹配 → 不足则**近似匹配 + agent 改写**（返回最接近素材 + `needs_rewrite` + `target_words`，**agent 按上方"改写规则"章节直接压缩**到目标词数区间）→ 生成补稿 → 重排。改写原则（铁律）：只压缩不扩写、忠实原文不编造事实、硬词数上限、保留记者名与站点归属。`rewrite.py`（Claude API 压缩）仅作 headless 自动化兜底。

**规格映射**：P1 world/military · P2 ai/tech · P3 space · P4 china-tech；需求类型按缺口：`<100pt → briefs`、`100-300pt → 1 main + briefs`、`>300pt → deep_dive + briefs`。

## 其余信号响应

| presswire 信号 | imposer 响应 |
|---|---|
| 内容超出版心（framefit panic，字号固定） | **选合适长度文章**（FreshRSS 原文直用）→ 无合适 → **改写缩小**（不缩字号） |
| 严重溢出 panic（fill > 1.05） | 裁段（末段起）→ 换次条 → 减简讯 |
| 编译 ✅ 成功 | 进入 QA（pdfcheck + --visual） |
| --visual ❌ 空白带 | 调配比（增/减内容）或接受 |

> **字号铁律（2026-08-08 用户决策）**：正文字号固定适宜阅读（100%，不缩放）。
> 内容放不下 → 由 imposer 层解决：优先从 FreshRSS 选**合适长度的文章**（原文直用，
> 不加工）；无合适长度的文章时 → **改写压缩**到版心容量（agent 按改写规则执行）。
> **绝不**用缩小字号来适配——字号适宜阅读是硬约束。
>
> 注: presswire autofit 模式 plate-frame 的 fill 报告失真（架构决策——收敛由
> framefit 渲染时保证，measure 时机无高度约束）→ parse_demand 的 fills 仅参考，
> **发单判定以 demand.json 为准**（权威信号，二者边界一致）。

**反馈环**：补稿（agent 改写）→ **重新成版（build_plates）** → 重排 → 重读需求，**最多 2 轮**。仍不达标 → 停止 + 诚实报告（列出未满足需求，不静默退出）。

## 信源与归属

**RSSHub（源码 dev 模式，2026-08-05 用户决策）**：本机 `~/news/rsshub-dev/start.sh`
持久化运行（端口 1201，crontab @reboot 开机自启）。源码 `~/news/rsshub-src` 以
**dev 模式**（NODE_ENV=dev）运行——**动态加载 `lib/routes/` 下的路由，加路由文件即
生效（tsx watch 自动重启），无需重建镜像**。内置路由（OpenAI/Anthropic 等）+ **自定义
路由**（`cnsa/news`、`esa/newsroom`，imposer 自写）都在 1201 一个实例上。

- **加自定义路由**：写 `~/news/rsshub-src/lib/routes/<name>/<route>.ts` + `namespace.ts`
  （参照 cnsa/esa 现有写法）→ tsx watch 自动重载 → 无需重启
- **接入 imposer**：sources.json 加 `"rsshub": "/<name>/<route>"` 字段，采集优先走路由，
  返回空自动回退原主页直抓（补强不是单点）
- **已接入**：CNSA（P3 中国航天官方）、ESA（P3 欧洲航天）、OpenAI/Anthropic（P2）

- 信源清单：`scripts/sources.json`（P1 国际军事 / P2 AI 科技 / P3 太空 / P4 中国科技，全面亲中）
- 归属铁律（2026-08-07 用户要求补日期）：`By {记者} · {站点} · {日期}`；无记者 `By {站点} News Desk · {日期}`；
  日期取素材 date（epoch/ISO/RFC2822）→ 英文格式 `Aug 6, 2026`，解析失败省略不伪造；多作者 `;` 分隔清洗为 `, ` 连接；
  副条 STORY-B 独立署名 `BYLINE-B:`（presswire 渲染为 storybyline 原子）；
  简讯末尾标 `— {站点}, {日期}.`（有记者再加 `{记者} et al.,` 前缀，多作者压缩）；付费墙退 RSS 摘要标注 `[付费墙]`
- 主栏补白（2026-08-07 用户要求：P1 主栏底部有空间就补）：P1 简讯拆 2 条 `MAINBRIEFS:`（主栏底部补白，
  正文不足栏高时 \vss 弹性贴底，填满主栏底部）+ 2 条侧栏 `BRIEFS:`；主栏补白摘要用 fulltext 前 400 字符（更满）
- UI/页脚垃圾过滤（2026-08-07 用户发现 VOA 播放器文案进版）：build_plates 选材前剔除 `_is_junk` 命中素材
  （播放器复制提示/订阅引导/页脚条款/栏目页模板，如 VOA 'Embed...clipboard'、TASS 页脚、CSIS 部门页），
  剔除记录打印供审料门审计（08-06 晚刊实测 26 条）
- 智库深度文章：每期至少一篇（CSIS/Brookings/RAND/CFR 等，有更新才放）
- 亲中编辑原则：涉华报道以中国官方口径为准；西方主流仅补充

## 版面结构（每版）

- P1 国际军事：main-aside（主条 2 栏 + 侧栏）+ 智库深度；**版顶出版日期线**（DATE 字段 → presswire dateline 原子，2026-08-07）
- P2 AI 科技 / P3 太空 / P4 中国科技：等宽多栏
- 每版：中长篇主条 ×2 + 简讯 ×3-5

## 交付物

```
$DAILY/
├── sources/p1-p4.md   # 信源归档（URL/记者/站点/摘要）
├── plates/p1-p4.md    # presswire 消费
├── out.pdf + out.typ + layout.json + demand.json
└── fetch.log + build.json + imposer.log  # 工作日志（build.json 即排版报告）
```

## 诚实原则

- 摘录尽量原文，不编造；付费墙标注；亲中立场透明（编辑决策）
- 失败诚实报告：信源抓取失败（跳过+记录）、版面放不下（报告历史最佳）、反馈环超限（停止）
