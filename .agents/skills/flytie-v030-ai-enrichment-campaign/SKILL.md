---
name: flytie-v030-ai-enrichment-campaign
description: >-
  Executable, decision-gated campaign for shipping flytie v0.3.0 — the
  AI-layer enrichment release: `edit --from-suggestion`, semantic matching for
  `material dedupe --ai`, and `flytie material categorize`. Use when: starting
  v0.3.0 work; extending --from-suggestion to edit; adding AI pair-judgment to
  dedupe; building material categorization; writing any new Codex-API prompt
  for flytie; asked about the privacy boundary for new AI features. Contains a
  verified reuse inventory of the existing AI infrastructure, per-phase specs
  with settled semantics, maintainer decision gates, and fenced wrong paths.
  No schema migrations anywhere in this release. NOT for v0.4.0 inventory work
  (see flytie-v040-inventory-campaign) or generic AI-integration advice.
---

# flytie v0.3.0 campaign — AI-layer enrichment

Authored 2026-07-04 by the outgoing principal session from live code recon at
v0.2.1 `main`. **Status: planned, not started.** Three features, zero schema
migrations, all building on the v0.1.0/v0.2.1 AI infrastructure. Phases run
IN ORDER (1 → 2 → 3): Phase 2 creates the pair-prompt/parse machinery Phase 3
reuses.

---

## §0 — Reuse inventory (verified 2026-07-04; re-verify, then REUSE — don't rebuild)

All in `src/flytie/ai/suggest.py` unless noted:

