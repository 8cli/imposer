# Imposer Architecture

This document records Imposer's key design decisions and the lessons behind them. It is the reference for anyone extending `scripts/*.py` or integrating with Linotype.

## Core concept: the demand-supply contract

Imposer and Linotype form a **demand-supply pair** (editor ↔ copy desk):

- **Linotype is the demand side.** When a plate is underfilled, it emits a `demand.json` order sheet: per plate, the fill %, the deficit in pt, and the requested stories (type / word-count / source-rank / topic).
- **Imposer is the supply side.** It matches cached material by spec, compresses over-length stories via the **agent executing the rewrite** (compress-only; `rewrite.py` is an optional headless fallback), backfills, and re-typesets until Linotype reports the page filled — or honestly reports it cannot be filled within bounds.

This is more precise than one-way signals: the engine tells you *exactly what to fill*, not just "something is empty."

## The demand.json protocol

```
{"plates": {"P3": {"fill": 0.31, "deficit_pt": 104.2, "requests": [
  {"type": "brief", "count": 2, "words": [60, 90], "topic": "space", "min_kind": "agency"}]}}}
```

Request types by deficit (Linotype `estimate_requests`):
- `deficit < 100pt` → `brief` (60-90 words)
- `100-300pt` → `main` (250-400 words) + briefs
- `> 300pt` → `deep_dive` (400-600 words, think-tank) + briefs

Topic / min_kind per plate: P1 world/military + china-official · P2 ai/tech + company · P3 space + agency · P4 china-tech + china-official.

`fill_min` is configurable via `--docopts fill_min=0.65` (serious-newspaper standard). Default 0.45 preserves Linotype's original behavior.

## Compress-only iron rule (user decision 2026-08-05; agent-executed 2026-08-05)

> 只允许在版面紧张情况下压缩概括，不允许扩写。

**Primary path — the agent executes the rewrite.** Imposer is a skill; the skill is invoked
by an agent, and the agent *is* an LLM. `supply.py` marks approximate matches with
`needs_rewrite: true` + `target_words: [lo, hi]`; the agent compresses each marked item
per SKILL.md's 改写规则 chapter (compress-only, hard cap, attribution preserved) and
backfills. No script calls a second Claude API (that path accumulated anthropic-package /
PEP 668 / SSE-parsing / CLI-contamination issues and was a detour).

**Fallback — `rewrite.py` (headless cron, optional).** Kept for automation without an
agent. It enforces the same rules mechanically:
1. If input words ≤ max_words, return verbatim (never call LLM, never expand).
2. If input overflows, compress to `[min_words, max_words]` via Claude API.
3. Hard cap: LLM output truncated to max_words if it ever exceeds.
4. Empty LLM output (nonsense input) → extractive fallback (first N words of source).
5. Attribution preserved: "according to Xinhua", "Reuters reported" survive compression.

## Source collection

