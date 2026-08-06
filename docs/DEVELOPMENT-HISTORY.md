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

## Phase 4 — The closed loop (honestly reported)

```
real sources (54, concurrent 28s) → build_plates 4 plates → linotype --demand fill_min=0.65
  → demand.json: P2/P3/P4 brief requests
  → supply match → (rewrite compress) → backfill cache (used=True) → rebuild plates → re-typeset
  → 2 rounds: 4 + 4 stories supplied, none supplied twice
  → P3/P4 brief deficits persist (final fill 56% / 54%) → honest stop + report
```

**Honest statement (corrected after final review)**: the first E2E report claimed "P1 filled 59→65%+, P4 main-story deficit eliminated 48→55%" as closed-loop verification. That was wrong on three counts — (1) fill increases during autofit come from **font-scaling, not content backfill**; (2) the loop never regenerated plates after supply, so supplied stories never entered the pages; (3) used markers weren't persisted, so round 2 re-supplied round 1's stories. After the Phase 5 fixes, the loop re-runs build_plates and persists used markers. **Phase 6 correction — the Phase 5 "NASA briefs enter P3" evidence was itself wrong**: the actual 2026-08-05 artifact's p3.md briefs were China Daily 2017 archives + JAXA + CNSA, not NASA — the slot-matching priority stopped at `kind_rank`, which let china-official (rank 0) squeeze out the supplied NASA agency items; and the P3/P4 headlines were the 2017-12-12 "Taiwan's New Party" archive whose empty `date` field bypassed `is_stale`. All corrected in Phase 6 (see below). The P3/P4 brief deficits persist structurally (brief slots cap at 3/plate); directed full-article fetching (fetch_fn) is the documented extension point.

## Phase 5 — Final review (2 Critical + 6 Important), one fix wave

Whole-project review found the closed loop could not converge and the docs over-claimed. All fixed in one wave (2026-08-05):

| Finding | Fix |
|---|---|
| C-1a loop never re-ran build_plates | SKILL.md loop calls `build_plates.py` every round before re-typesetting |
| C-1b used marker not persisted | `supply_requests` marks items `used=True` (+ attaches `request`) in place; cache backfill persists it — round 2 never re-supplies the same URL (verified: all supplied URLs unique) |
| C-1c supplied stories never entered plates | `pick_main_stories`/`pick_briefs` prefer slot-matching supplied items (used + request.words), after topic penalty; `_dedup` keeps the annotated original. **Phase 6 correction**: the first attempt (2-level priority) still let `kind_rank` decide *within* the slot-matched tier, so the actual 2026-08-05 artifact had China Daily 2017 archives — not the supplied NASA items — in p3.md briefs. Fixed in Phase 6 with a 3-tier slot priority + target-distance axis + main-word-count gate |
| C-1d silent loop exit | loop ends with an honest report listing every unmet demand (≤2-round stop) |
| C-2 docs over-claimed convergence | README×2 + this file rewritten to the honest, reproducible account above |
| I-1 overfull detection missed 3 patterns | parse_demand matches all 4 linotype.cls patterns (`plate: content` / `main column` / `aside column` / `mainstory`) — a real 6pt `Overfull mainstory` on P1 is now caught |
| I-2 no story-level dedup | fetch_rss + fetch_page dedup by URL+title; pick_* dedup pools (verified: no duplicate headline/brief in any plate). **Phase 6 correction**: intra-plate dedup left cross-plate duplicates — the same 2017 China Daily URLs were headlines in both P3 and P4. Fixed in Phase 6 with a four-plate pool-level used-URL set |
| I-3 no recency filter | `is_stale` (>30 days) excludes archive stories in build_plates + supply; date-less items kept. **Phase 6 correction**: `is_stale` only fired on a `date` field; China Daily's comprehensive RSS emits items with an empty `date` (the 2017-12-12 archive became P3/P4 headlines). Fixed in Phase 6 with a URL-date-path fallback (`/201712/12/`) + conservative title-year exclusion |
| I-4 topic unused end-to-end | topic → plate map; title keyword penalty in build_plates (deprioritize + record) and supply (hard skip); residual general-China leaks (e.g. cross-strait politics in P4) are documented as a lightweight-filter limitation caught by the review gate |
| I-5 no review gate | SKILL.md/README 审料门 section (5 checks before composing); fetch_page URL/title/paragraph junk filters (`javascript:`, beian.miit.gov.cn, `/about` `/podcast` `/multimedia`, "Skip to…", "opens in a new window", email-titles, "File photo" captions) |
| I-6 rewrite untested + crash-prone | `test_rewrite.py` (5 tests, injected `_call_anthropic`); `supply_requests` wraps rewrite_fn in try/except — failure keeps original + warning (no whole-round abort) |