| Asset | What it gives you | Re-verify |
|---|---|---|
| `Streamer` seam (`Callable[[str, str], Iterator[str]]`) | Tests inject fake streamers; NO live API in tests, ever (hard rule) | `grep -n "^Streamer" src/flytie/ai/suggest.py` |
| `anthropic_streamer(api_key, model)` | The ONLY place SDK errors are translated (401/403, 429, 529, connection, truncation via `stop_reason == "max_tokens"`, catch-all). Never duplicates key material into messages | `grep -n "_status_error_message\|stop_reason" src/flytie/ai/suggest.py` |
| `resolve_api_key()` | Env-only key with actionable error; never persisted/logged | `grep -n "ANTHROPIC_API_KEY" src/flytie/ai/suggest.py` |
| `DEFAULT_MODEL` constant | Single bump point (volatile — verify against current Anthropic docs, not a reviewer's memory; see flytie-failure-archaeology) | `grep -n "DEFAULT_MODEL" src/flytie/ai/suggest.py` |
| `_extract_json_array` | String-literal-aware array extraction (survives `]` inside rationale strings, code fences) | it is private — see Gate 0 below |
| `_clean_str` | JSON null → `""` (never the literal "None" in the CLI) | same |
| `core/suggestions.py` | `last_suggestions.json` persistence, 1-based `get_suggestion`, atomic writes, typed errors | `grep -n "SUGGESTIONS_FILENAME" src/flytie/core/suggestions.py` |
| `core/dedupe.py` | `combined_similarity = max(levenshtein_ratio, jaccard_similarity)`; `find_duplicate_candidates(threshold=0.6)`; `DupeCandidate` | `grep -n "combined_similarity\|threshold" src/flytie/core/dedupe.py` |

**GATE 0 (small, do first):** `_extract_json_array` and `_clean_str` are
private to suggest.py but Phases 2–3 need them. Promote them to a shared home
(`src/flytie/ai/parsing.py`, public names) with suggest.py re-importing —
one commit, before any feature code. Mirrors the §3 units-extraction move in
the v0.4.0 campaign; same circular-import rationale.

**Privacy doctrine for ALL new prompts (non-negotiable, canon):** each new
prompt builder is a NEW privacy boundary and gets the same treatment as
`build_prompt`: only material names + categories cross the wire for Phases
2–3 — no quantities, no pattern names, no notes, no counts-per-pattern. Every
new builder gets a paired privacy test in the shape of the existing
`test_grounding_block_excludes_instructions_and_notes`. Adding ANY other
field to a prompt requires explicit maintainer privacy review first.

**Reuse rule for the transport:** Phases 2–3 responses are short; you do not
need streaming UX — but reuse the `Streamer` seam anyway (buffer the chunks).
One error-translation path, one fake-streamer test pattern, zero new SDK
touchpoints. Building a second non-streaming client wrapper is a fenced
wrong path.

---

## Phase 1 — `flytie edit --from-suggestion <n>` (scope: light)

Port the v0.2.1 `add --from-suggestion` affordance to `edit`. Settled
semantics (roadmap + maintainer, 2026-07-04):

- **Merge-and-skip, materials only.** Suggestion materials not already on the
  pattern (matched by canonical name via `normalize_name`) are ADDED —
  exactly as `add --from-suggestion` builds them: category `"other"`,
  quantity `None`, no unit (verified: cli.py builds draft materials with
  name+category only; there are NO quantity defaults — don't invent them).
  Matches are SKIPPED. Hook size, instructions, notes: untouched unless the
  user passes the normal `edit` flags alongside.
- A printed summary always shows added vs skipped, by name.
- The draft notice is a CONSOLE PRINT ONLY in `add --from-suggestion`
  (verified: nothing is persisted to notes or any DB field). Phase 1 prints
  the same style of notice; do NOT write it into the version unless the
  maintainer explicitly asks for persistence.
- **GATE P1 (maintainer): all-skip behavior.** If every suggested material is
  already present (and no other edit flags were passed), does `edit` still
  create a new version? Recommendation: NO — print "nothing to merge; no new
  version created", exit 0. A no-op version pollutes history. **DECIDED
  2026-07-04 by the maintainer: NO new version on all-skip.** Implement as
  recommended; paired test pins it. **Implementation location (reviewer
  finding, verified): `edit_pattern` in core/patterns.py ALWAYS creates a new
  version — there is no no-op path inside it. The all-skip guard is an early
  return in the CLI `edit` command, BEFORE the `edit_pattern` call, taken
  when the merge helper reports nothing-to-add AND no other edit flags were
  passed. Do not put the guard inside `edit_pattern`.**
- Files: `cli.py` (edit command), `core/suggestions.py` (merge-and-skip
  helper — pure function, unit-tested), `tests/test_suggestions.py` (skip
  behavior, all-skip, empty-materials suggestion, draft-notice carryover,
  hook preserved, flags layer on top — that last one re-walks the Phase 2
  `--from-file` flag-layering bug; don't repeat it — plus the staleness
  race: `suggest` → `suggest` again → `edit --from-suggestion 1` now points
  at the SECOND run's suggestion #1; only the last run is kept. Test the
  sequence and make the summary print the suggestion name so the user sees
  what they merged), `docs/commands.md` AND
  `docs/ai-suggestions.md` (the topical guide went stale once before —
  recorded lesson; update both, add docs-content smoke tests).
- Expected gate: suite green; new tests fail against pre-change code
  (regression discipline); no new API calls anywhere in this phase (it only
  reads `last_suggestions.json`).

---

## Phase 2 — `flytie material dedupe --ai` (scope: light–medium)

Fuzzy scoring runs first, exactly as today. `--ai` adds a semantic-judgment
tier for pairs the string metrics can't decide ("CDC feather" vs "cul de
canard" shares no characters — the motivating example).

**Measure BEFORE wiring (numbers-predicted-first, canon):** the candidate
space is O(n²). Build a ~100-material synthetic library in a test and COUNT
pairs passing the proposed floor before touching the API path. Expected
observation: at floor 0.3 on `combined_similarity`, pair counts can reach
the hundreds+ — which is why the cap exists. If your measured count at the
floor is small (<40) even at 200 materials, record the numbers and simplify.

Settled design — **DECIDED 2026-07-04 by the maintainer: ratified exactly as specified below** (floor 0.3, cap 40, one batched call, fuzzy-only fallback):
- **Floor mechanics (be literal about this):** `find_duplicate_candidates`
  returns only pairs AT OR ABOVE the threshold you pass it. To get the AI
  band you must call it once at `threshold=FLOOR` (0.3) and PARTITION the
  result: pairs `>= user_threshold` (default 0.6) → the normal interactive
  flow, no API; pairs in `[0.3, user_threshold)` → the AI-judgment tier.
  Calling it at the default and expecting a 0.3 band yields an AI tier that
  never fires — the silent-failure shape a reviewer explicitly flagged.
- **Cap:** send at most the top-K eligible pairs by score (K = 40 to start —
  a constant, documented, tunable). If more were eligible, say so:
  "N additional low-similarity pairs not sent; re-run after merging".
- **One batched call**, not per-pair: JSON array in → JSON array out
  (`[{"a": ..., "b": ..., "verdict": "yes|no|uncertain", "rationale": ...}]`),
  parsed with the promoted `extract_json_array`. Verdicts outside the enum →
  treated as `uncertain`. Parse failure of the whole response → warn, fall
  back to fuzzy-only flow (never crash the interactive session; the fuzzy
  path must remain fully usable without the flag, without the [ai] extra,
  and without a key).
- **Presentation (DECIDED 2026-07-04: labeled, never preselected — applies
  to Phase 3's accept/reject flow too):** AI-sourced candidates enter the
  SAME interactive flow, labeled by origin — `[AI: likely]` for yes, `[AI: uncertain]` for
  uncertain (shown, never preselected). Rich markup escape: write the
  labels as raw strings with escaped brackets — `r"\[AI: likely]"`,
  `r"\[AI: uncertain]"` — or Rich eats them as markup (the Phase 5 badge
  lesson; render.py's `\[NEW]` badge is the in-repo precedent).
- New file `src/flytie/ai/material_match.py`: prompt builder (names +
  categories ONLY) + response parser, both pure; orchestrator reusing the
  Streamer seam. New `tests/test_material_match.py`: fake streamer, prompt
  privacy test, enum coercion, parse-failure fallback, cap behavior,
  floor boundary. `tests/test_dedupe.py` gains the integrated-flow cases.
- CLI: `--ai` on `material dedupe`; requires [ai] extra + key ONLY when
  passed (lazy import stays lazy; cold-start gate). **Ctrl-C: dedupe's
  interactive loop has NO KeyboardInterrupt handler today (verified) — an
  interrupt currently escapes as a traceback. Add a handler around the new
  `--ai` API-call block that exits 130 with a clean message, mirroring the
  pattern in the `suggest` command (the only place it exists); fixing the
  bare interactive loop's Ctrl-C is optional scope — if you touch it, pair
  a test.**
- Docs: `commands.md` + `ai-suggestions.md` + smoke tests.

---

## Phase 3 — `flytie material categorize` (scope: light–medium)

Batch re-categorization of `other`-category materials. Settled by roadmap:
batch command only — `suggest` remains the only command that calls the API
during normal pattern workflows; users opt in explicitly.

- One batched call: all `other` materials (names + current category only).
  Response schema: `[{"name": ..., "category": ...}]`.
- **Whitelist validation is mandatory:** any suggested category not in
  `MATERIAL_CATEGORIES` (13 entries, `src/flytie/models.py`) is dropped with
  a per-item warning — the model WILL occasionally invent categories; the
  application-level validation that guards `add`/`edit` guards this too.
  Names in the response that don't match any local material: ignored.
- Interactive accept/reject per material (same UX shape as dedupe's flow,
  including `s`/`q` shortcuts — their only "documentation" is dedupe's
  prompt string in cli.py, `[1/2/skip(s)/quit(q)]`; grep for it and mirror
  exactly); accepted
  changes written immediately; `--dry-run` prints the proposal table and
  writes nothing.
- Empty `other` set: exit 0 with a friendly message BEFORE any API call.
- New `src/flytie/ai/categorize.py` (reuses Phase 2's parsing/transport
  patterns), `tests/test_categorize.py` (fake streamer, whitelist rejection,
  unknown-name handling, dry-run writes nothing, empty-set no-API-call,
  interactive accept/reject/quit), CLI subcommand, docs pair + smoke tests.

---

## Reviews, hardening, release (per change-control — non-negotiable)

- **Three-reviewer pass over all three phases together** (bundling
  precondition holds: the phases share the AI layer by design, so run the
  reviews AFTER all three land, briefing reviewers on the full surface):
  skeptic (standing) + **AI/prompt-engineering specialist** (prompt
  templates, privacy boundaries, parse edge cases, enum coercion) + UX/CLI
  specialist (interactive flows, AI-origin labeling, merge-and-skip
  legibility). Briefs from `subagent-brief-templates.md` or the embedded
  templates in `flytie-subagent-orchestration`. Reviewer out-of-scope list:
  semantic-match QUALITY (no live API in tests — quality is a post-release
  user observation), unit conversion, v0.4.0 inventory.
- Every accepted CRITICAL/HIGH/MEDIUM finding → paired regression test.
  Phase summary at `phase-summaries/phase-3-1.md` (X-Y naming).
- **Triple-lens hardening audit** (spec-drift: backport §6 history + FR-6
  extensions; contributor-friction; CI-as-contract), fixes paired, then the
  standard release runbook. Version bump to 0.3.0, CHANGELOG, README.
- Gates green throughout: full suite at COLUMNS=80, coverage ≥85 untouched,
  smoke exactly 5, cold-start <600ms (anthropic must stay lazy — three new
  AI files make top-level imports tempting; don't).

---

## Fenced wrong paths

- **A second SDK wrapper / non-streaming client path** — reuse the Streamer
  seam and `anthropic_streamer`; one error-translation ladder.
- **Anything beyond names+categories in Phase 2/3 prompts** — new privacy
  boundary, maintainer review required; the paired privacy test is not
  optional.
- **Unbounded pair sends** — O(n²) at a 0.3 floor without the cap is a
  token-cost and latency footgun; measure first, cap always.
- **Trusting model-emitted categories without the whitelist** — validation
  exists at add/edit for exactly this class of input.
- **Touching `build_prompt` for these features** — separate builders;
  build_prompt is suggest's boundary and its privacy test pins it.
- **Live API calls in any test** — fake streamers only (ratified hard-never).
- **Updating `commands.md` but not `ai-suggestions.md`** — the recorded
  docs-drift lesson; both, with smoke tests, every phase.
- **Editing the saved-suggestions JSON format incompatibly** — `add
  --from-suggestion` (v0.2.1) reads it; Phase 1 only ADDS a consumer.

## When NOT to use this skill

v0.4.0 inventory/migration work → `flytie-v040-inventory-campaign`. Review
mechanics → `flytie-subagent-orchestration`. Test conventions →
`flytie-validation-and-qa`. AI-layer architecture background →
`flytie-architecture-contract` (Streamer seam + privacy boundary sections).
Release mechanics → `flytie-run-and-operate`.

## Provenance and maintenance

Authored 2026-07-04 from direct recon of `src/flytie/ai/suggest.py`,
`core/suggestions.py`, `core/dedupe.py`, `cli.py`, `models.py`, the roadmap's
v0.3.0 section, and the v0.2.1 phase records. Re-verification greps are
inline in §0. `DEFAULT_MODEL` is the one fact here most likely to drift —
check it against current Anthropic model docs at campaign start.

**Gate record (all ratified by the maintainer 2026-07-04, authoring
session):** GATE 0 promote-shared-parsers = standing instruction, do first;
P1 all-skip = no new version; P2 = floor 0.3 / cap 40 / single batched call /
fuzzy-only fallback; P2+P3 verdict presentation = labeled, never preselected,
uncertain always shown. The only in-flight judgment left is tuning the
floor/cap constants against the Phase 2 measurement step — tune within the
ratified shape and record what you measured. If execution produces evidence
against a ratified decision, stop and return to the maintainer.
