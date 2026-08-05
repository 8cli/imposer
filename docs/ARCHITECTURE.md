# Imposer Architecture

This document records Imposer's key design decisions and the lessons behind them. It is the reference for anyone extending `scripts/*.py` or integrating with Linotype.

## Core concept: the demand-supply contract

Imposer and Linotype form a **demand-supply pair** (editor ↔ copy desk):

- **Linotype is the demand side.** When a plate is underfilled, it emits a `demand.json` order sheet: per plate, the fill %, the deficit in pt, and the requested stories (type / word-count / source-rank / topic).
- **Imposer is the supply side.** It matches cached material by spec, compresses over-length stories with LLM (compress-only), backfills, and re-typesets until Linotype reports the page filled — or honestly reports it cannot be filled within bounds.

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

## Compress-only iron rule (user decision 2026-08-05)

> 只允许在版面紧张情况下压缩概括，不允许扩写。

`rewrite.py` enforces this mechanically:
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
- Source-rank priority (China-friendly): china-official < thinktank < agency < company < china-ai < independent < tech-media < aggregator < western.
- Attribution: `By {reporter} · {source}`; no reporter → `By {source} News Desk`; briefs end with `— {source}.`

## Supply matching (supply.py)

- `match_cache`: kind rank ≤ request min_kind, word count within `[min, max]` (no slack — over-length goes to rewrite), English filter, skip used URLs.
- Rewrite fallback: closest in-kind material flagged `needs_rewrite` + `target_words`; `rewrite_fn` (rewrite.py) compresses.
- Dedupe: fetch_fn results recorded in `used`; duplicate URLs discarded (宁缺毋滥).

## Lessons (integrations surfaced by E2E)

1. **fill_min must not reach linotype.cls** — it's a build.py autofit threshold, not a LaTeX keyval. Filtering it from `base` docopts was the fix (a missing filter caused "fill_min undefined" keyval error + empty-fill false convergence).
2. **Empty fills = false convergence** — autofit converges on `not fills`; a failed compile (e.g. keyval error) yields no `Plate content` lines and autofit "converges" with fill=0. Always verify the log has content lines.
3. **CLI `--print` is session-contaminated** — Claude CLI printed the session's system prompt as output. `--output-format stream-json` + SSE parse is reliable; the anthropic API path parses both SDK objects and local-proxy SSE strings.
4. **Anthropic local proxy returns SSE strings** — `ANTHROPIC_BASE_URL` pointing at a forwarding proxy makes `messages.create` return raw SSE. Parse `data: {json}` lines for `content_block_delta`/`text_delta`.
5. **Summaries cap at ~70 words** — first-paragraph extraction cannot supply `main` (250-400 word) specs. Compress-only means short material stays short; directed full-article fetch is the extension point.
6. **Concurrent fetch needs as_completed** — `ex.map` blocks on the slowest worker; `as_completed` returns as each finishes. Plus per-request timeout (8s) so slow sources don't stall the whole round.
7. **Short sources never satisfy big deficits** — "compress-only" + sparse cache means underfilled plates persist; honest reporting (≤2 rounds, then stop) is the contract.

## QA layers

| Layer | What | Failure mode |
|---|---|---|
| Unit tests | 20 tests (fetch 6 / demand 3 / supply 3 / build_plates 8), no pytest needed | any pipeline regression |
| Compile-time | Linotype `Overfull plate` warnings + fill typeout | content exceeds viewport |
| Demand check | `parse_demand.py` — health report + order sheets | underfilled plates trigger supply |
| Visual | Linotype `--visual` pixel-check (blank bands) | visually sparse pages |

## Known limitations (accepted)

- **Compress-only**: short material used as-is; big deficits may persist without directed full-article fetching.
- **Rewrite needs LLM**: `rewrite.py` requires `anthropic` + API key (or Claude CLI); everything else works without it.
- **Source volatility**: rate-limits (Blue Origin 429, Microsoft 403) are logged and skipped, not fatal.