Verified end-to-end on real sources: fetch → build → typeset → loop (2 rounds) → honest report; regression 38/38 green.

## Phase 6 — Agent-executed rewrite architecture + final-review hard fixes (2026-08-05)

Three hard findings survived the final review, plus a user decision that replaces the LLM-rewrite path:

**User decision — agent executes the rewrite (architecture change).** Imposer is a skill; the skill is invoked by an agent, and the agent *is* an LLM. Rewriting should therefore be done by the agent directly, not by `rewrite.py` calling the Claude API again (that path accumulated anthropic-package / PEP 668 / SSE-parsing / CLI-contamination issues and was a detour). Changes:
- `SKILL.md` closed loop is now a described **agent-executed procedure** (supply → agent compresses per the rewrite-rules chapter → backfill → build_plates → re-typeset → re-read demand), no Python heredoc.
- A complete **rewrite-rules chapter** (compress-only iron rule, hard `target_words` cap, attribution preserved, lead preserved, plain text output) tells the agent exactly how to compress.
- `supply.py` keeps `rewrite_fn=None` as the default: approximate matches keep `needs_rewrite: true` + `target_words` markers — the signal telling the agent which items to rewrite and to what word count.
- `rewrite.py` is demoted to an **optional fallback** for headless cron automation (no agent); the docs mark it as such.

**I-3 (recency) — the 2017 archive still reached the plates.** Root cause: `is_stale` only fired when a `date` field existed; China Daily's comprehensive RSS emits items with an empty `date`, so the 2017-12-12 archive (`/201712/12/` in the URL) became the P3 and P4 headlines. Fix: URL-date-path fallback (`/a/201712/12/`, `/page/202608/`, `/2026/08/[05]/`) when `date` is empty, plus a conservative title-year exclusion for items with no date signal at all. Verified: 0 archive URLs in any regenerated plate.

**I-2 (dedup) — duplicates were intra-plate only.** The same 2017 China Daily URLs were headlines in *both* P3 and P4 (P3/P4 share the China Daily comprehensive RSS; P1/P4 share GT/Xinhua). Fix: `write_plates` keeps a four-plate pool-level used-URL set — a URL is used only by the first plate that picks it; later plates skip it or substitute. Verified: 0 cross-plate duplicate URLs across the 24 URLs used in the four regenerated plates.

**C-1c (supply slot priority) — supplied NASA briefs still lost the slot.** Root cause: the 2-level slot priority put slot-matched supplied items in one tier, then let `kind_rank` decide *within* it — china-official (rank 0) squeezed out supplied NASA agency items, so p3.md briefs were China Daily/JAXA/CNSA, not NASA. Fix: 3-tier priority (on-spec supplied → nearest-to-target supplied → neutral) plus a target-distance axis that outranks `kind_rank` in brief selection, and a `MIN_MAIN_WORDS = 100` gate so a 38-word supplied brief never takes a main headline (fallback to the best available pool only when no ≥100-word material exists). Verified on the real cache: p3.md briefs are now the supplied NASA items ("Advanced Mini-laboratories…", "NASA Will Attempt…", "NASA's PUNCH…").

