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
#    注意: linotype build.py 需在引擎目录运行（cwd 须含 linotype.cls）
#    fill_min=0.65 严肃报纸标准：空白多则发补稿单（默认 0.45 宽松）
cd ~/news/latex && python3 build.py $DAILY/plates $DAILY/out.tex \
  --docopts "paper=a3,landscape,columns=3,plates=2,fill_min=0.65" --visual --demand > $DAILY/build.log 2>&1 && cd -
# 5. 读需求 → 版面健康报告 + 补稿单
python3 ~/.claude/skills/imposer/scripts/parse_demand.py $DAILY/build.log --log $DAILY/out.log --demand $DAILY/demand.json
# 6. 需求-供给闭环：按单补稿 → LLM 压缩改写（只压缩不扩写）→ 回填 → 重新成版 → 重排
#    直到 linotype 返回"已填满"（demand.json 无需求或 ≤2 轮上限）。
#    铁律：每轮 supply 后必须重跑 build_plates.py 重新成版——否则 plates 不更新、
#    demand.json 永不变化，循环空转（终审 C-1a）。supply 输出带 used=True 标记，
#    回写缓存即持久化，第 2 轮不会重复供给同一批素材（终审 C-1b）。
python3 - <<'PYEOF'
import json, subprocess
from pathlib import Path
import sys
SKILL = Path.home() / ".claude/skills/imposer/scripts"
DAILY = Path.home() / "news/daily" / subprocess.run(["date", "+%F"], capture_output=True, text=True).stdout.strip()
sys.path.insert(0, str(SKILL))
import supply, rewrite

def build_plates():
    subprocess.run(["python3", str(SKILL / "build_plates.py"), str(DAILY / "fetch_results.json"), str(DAILY)],
                   capture_output=True)

def typeset():
    r = subprocess.run(["python3", "build.py", str(DAILY / "plates"), str(DAILY / "out.tex"),
                        "--docopts", "paper=a3,landscape,columns=3,plates=2,fill_min=0.65", "--demand"],
                       cwd=str(Path.home() / "news/latex"), capture_output=True)
    (DAILY / "build.log").write_bytes(r.stdout + r.stderr)  # 供 parse_demand.py 重读
    return r.returncode

unmet = None  # 未满足需求（诚实报告的载体）
for round_no in range(1, 3):  # ≤2 轮防死循环
    demand = json.load(open(DAILY / "demand.json")) if (DAILY / "demand.json").exists() else {"plates": {}}
    if not demand.get("plates"):
        print(f"✅ 第 {round_no-1} 轮后已填满（无需求）"); break
    cache = json.load(open(DAILY / "fetch_results.json"))
    sources = json.load(open(str(SKILL / "sources.json")))
    supplied = supply.supply_requests(demand, cache, sources, DAILY, rewrite_fn=rewrite.rewrite)
    if not any(supplied.values()):
        print(f"⚠️ 第 {round_no} 轮无供给（素材用尽/题材不匹配），停止并报告"); unmet = demand.get("plates", {}); break
    for plate, items in supplied.items():
        for i in items: cache[plate].append(i)   # 携带 used=True 回写，第 2 轮不再重复供给
    with open(DAILY / "fetch_results.json", "w") as f: json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"🔄 第 {round_no} 轮补稿 {sum(len(v) for v in supplied.values())} 条 → 重新成版 → 重排")
    build_plates()                                # 关键：先重新成版，plates 才反映补稿
    if typeset() != 0:
        print(f"  ⚠️ 重排失败（见 {DAILY}/build.log），停止并报告"); unmet = demand.get("plates", {}); break
else:
    # 2 轮跑完仍未收敛 → 诚实报告，不静默退出（终审 C-1d）
    unmet = json.load(open(DAILY / "demand.json")).get("plates", {})
if unmet:
    print("⚠️ 停止并报告：以下需求在 ≤2 轮内未满足（不硬调，宁缺勿滥）")
    for plate, info in unmet.items():
        reqs = info.get("requests", [])
        fill = info.get("fill")
        fill_s = f"{fill*100:.0f}%" if isinstance(fill, (int, float)) else "?"
        total = sum(r.get("count", 1) for r in reqs)
        print(f"  {plate}: fill {fill_s}，{total} 条未满足（{len(reqs)} 项需求）— {reqs}")
    print("  可定向抓取全文（supply fetch_fn）后重试，或人工接受当前版面")
PYEOF

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

linotype 在 `--demand` 模式下输出 `demand.json`——每版缺什么：

```json
{"plates": {"P3": {"fill": 0.31, "deficit_pt": 84.2, "requests": [
  {"type": "brief", "count": 2, "words": [60, 90], "topic": "space", "min_kind": "agency"}]}}}
```

imposer 的 supply 按规格找稿：`topic`（版块题材）× `words`（字数区间）× `min_kind`（最低信源层级，亲中优先）→ 缓存匹配 → 不足则**近似匹配 + AI 改写**（返回最接近素材 + `needs_rewrite` + `target_words`，由编排层 AI 改写压缩到目标词数区间）→ 生成补稿 → 重排。改写原则：忠实原文不编造事实，压缩到目标词数，保留记者名与站点归属。

**规格映射**：P1 world/military · P2 ai/tech · P3 space · P4 china-tech；需求类型按缺口：`<100pt → briefs`、`100-300pt → 1 main + briefs`、`>300pt → deep_dive + briefs`。

## 其余信号响应

| linotype 信号 | imposer 响应 |
|---|---|
| Overfull plate 警告 | 裁段（末段起）→ 换次条 → 减简讯 |
| autofit ✅ 收敛 | 进入 QA（pdfcheck + --visual） |
| autofit ❌ 边界内无法放下 | 接受 + 报告用户人工决策（不硬调） |
| --visual ❌ 空白带 | 调配比（增/减内容）或接受 |

**反馈环**：补稿 → **重新成版（build_plates）** → 重排 → 重读需求，**最多 2 轮**。仍不达标 → 停止 + 诚实报告（列出未满足需求，不静默退出）。

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
