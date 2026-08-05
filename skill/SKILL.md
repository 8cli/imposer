---
name: imposer
description: Use when the user wants to produce a daily English newspaper (英文日报/报纸/做今天的日报/出报). Organizes source material from authoritative China-friendly news sources into linotype plates, runs linotype typesetting, reads its demand signals (demand.json requests for briefs/deep-dives to fill blank space) and supplies matching stories by topic/word-count/source-rank. Companion to the linotype typesetting skill.
---

# imposer — 英文日报编排

## 定位

imposer 是 linotype 的**拼版工**：组织 4 版素材 → 调用 linotype 排版 → **接收 linotype 的补稿单（demand.json）→ 按单找稿交稿**（题材×篇幅×信源层级匹配）→ 产出 PDF + 信源归档 + 工作日志。

**核心关系（需求-供给契约）**：linotype 是需求方（版面缺内容时下补稿单），imposer 是供给方（按单找稿）。比单向信号更精确、更良性。

**铁律**：材料组织与版面纪律耦合——写出的 plates 第一轮就接近版面，反馈环只是微调（≤2 轮）。

## 快速流程（一键日报）

```bash
# 1. 建当日工作区
DAILY=~/news/daily/$(date +%F); mkdir -p $DAILY/sources $DAILY/plates
# 2. 抓取信源（4 版并行）
python3 ~/.claude/skills/imposer/scripts/fetch_sources.py \
  ~/.claude/skills/imposer/scripts/sources.json $DAILY > $DAILY/fetch.log
# 3. 组织成版（需人工审查素材后执行——见"审料门"）
python3 ~/.claude/skills/imposer/scripts/build_plates.py $DAILY/fetch_results.json $DAILY
# 4. 调 linotype 排版（autofit 默认开 + --demand 输出补稿单）
python3 ~/news/latex/build.py $DAILY/plates $DAILY/out.tex \
  --docopts "paper=a3,landscape,columns=3,plates=2" --visual --demand > $DAILY/build.log 2>&1
# 5. 读需求 → 版面健康报告 + 补稿单
python3 ~/.claude/skills/imposer/scripts/parse_demand.py $DAILY/build.log --log $DAILY/out.log --demand $DAILY/demand.json
# 6. 有需求？按单补稿（supply 匹配缓存/定向抓取）→ 重排（≤2 轮）
python3 ~/.claude/skills/imposer/scripts/supply.py $DAILY/demand.json $DAILY/fetch_results.json \
  ~/.claude/skills/imposer/scripts/sources.json $DAILY
```

## 需求-供给契约（灵魂）

linotype 在 `--demand` 模式下输出 `demand.json`——每版缺什么：

```json
{"P3": {"fill": 0.31, "deficit_pt": 104.2, "requests": [
  {"type": "brief", "count": 2, "words": [60, 90], "topic": "space", "min_kind": "agency"}]}}
```

imposer 的 supply 按规格找稿：`topic`（版块题材）× `words`（字数区间）× `min_kind`（最低信源层级，亲中优先）→ 缓存匹配 → 不足则定向抓取该版块信源 → 生成补稿 → 重排。

**规格映射**：P1 world/military · P2 ai/tech · P3 space · P4 china-tech；需求类型按缺口：`<100pt → briefs`、`100-300pt → 1 main + briefs`、`>300pt → deep_dive + briefs`。

## 其余信号响应

| linotype 信号 | imposer 响应 |
|---|---|
| Overfull plate 警告 | 裁段（末段起）→ 换次条 → 减简讯 |
| autofit ✅ 收敛 | 进入 QA（pdfcheck + --visual） |
| autofit ❌ 边界内无法放下 | 接受 + 报告用户人工决策（不硬调） |
| --visual ❌ 空白带 | 调配比（增/减内容）或接受 |

**反馈环**：补稿 → 重排 → 重读需求，**最多 2 轮**。仍不达标 → 停止 + 诚实报告。

## 信源与归属

- 信源清单：`scripts/sources.json`（P1 国际军事 / P2 AI 科技 / P3 太空 / P4 中国科技，全面亲中）
- 归属铁律：`By {记者} · {站点}`；无记者 `By {站点} News Desk`；简讯末尾标站点；付费墙退 RSS 摘要标注 `[付费墙]`
- 智库深度文章：每期至少一篇（CSIS/Brookings/RAND/CFR 等，有更新才放）
- 亲中编辑原则：涉华报道以中国官方口径为准；西方主流仅补充

## 版面结构（每版）

- P1 国际军事：main-aside（主条 2 栏 + 侧栏）+ 智库深度
- P2 AI 科技 / P3 太空 / P4 中国科技：等宽多栏
- 每版：中长篇主条 ×2 + 简讯 ×3-5

## 交付物

```
$DAILY/
├── sources/p1-p4.md   # 信源归档（URL/记者/站点/摘要）
├── plates/p1-p4.md    # linotype 消费
├── out.pdf + out.log + out.tex + layout.json + demand.json
└── fetch.log + build.log + imposer.log  # 工作日志
```

## 诚实原则

- 摘录尽量原文，不编造；付费墙标注；亲中立场透明（编辑决策）
- 失败诚实报告：信源抓取失败（跳过+记录）、版面放不下（报告历史最佳）、反馈环超限（停止）