**Honest docs.** README×2 / ARCHITECTURE / this file corrected: the previous "14 unique supplied URLs", "P3 briefs = 3 NASA items", "2017 archive no longer in plates", and "60-word brief never steals a main slot" claims did not match the actual artifact (real counts: P3 12 / P4 10 unique supplied URLs; old p3.md briefs were China Daily + JAXA + CNSA; old P3/P4 headlines were the 2017 archive; the 38-word archive brief *was* the headline). All claims below are re-checked against regenerated output.

Regression: 44/44 green (fetch 8 / demand 4 / supply 10 / build_plates 17 / rewrite 5).

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
| 14 | loop never rebuilt plates after supply | C-1a: supply → backfill → build.py, no build_plates | re-run build_plates every round |
| 15 | round 2 re-supplied round 1's stories | C-1b: used set was local, never persisted | item["used"]=True in place + request attached |
| 16 | supplied NASA brief never entered p3.md | C-1c: pick_* ignored supplied markers; dedup kept annotation-less original | slot-matching priority + request on original |
| 17 | loop exited silently when not converged | C-1d: no report after 2 rounds | honest unmet-demand report |
| 18 | docs claimed "closed loop verified" | C-2: fill gains were autofit font-scaling, not backfill | README×2/HISTORY rewritten honestly |
| 19 | overfull detection missed mainstory etc. | I-1: regex only matched `Overfull plate: content` | match all 4 linotype.cls patterns |
| 20 | duplicate briefs/headlines in plates | I-2: no story-level dedup | URL+title dedup in fetch + pick_* |
| 21 | 2017 archive story as P3/P4 headline | I-3: date captured but unused | is_stale >30d filter in build_plates + supply |
| 22 | P4 headline was a memorial story | I-4: topic field unused end-to-end | topic→plate keyword penalty + record |
| 23 | nav/podcast/ICP junk reached plates | I-5: no review gate, no URL legality filter | 审料门 + URL/title/paragraph junk filters |
| 24 | rewrite failure aborted whole supply round | I-6: rewrite_fn called without try/except | try/except keep original + warning |
| 25 | 2017 archive still P3/P4 headline | I-3 phase-6: `is_stale` only fired on `date`; empty-date archive (URL `/201712/12/`) bypassed it | URL-date-path fallback + conservative title-year exclusion (build_plates + supply) |
| 26 | same 2017 URLs in P3 *and* P4 | I-2 phase-6: dedup was intra-plate only; P3/P4 share China Daily RSS | four-plate pool-level used-URL set in write_plates |
| 27 | supplied NASA briefs still lost p3.md slot | C-1c phase-6: 2-level priority then `kind_rank` decided within tier — china-official 0 squeezed out agency 2 | 3-tier priority + target-distance axis (briefs) + MIN_MAIN_WORDS=100 gate (mains) |
| 28 | 38-word supplied brief was P3/P4 headline | C-1c phase-6: no main word-count gate | ≥100-word primary pool; fallback only when material exhausted |
| 29 | fix report claimed "P3 briefs = NASA, 14 unique supplied" | C-2 phase-6: claims not checked against artifact | docs re-verified against regenerated output (real: P3 12 / P4 10 unique supplied URLs) |
| 30 | 66-word summary cannot supply a 250-400 main | compress-only iron rule + short RSS descriptions | `fetch_fulltext()` + `fulltext_fn` — main/deep-dive specs auto-fetch the article (272-word E2E), summaries for briefs + fallback |
| 31 | P4 matched SCMP "Brazil borrower" finance story | P4 pool was 4 China sources; after widening, international general RSS overflow | positive `_tech_gate`: non-China titles without tech keywords deprioritized; China-official stays identity core |
| 32 | brief spec got fulltext fetched | fulltext intended for mains only | gate on `words[0] >= 250` — briefs skip fulltext_fn |
| 33 | RSSHub installed to "fix" the 3 failing sources | assumed RSSHub rescues anti-bot-blocked feeds | measured: RSSHub has **no** route for WaPo/Microsoft/Blue Origin; its Nature route is dead (503); only OpenAI/Anthropic have live news routes — wired those via `rsshub` field + fallback to direct scrape |
| 34 | RSSHub route returns empty | route stale or upstream changed | automatic fallback to the original page-scrape (`rsshub` field is a preference, not a single point of failure) |

