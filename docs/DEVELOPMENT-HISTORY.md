# Imposer Development History

The full build-and-debug journey. Every entry records a **root cause, the fix, and the measurable evidence** — read this before touching the scripts or the demand-supply protocol.

> Timeline: 2026-08-05 (design) → 2026-08-05 (9-task implementation + E2E). All measurements are real.

---

## Phase 0 — Why Imposer (the strategic decision)

Linotype solves typesetting: `plates/*.md` → print-ready PDF with compile-time overflow detection. But "who organizes the source material?" was unanswered — content had to be hand-authored in Linotype's field format. Imposer answers that: it is the **copy desk + compositor** that Linotype's hot-metal predecessor needed.

The user's core request (paraphrased): *"I want Linotype to signal when it needs briefs to fill blank space, and the skill to capture that signal and find stories of the matching spec."* Abstracted into the **demand-supply contract**: Linotype is the demand side (emits order sheets), Imposer is the supply side (fills them). This became the project's soul.

User decisions along the way:
- **Name**: imposer (拼版工) — the hot-metal worker who arranges Linotype-cast lines into pages. Same workshop, same era, perfect pairing.
- **China-friendly**: Chinese official media primary (GT/Xinhua/CGTN/China Daily); Western supplement only; think-tanks one deep-dive per issue.
- **One-key daily**: "做今天的日报" → full auto loop, human reviews output.
- **Serious-newspaper standard**: only normal whitespace allowed; too much blank → add stories/briefs.
- **Compress-only**: allow compressing long stories, never expand (quality + layout control).

## Phase 1 — The 9-task build

| Task | Deliverable | Notes |
|---|---|---|
| 1 | `sources.json` — 55+ verified sources | all URLs live-tested (VOA trailing slash fixed) |
| 2 | `fetch_sources.py` — concurrent RSS+page | serial >2min → concurrent 28s |
| 3 | linotype `--demand` + `fill_min` | cross-repo protocol, backward compatible (25/25) |
| 4 | `parse_demand.py` — health report + order sheets | parses build stdout + demand.json |
| 5 | `supply.py` — demand-supply matching | rewrite fallback added later |
| 6 | `build_plates.py` — field-format composition | raw text, no pre-escaping |
| 7 | `SKILL.md` — orchestration manual | demand-supply contract documented |
| 8 | E2E first edition | 6 integration defects fixed (below) |
| 9 | `tests/run_tests.py` — 20-test regression | no pytest needed |

## Phase 2 — E2E integration defects (all fixed)

1. **build_plates wrote wrong dir** — wrote `$DAILY/pN.md`, Linotype consumes `plates/`. Fix: write `plates/` subdir.
2. **fetch_page had no summaries** — China-official page sources yielded 0-word items (unusable). Fix: fetch first-paragraph summary (top 2 candidates only).
3. **Serial fetch > 2min timeout** — 55 sources × slow sites. Fix: ThreadPoolExecutor + as_completed + 8s timeout → **28s**.
4. **Non-English material entered plates** — TASS returned Bulgarian (Cyrillic). Fix: English-only filter (Latin ratio ≥ 0.85) in build_plates + supply.
5. **fill_min keyval error** — `fill_min=0.65` passed to linotype.cls which doesn't define it → "fill_min undefined" + empty fills → false convergence. Fix: filter fill_min from cls docopts.
6. **Visual blank bands** — fill 48-65% passed autofit (FILL_MIN 0.45) but 120mm blank bands failed visual acceptance. Fix: user decision — serious standard fill_min=0.65, demand triggers earlier.

## Phase 3 — The LLM rewrite engine (user directive)

User: *"imposer 需要具备信息搜集和改写能力...只允许在版面紧张情况下压缩概括但不允许扩写...搜集报道和压缩改写报道直到 Linotype 返回已填满。"*

`rewrite.py` implemented with the **compress-only iron rule**:
- Input ≤ max_words → verbatim (never expand).
- Over-length → Claude API compress to `[min, max]`.
- Hard cap: output truncated to max_words if LLM exceeds.
- Attribution preserved through compression.

Debugging journey:
1. `anthropic` not installed → PEP 668 blocked → `--break-system-packages`.
2. API returned `'str' object has no attribute 'content'` → local proxy returns **SSE strings**, not SDK objects → SSE parse (`data: {json}` → `content_block_delta`/`text_delta`).
3. Claude CLI `--print` session-contaminated (printed system prompt as output) → `--verbose --output-format stream-json` + SSE parse.
4. `"word " * N` nonsense input → LLM returns empty → extractive fallback (first N words).

Measured: 373-word input → 82-word compression, valid English, attribution preserved, no filler. Short input (≤ cap) returned verbatim. **Compress-only verified.**

## Phase 4 — The closed loop (verified end-to-end)

```
real sources (54, concurrent 28s) → build_plates 4 plates → linotype --demand fill_min=0.65
  → demand.json: P1 brief, P3 2×brief, P4 main+brief
  → supply match → rewrite compress → backfill → rebuild → re-typeset
  → demand shrinks: P1 filled (>65%), P4 main-story deficit eliminated (48→55%)
```

The remaining P3/P4 brief deficits persist because cache material is exhausted — the honest stop per the ≤2-round contract. Directed full-article fetching (fetch_fn) is the documented extension point.

## Bug log (chronological)

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | build_plates output missing from plates/ | wrote out_dir/pN.md not out_dir/plates/ | write plates/ subdir |
| 2 | China-official sources 0-word | fetch_page no summary | first-paragraph fetch (top 2) |
| 3 | fetch >2min timeout | 55 sources serial + slow sites | concurrent as_completed + 8s |
| 4 | Bulgarian text in P1 headline | TASS/EurAsian non-English material | English-only filter (0.85 ratio) |
| 5 | fill_min keyval undefined | fill_min reached linotype.cls | filter from cls docopts |
| 6 | 120mm blank band yet "converged" | FILL_MIN 0.45 vs visual acceptance | fill_min configurable, serious 0.65 |
| 7 | supply matched "Bulgarian Български" | language-switcher link passed filter | English filter in match_cache |
| 8 | supply 0 matches | summaries ~70 words vs main 250-400 | rewrite fallback (needs_rewrite) |
| 9 | rewrite LLM output empty | nonsense input "word word" | extractive fallback |
| 10 | rewrite keyerror `item["request"]` | fallback item lacks request before attach | use loop `req` |
| 11 | rewrite output 151 words (over cap) | match_cache +100 upper slack let 151 pass | removed slack → rewrite path |
| 12 | API returns str not Message | local proxy SSE stream | SSE parse in _call_anthropic |
| 13 | CLI --print contaminated | session context leaked | stream-json + verbose |

## What survives

- **20 regression tests** → `tests/run_tests.py` (fetch 6 / demand 3 / supply 3 / build_plates 8)
- **Demand-supply protocol** → linotype `--demand` (25/25 regression intact) + `demand.json` schema
- **Compress-only iron rule** → `rewrite.py` (user decision, mechanically enforced)
- **Every measurement above is reproducible** — run the scripts on the examples or the E2E daily.

The design debt we chose to accept: compress-only (no expansion means underfilled plates may persist), rewrite needs LLM, and directed full-article fetching is the natural next step.
