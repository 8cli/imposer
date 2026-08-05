<div align="center">

# 📰 Imposer

**The compositor for Linotype — a demand-driven English daily newspaper orchestrator**

Turn authoritative China-friendly news sources into print-quality English daily newspapers, powered by a **demand-supply contract** with the Linotype typesetting engine.

`fetch → build_plates → linotype --demand → supply → agent rewrite → converge`

[Quick Start](#quick-start) · [Demand-Supply Contract](#demand-supply-contract) · [Content Format](#content-format) · [Sources](#sources) · [CLI Reference](#cli-reference) · [中文 README](README.zh-CN.md)

</div>

---

## What is Imposer?

Imposer is the **compositor** (拼版工) for the Linotype typesetting engine. In hot-metal printing, the compositor arranges Linotype-cast lines into pages, reads the proofs, and adjusts the layout. Imposer does exactly that in software:

1. **Collects** source material from authoritative China-friendly news sources (RSS + page scraping, concurrent)
2. **Composes** it into Linotype's `plates/*.md` field format (main stories + briefs, with reporter/source attribution)
3. **Reads Linotype's demand signals** — when a plate is underfilled, Linotype emits a `demand.json` "order sheet" (fill %, deficit, requested story specs)
4. **Supplies matching stories** by spec (topic × word-count × source-rank); the agent compresses over-length material to fit tight columns (compress-only, never expand)
5. **Iterates** until Linotype reports the page is filled — or honestly reports it cannot be filled within bounds

Its core differentiator is the **demand-supply contract**: Linotype is the demand side (it says exactly what it needs), Imposer is the supply side (it finds or rewrites to spec). This is more precise than one-way signals — the engine tells you precisely what to fill.

## Features

- **Demand-supply contract** — Linotype emits `demand.json` (per-plate fill %, deficit in pt, requested stories by type/words/source-rank); Imposer supplies exactly what's requested
- **Agent-executed compression (compress-only)** — Imposer is a skill; the agent that runs it *is* an LLM, so it compresses over-length stories directly per the rewrite-rules chapter in SKILL.md. `supply.py` marks each item with `needs_rewrite` + `target_words` as the agent's signal. **Never expands**: short material is used as-is (no fact fabrication)
- **Compress-only iron rule** — short stories (≤ word cap) are returned verbatim; only over-length stories are compressed. Quality over forced filling. `rewrite.py` (Claude API) remains as an optional fallback for headless cron automation
- **Concurrent source collection** — 55+ sources across 4 sections fetched in parallel (~28s), RSS-first with page-scraping fallback
- **English-only filter** — rejects non-Latin material (Cyrillic, Bulgarian, language-switcher links) to preserve the English-daily positioning
- **Serious-newspaper standard** — configurable `fill_min` threshold (default 0.45, serious standard 0.65): underfilled plates trigger order sheets instead of accepting sparse pages
- **Full attribution** — every story keeps reporter name + source (`By John Smith · Reuters`; no byline → `By {source} News Desk`); briefs carry source at the end
- **China-friendly editorial stance** — Chinese official media (GT/Xinhua/CGTN/China Daily) are primary sources; Western media supplement only
- **Honest failure** — no demand can be met → stops and reports (never fabricates content)
- **Zero heavy deps** — collection/composition use only Python stdlib; the agent-executed rewrite needs no packages at all (`anthropic` is only needed by the optional `rewrite.py` fallback)

## Architecture

```
news sources (55+, 4 sections)
      │  fetch_sources.py (concurrent RSS + page)
      ▼
fetch_results.json  +  sources/pN.md archive
      │  build_plates.py (field format + attribution)
      ▼
plates/p1-p4.md  ──►  linotype build.py --demand (xelatex)
                          │
                          ▼
                     out.pdf + demand.json (order sheet)
                          │
                          ▼
      supply.py (needs_rewrite + target_words manifest)
                          │  agent compresses per SKILL.md rewrite rules
                          ▼
                     backfill cache (used=True)
      │   ▲                                        │
      └───  iterate ≤2 rounds until demand.json empty — or honest stop ──┘
      (rewrite.py = optional headless fallback for the agent step)
```

## Quick Start

```bash
# 1. Collect sources (4 sections in parallel, ~28s)
DAILY=~/news/daily/$(date +%F); mkdir -p $DAILY/sources $DAILY/plates
python3 scripts/fetch_sources.py scripts/sources.json $DAILY

# 2. Compose plates (review material first — see "review gate")
python3 scripts/build_plates.py $DAILY/fetch_results.json $DAILY

# 3. Typeset with Linotype (run in engine dir; fill_min=0.65 serious standard)
cd ~/news/latex && python3 build.py $DAILY/plates $DAILY/out.tex \
  --docopts "paper=a3,landscape,columns=3,plates=2,fill_min=0.65" --demand && cd -

# 4. Read the order sheet
python3 scripts/parse_demand.py $DAILY/build.log --log $DAILY/out.log --demand $DAILY/demand.json

# 5. Supply loop: match → agent compresses per SKILL.md rewrite rules → backfill
#    → re-compose → re-typeset (≤2 rounds; full agent-executed loop in SKILL.md)
```

The first daily edition (2026-08-05), honestly reported: 54 sources → 4 plates → Linotype typeset with autofit + `--demand`. **Two earlier claims about this artifact were wrong and are corrected here**: (1) "P3 briefs = supplied NASA items" — the actual p3.md briefs were China Daily 2017 archives + JAXA + CNSA, because slot priority stopped at `kind_rank` (china-official rank 0 squeezed out agency); (2) "2017 archive no longer enters plates" — the actual P3/P4 headlines were the 2017-12-12 "Taiwan's New Party" archive, whose empty `date` field bypassed the recency filter. After the Phase-6 fixes (URL-date recency fallback, four-plate pool-level dedup, 3-tier supply slot priority + main word-count gate), re-running `build_plates.py` on the same cache produces plates with **zero 2017/archive URLs, zero cross-plate duplicate URLs, and p3.md briefs that are the supplied NASA items** ("Advanced Mini-laboratories…", "NASA Will Attempt…", "NASA's PUNCH…"). P3/P4 brief deficits persist (final fill 56% / 54%): fill gains during autofit come from **font-scaling, not content backfill**, and the loop **honestly stops and reports the unmet demand** instead of claiming convergence. Full convergence requires directed full-article fetching (documented extension point) or accepting the sparse-but-honest layout. Reproduce: `fetch_sources.py` → `build_plates.py` → linotype `--demand` → the agent-executed loop in `SKILL.md`.

## Review gate (审料门)

Composing plates is **not mechanical pasting** — before `build_plates.py` runs, a human reviews the collected material once. This is the last line of defense against junk reaching the page (nav text, podcast pages, ICP filing pages, `javascript:;` links, stale archive stories).

1. **Read the manifest** — `$DAILY/sources/p1.md … p4.md` (or `fetch_results.json`): title / byline / topic / date / URL per item.
2. **Five checks** — drop any item that fails one:
   - **Title**: a real headline, not nav copy ("Download press kit", an email, `About Us`)
   - **Attribution**: has a reporter or source name, traceable
   - **Topic**: matches the section (P1 world/military · P2 ai/tech · P3 space · P4 china-tech)
   - **Recency**: not a >30-day archive story
   - **URL legality**: `http(s)`, not a filing page, not `javascript:`/`#`/nav link
3. **Only then compose** — run `build_plates.py`.
4. **Supplied backfill passes the gate too** — supply output (`used=True` items) enters plates via cache backfill; re-read `parse_demand.py` output to review what was supplied.

> Automatic front-gates run in code (`fetch_sources.py` URL/title filtering, `build_plates.py` recency/topic/dedup) — the review gate is the human master switch for what they miss.

## Demand-Supply Contract

Linotype emits `demand.json` when a plate is underfilled (`--demand` + `fill_min`):

```json
{"plates": {"P3": {"fill": 0.31, "deficit_pt": 104.2, "requests": [
  {"type": "brief", "count": 2, "words": [60, 90], "topic": "space", "min_kind": "agency"}]}}}
```

| Field | Meaning |
|---|---|
| `fill` | plate utilization (content height / viewport height) |
| `deficit_pt` | how many pt of content are missing to reach `fill_min` |
| `requests[].type` | `brief` (<100pt deficit) · `main` (100-300pt) · `deep_dive` (>300pt, think-tank) |
| `requests[].words` | target word range (e.g. [60, 90] for a brief) |
| `requests[].min_kind` | minimum source rank (China-friendly priority) |
| `requests[].topic` | plate topic (P1 world/military · P2 ai/tech · P3 space · P4 china-tech) |

Imposer's `supply.py` matches cached material by `topic × words × min_kind`; if a longer-than-cap story is closest, it is flagged `needs_rewrite` + `target_words` and **the agent compresses it** to the target range (compress-only; `rewrite.py` is the optional headless fallback). Backfill → re-compose → re-typeset → read demand again, **≤2 rounds** to avoid infinite loops.

## Content Format

Each plate is a `plates/pN.md` with Linotype field labels:

```markdown
LAYOUT: main-aside        # P1 uses main-aside (main 2-col + aside 1-col)
COLUMNS: 3                # P2/P3/P4 equal columns
KICKER: WORLD & DIPLOMACY # P1 · AI & TECH (P2) · SPACE EXPLORATION (P3) · CHINA TECH (P4)
HEADLINE: Main story title
DECK: Standfirst
BYLINE: By John Smith · Reuters   # attribution iron rule
BODY:
Paragraph one...
Paragraph two...
STORY-B: Secondary story
Sub-paragraph...
BRIEFS:
**Brief title:** Brief content — Reuters.
```

Special characters are escaped by Linotype's `build.py` (Imposer writes raw text — no double-escaping). Full field reference in Linotype's README.

## Sources

**China-friendly editorial stance**: Chinese official media are primary; Western media supplement only; think-tanks provide one deep-dive per issue.

| Section | Primary (china-official) | Supplement |
|---|---|---|
| P1 World & Military | Global Times, Xinhua, CGTN | Al Jazeera, TASS, Asia Times, AMR, Naval News, DefenceTalk, WaPo/NYT/VOA/ABC (western supplement), CSIS/Brookings/RAND/CFR (think-tank) |
| P2 AI & Tech | Moonshot, Z.ai, DeepSeek, Alibaba | Google, OpenAI, Anthropic, NVIDIA, xAI, Cloudflare, MS, GitHub, Amazon, Yahoo/AOL, MIT/Ars |
| P3 Space | CNSA, Xinhua Space | NASA, ESA, JAXA, ISRO, SpaceX, Rocket Lab, SpaceNews, Space.com, NASA Spaceflight, Universe Today |
| P4 China Tech | China Daily, Global Times, Xinhua | SCMP |

All URLs verified reachable (2026-08-05). Edit `scripts/sources.json` to add/remove sources.

## CLI Reference

| Script | Purpose | Key args |
|---|---|---|
| `fetch_sources.py` | Concurrent RSS+page collection | `<sources.json> <out_dir>` (→ fetch_results.json + sources/pN.md) |
| `parse_demand.py` | Read build output + demand.json → health report | `<build.log> [--log x.log] [--demand demand.json]` |
| `supply.py` | Match demand → stories (agent rewrite markers; rewrite_fn optional) | `<demand.json> <fetch_results.json> <sources.json> <out_dir>` |
| `rewrite.py` | Optional headless compress-only rewrite (Claude API) | `<summary> <min_words> <max_words> [--source X] [--title Y]` |
| `build_plates.py` | Material → linotype field-format plates (recency URL fallback + pool-level cross-plate dedup) | `<fetch_results.json> <out_dir>` (→ plates/p1-p4.md) |
| `tests/run_tests.py` | Regression suite (44 tests) | `python3 tests/run_tests.py` |

## Requirements

- **Linotype** (`~/news/latex` or the [linotype repo](https://github.com/8cli/linotype)) — the typesetting engine, with `--demand` support (build.py ≥ 2026-08-05)
- **Python 3.10+** (stdlib for collection/composition)
- **An agent** (normal case) to execute the rewrite per SKILL.md rules; or, for headless cron automation, the optional `rewrite.py` fallback needs `anthropic` + `ANTHROPIC_API_KEY` (falls back to Claude CLI)
- **xelatex** (TeX Live) — via Linotype

## Project Layout

```
├── SKILL.md               # Orchestration manual (agent-facing; rewrite rules chapter)
├── scripts/
│   ├── sources.json       # 55+ verified sources (P1-P4)
│   ├── fetch_sources.py   # Concurrent RSS+page collection
│   ├── parse_demand.py    # Linotype demand → health report
│   ├── supply.py          # Demand-supply matching (agent rewrite markers)
│   ├── rewrite.py         # Optional headless compress-only fallback (Claude API)
│   └── build_plates.py    # Material → linotype plates (recency + cross-plate dedup)
├── tests/                 # Regression suite (44 tests, no pytest needed)
└── docs/                  # Design spec & dev history
```

## Known Limitations (accepted)

- **Compress-only**: material shorter than the word cap is used as-is (never expanded) — underfilled plates may persist if the cache lacks sufficient material; directed fetching of full articles is the natural next step
- **Agent-executed rewrite**: the primary compression path needs the agent at the controls (normal for a skill); headless cron automation uses the optional `rewrite.py` fallback (`anthropic` + API key or Claude CLI)
- **No text-wrap images**: image handling follows Linotype's `\photo` (plate-top / between-element)
- **Source volatility**: some sources rate-limit (Blue Origin 429, Microsoft 403 transient); failures are logged and skipped, not fatal
- **Residual scrape junk / topic leaks**: page-scraped nav or general-China politics stories can beat the automatic filters — the review gate is the designed catch; per-source parsing rules and stronger topic signals are the extension points
- **Brief slots cap at 3/plate**: brief-based supply alone cannot structurally converge a plate past ~3 briefs + 2 mains; larger deficits need a main-story upgrade or directed full-article fetch

## License

[MIT](LICENSE) © 2026 Yu (8cli)