## What survives

- **52 regression tests** → `tests/run_tests.py` (fetch 8 / demand 4 / supply 16 / build_plates 19 / rewrite 5)
- **Demand-supply protocol** → linotype `--demand` (25/25 regression intact) + `demand.json` schema
- **Compress-only iron rule** → agent-executed rewrite (SKILL.md 改写规则 chapter, user decision); `rewrite.py` kept as optional headless fallback
- **Closed-loop mechanics** → build_plates regeneration + used persistence + 3-tier slot priority + main-word gate + pool-level cross-plate dedup + honest stop, verified E2E on the real 2026-08-05 cache
- **Review gate** → SKILL.md/README 审料门 (human master switch over the automatic filters)
- **Every measurement above is reproducible** — run the scripts on the examples or the E2E daily.

The design debt we chose to accept: compress-only (no expansion means underfilled plates may persist), agent-executed rewrite requires an agent (headless runs use `rewrite.py` + LLM). Full-article fetching (2026-08-05 evening) closed the directed-fetch gap: mains now have real full text to compress; remaining shortfall is genuine source scarcity, reported honestly.

## Phase 7 — Full-text-first supply + P4 widening (2026-08-05 evening)

User decisions: *"如果你需要全文而不是摘要就可以满足排版需求，优先放全文。摘要是没有办法时候用。"* (full text first, summary fallback) and *"P4，从国际信源找科技报道也是可以的，比如核聚变等等。"* (P4 = China tech + international breakthroughs).

| Change | Where | Evidence |
|---|---|---|
| `fetch_fulltext(url, max_chars=8000)` — all article paragraphs, sentence-boundary truncation | `fetch_sources.py` | reuses existing paragraph junk filters |
| `supply_requests(..., fulltext_fn)` — fetch full text for `words[0] >= 250` candidates; attach `fulltext`; summary fallback on failure | `supply.py` | E2E: SCMP summary 66 words → full text 272 words, genuinely in [250,400] |
| `match_cache` counts `fulltext` words; fulltext-hit still marks `needs_rewrite` (compress back into summary) | `supply.py` | cached full text reused across loop rounds, no re-fetch |
| linotype P4: `topic "tech"`, `min_kind "tech-media"` | `linotype-repo/build.py` (both copies) | demand now accepts rank ≤ 6 international tech sources |
| `TOPIC_TO_PLATE["tech"] = 4` (keeps `china-tech` compat) | `build_plates.py` | demand topic maps to plate 4, not default 1 |
| P4 sources +6: ITER, Phys.org, TechXplore, Nature, IEEE Spectrum, New Scientist | `sources.json` | live fetch: P4 pool 4 → 10 sources, 80 items |
| `_tech_gate` — P4 positive subject gate for non-China items | `build_plates.py` + `supply.py` | live match: Brazil finance gated, defence-AI story hit |
| SKILL.md full-text-first rule (rewrite rule 0) + loop step 3 wording | `SKILL.md` | agent compresses full text, never expands a short summary |
| +6 tests (5 supply fulltext/gate, 1 build_plates tech gate/mapping) | `tests/` | 44 → 52, all green; linotype 25/25 intact |

## Phase 8 — Local RSSHub (2026-08-05 late evening)

User asked whether direct scraping is the problem and whether a self-hosted RSSHub would be more reliable. Decision: deploy local Docker RSSHub (persistent) and measure what it actually covers before trusting it.