- RSS-first with page-scraping fallback; **concurrent** via ThreadPoolExecutor + as_completed (55 sources ~28s; serial > 2min — the original bottleneck).
- `SUMMARY_TOP_N = 2`: only the top 2 page candidates get first-paragraph summaries (limits request count; full article fetching is a directed-fetch extension).
- English-only filter: Latin-ratio ≥ 0.85 on title+summary, rejecting Cyrillic/Bulgarian/language-switcher links (CGTN's "Български" case).
- XML entity resilience: undefined entities (`&nbsp;`, `&mdash;`…) in RSS feeds previously dropped the *whole source* — now replaced once and re-parsed.

## Composition (build_plates.py)

- Writes to `<out_dir>/plates/` (Linotype consumes the `plates/` dir).
- Raw text, no pre-escaping — Linotype's `build.py` escapes fields (pre-escaping caused double-escape `5%` → `5\\%`).
- P1 uses `LAYOUT: main-aside`; P2/P3/P4 `COLUMNS: 3`.
- STORY-B followed by direct paragraphs (a `BODY:` line after STORY-B routes into the main body — Linotype parsing quirk).
- Selection key (post final review + Phase 6): mains = `topic penalty → supply tier → kind rank → length`; briefs = `topic penalty → supply tier → target-distance → kind rank`. Supply tier (C-1c): 0 = on-spec supplied (words within `request.words`), 1 = slot-matched supplied but outside range (nearest to target first), 2 = unsupplied / slot mismatch (neutral). The target-distance axis outranks `kind_rank` in brief selection so supplied NASA briefs land in the slot instead of being squeezed by china-official (rank 0).
- Main word-count gate (C-1c): `MIN_MAIN_WORDS = 100` — mains are drawn from a ≥100-word pool first; only when no ≥100-word material exists (素材用尽) does selection fall back to the best available, so a 38-word supplied brief never headlines a plate.
- Story-level dedup (I-2): same URL / same normalized title selected once within a plate (fetch-level too), **plus a four-plate pool-level used-URL set** in `write_plates` — a URL is used only by the first plate that picks it (P3/P4 share the China Daily RSS; P1/P4 share GT/Xinhua).
- Recency (I-3): `is_stale` — date >30 days (RFC2822 + ISO parse) excludes archive stories; **date-empty items fall back to the URL date path** (`/a/201712/12/`, `/page/202608/`, `/2026/08/[05]/`); items with no date signal at all are kept unless the title reports an obviously old year (conservative exclusion).
- Topic (I-4, lightweight): per-plate negative title keywords deprioritize obviously off-topic items (and record them); supply hard-skips them. General-China feed leaks that miss the keyword list are caught by the review gate.
- Source-rank priority (China-friendly): china-official < thinktank < agency < company < china-ai < independent < tech-media < aggregator < western.
- Attribution: `By {reporter} · {source}`; no reporter → `By {source} News Desk`; briefs end with `— {source}.`

## Supply matching (supply.py)

- `match_cache`: kind rank ≤ request min_kind, word count within `[min, max]` (no slack — over-length goes to rewrite), English filter, skip used URLs, skip stale (date >30d) and topic-mismatched (title keyword penalty) items.
- Rewrite fallback: closest in-kind material flagged `needs_rewrite` + `target_words` — **the agent compresses these** (primary path; `rewrite_fn=None` keeps the markers in place as the agent's signal). If a `rewrite_fn` is passed (headless fallback via rewrite.py), failure is per-item fault-tolerant (try/except keeps the original + warning — a rewrite outage never aborts the supply round).
- Used persistence (C-1b): every supplied item is marked `used=True` **in place** and carries the matched `request` — cache backfill then persists both, so round 2 never re-supplies the same story and build_plates can match slots.
- Dedupe: fetch_fn results recorded in `used`; duplicate URLs discarded (宁缺毋滥).

## Lessons (integrations surfaced by E2E)

1. **fill_min must not reach linotype.cls** — it's a build.py autofit threshold, not a LaTeX keyval. Filtering it from `base` docopts was the fix (a missing filter caused "fill_min undefined" keyval error + empty-fill false convergence).
2. **Empty fills = false convergence** — autofit converges on `not fills`; a failed compile (e.g. keyval error) yields no `Plate content` lines and autofit "converges" with fill=0. Always verify the log has content lines.
3. **CLI `--print` is session-contaminated** — Claude CLI printed the session's system prompt as output. `--output-format stream-json` + SSE parse is reliable; the anthropic API path parses both SDK objects and local-proxy SSE strings.
4. **Anthropic local proxy returns SSE strings** — `ANTHROPIC_BASE_URL` pointing at a forwarding proxy makes `messages.create` return raw SSE. Parse `data: {json}` lines for `content_block_delta`/`text_delta`.
5. **Summaries cap at ~70 words** — first-paragraph extraction cannot supply `main` (250-400 word) specs. Compress-only means short material stays short; directed full-article fetch is the extension point.
6. **Concurrent fetch needs as_completed** — `ex.map` blocks on the slowest worker; `as_completed` returns as each finishes. Plus per-request timeout (8s) so slow sources don't stall the whole round.
7. **Short sources never satisfy big deficits** — "compress-only" + sparse cache means underfilled plates persist; honest reporting (≤2 rounds, then stop) is the contract.
8. **Font-scaling is not backfill** — autofit raises fill by enlarging type; only content backfill raises it structurally. Never report "fill rose" as loop evidence (the first E2E report made this error; corrected in Phase 5).
9. **Dedup must keep the annotated original** — supply attaches `request` to backfilled *copies*; a URL-dedup that keeps the first (unannotated) occurrence silently drops slot priority. Mark the original in place (C-1b fix).
10. **Overfull has four faces** — linotype.cls emits `Overfull plate: content`, `main column`, `aside column`, `mainstory`. Matching only `plate: content` missed real truncations (a 6pt mainstory cut on P1).
11. **A filter that silently skips its own trigger is a trap** — `is_stale` only fired on a `date` field, and the China Daily comprehensive RSS emits empty dates, so the 2017 archive (URL `/201712/12/`) sailed through. Every filter needs a fallback signal (URL date path) and a conservative catch-all (title-year), not a silent pass.
12. **Slot priority must outrank editorial rank within its tier** — a 2-level "supplied-slot priority" still let `kind_rank` decide *within* the matched tier, so china-official (0) squeezed supplied NASA agency items out of the brief slots. A 3-tier priority with a target-distance axis (and a main word-count gate) is what actually lands backfill in the pages.
13. **Dedup scope is per consumer, not per story** — intra-plate dedup left the same 2017 URLs as headlines in both P3 and P4. When plates share feeds (P3/P4 China Daily, P1/P4 GT/Xinhua), the used-URL set must span the whole four-plate pool.

## QA layers

| Layer | What | Failure mode |
|---|---|---|
| Unit tests | 44 tests (fetch 8 / demand 4 / supply 10 / build_plates 17 / rewrite 5), no pytest needed | any pipeline regression |
| Review gate | human pass over the material manifest before composing (SKILL.md 审料门, 5 checks) | junk that beats the automatic filters reaches a plate |
| Compile-time | Linotype Overfull warnings (`plate: content` / `main column` / `aside column` / `mainstory`) + fill typeout | content exceeds viewport |
| Demand check | `parse_demand.py` — health report + order sheets | underfilled plates trigger supply |
| Visual | Linotype `--visual` pixel-check (blank bands) | visually sparse pages |

## Known limitations (accepted)

- **Compress-only**: short material used as-is; big deficits may persist without directed full-article fetching.
- **Agent-executed rewrite**: the primary compression path needs an agent at the controls (imposer is a skill, so that's the normal case); headless cron automation uses `rewrite.py` + `anthropic`/API key (or Claude CLI) as the documented fallback.
- **Source volatility**: rate-limits (Blue Origin 429, Microsoft 403) are logged and skipped, not fatal.
- **Residual scrape junk**: page-scraped sources can leak nav/topic-page links (RAND topic pages, Amazon nav) that beat the automatic filters — the review gate is the designed catch; per-source parsing rules are the extension point.
- **Residual topic leaks**: general-China feeds (China Daily RSS) in P3/P4 can supply politics stories that miss the lightweight keyword list — review gate catches; per-section source curation or stronger topic signals are the extension point.
- **Brief slots cap at 3/plate**: brief-based supply cannot structurally converge a plate past ~3 briefs + 2 mains; larger deficits need a main-story upgrade or directed full-article fetch.