| Measurement | Result |
|---|---|
| 61 sources, direct scrape | 58/61 OK (95%) — WaPo timeout, Microsoft 403, Blue Origin 429 |
| RSSHub route coverage for our sources | only **OpenAI + Anthropic** have live news routes (10 items each, E2E verified); TASS/Nature routes are dead; NASA is only apod (not news); CGTN only podcast; Microsoft only addon/mcr; DeepSeek route serves Chinese API docs; google/amazon/yahoo empty or non-news; ESA/CNSA/JAXA/ISRO/SpaceX/GlobalTimes/Xinhua/CSIS/Brookings/RAND/ABC/NavalNews/AsiaTimes/DefenceTalk/EurAsianTimes/ITER/BlueOrigin have **no** route |
| Conclusion | RSSHub is an incremental stabilizer, not a rescue for anti-bot sources. It cannot fix what the origin sites refuse to serve |

Wired the useful part: sources.json now carries `"rsshub"` route paths (OpenAI `/openai/news`, Anthropic `/anthropic/news`); `fetch_sources.py` prefers the RSSHub route (community-maintained precise parsing) and **falls back to direct page-scraping when it returns empty** — a preference, not a single point of failure. +2 tests (route priority, empty-fallback). 52 → 54, all green.

## Phase 9 — Custom routes via source-tree dev mode (2026-08-06 early)

User pushed back: *"没有的路由你可以自己补充进去所需路由，不要只用已有路由！"* and *"直接用docker镜像，通过接口添加自定义路由就可以，你在做什么？你不调研rsshub docker用法？"* — both correct. Systematic investigation of the RSSHub source tree (`rsshub-src`, 49M) revealed **three** route mechanisms, only one of which (prod build) the official Docker image exposes:

| Mechanism | How | Source evidence |
|---|---|---|
| ① routes-dir dynamic load (**dev mode**) | drop route files in `lib/routes/`, **tsx watch auto-reloads — no rebuild** | `registry-dev.ts` runtime `fs.readdirSync(routesDirectory)`; `registry.ts:59` dev branch |
| ② `registerRoute` API (**npm package**) | `init()` + `registerRoute(namespace, route)` — programmatic, runtime | `lib/pkg.ts:40`, official test `pkg.test.ts:89` |
| ③ build-time scan (**prod / Docker image**) | `lib/routes/` compiled into dist by `build-routes.ts` | `build-routes.ts`; Dockerfile `rm -rf /app/lib` |

The official Docker image ships **only ③** (`dist/`, `lib/` deleted, `index.mjs` exports just `default`); `registerRoute` lives in the **npm package** (`package.json` `exports["."]` → `dist-lib/pkg.mjs`, entry `./lib/pkg.ts`).

**Decision (user "按A落地验证"): source-tree dev mode.** `pnpm install` (830M dev deps) + `PORT=1201 pnpm dev` — NODE_ENV=dev dynamically loads routes. Wrote **2 custom routes**:

- `/cnsa/news` — CNSA English news list (`li.ej_cont_li > a`, filter `/content.html`) — **the P3 China-space gap, filled**
- `/esa/newsroom` — ESA press releases (`div.grid-item.press-release`, `data-date` → pubDate)

E2E verified on the live dev instance: CNSA 8 items, ESA 5 items with dates, OpenAI/Anthropic 8 items each still served. Found and fixed a real bug: CNSA links lost `/english/` prefix (relative `../../` resolved against `/english/` instead of the list page) — `new URL(href, listUrl)` fixes it.

Persistence: `~/news/rsshub-dev/start.sh` (idempotent, healthcheck) + crontab `@reboot`. Docker container (1200, built-in routes only) retired in favour of the single dev instance (1201, all routes). sources.json `rsshub` fields for CNSA/ESA; `RSSHUB_BASE` → 1201. 54/54 green.
