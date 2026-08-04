---
name: flytie-subagent-orchestration
description: >-
  How to run flytie's multi-agent review machinery from an agent session (Codex
  Code / Cowork) using the Agent/Task tool to spawn contextless subagents. Use
  when running the end-of-phase three-reviewer pass, running an end-of-version
  hardening audit (dual- or triple-lens), composing a reviewer brief, triaging
  reviewer findings, deciding parallel vs serial reviewer execution, or picking
  the model tier for reviewer subagents. Teaches the whole orchestration loop
  from zero; embeds the complete brief templates, persona library, and lens
  library so it is self-sufficient.
---

# flytie subagent orchestration

This skill teaches flytie's signature review methodology from zero. If you have
never run a multi-agent review, start here and copy the templates verbatim.

**What "subagent" means here.** From an agent session (Codex / Cowork) you
have an **Agent/Task tool** that spawns a fresh, *contextless* subagent: it sees
none of your conversation, only the brief you hand it and the files on disk. That
contextlessness is the whole point — an independent reader arrives at findings
from a different path than you did, so agreement between two of them is real
signal, not echo. Everywhere below, "spawn a reviewer" means one Agent/Task call
with the brief as its prompt.

Replace `<absolute path to your clone's project root>` in every template with the
real path to your flytie checkout.

## When NOT to use this skill

- Deciding **whether** a change even needs review, and which change class it falls
  in → `flytie-change-control`. This skill assumes review is already required and
  teaches *how* to run it.
- Writing the paired regression tests that accepted findings demand →
  `flytie-validation-and-qa` (naming conventions, evidence standards).
- Recording a triaged false alarm so a future audit does not re-raise it →
  `flytie-failure-archaeology`.
- The cost rationale behind Sonnet-tier reviewers → `flytie-token-economics-campaign`.
- Debugging a live bug (not reviewing a change) → `flytie-debugging-playbook`.

**Review is never optional for feature work.** A feature phase requires the
three-reviewer pass; a hardening pass requires the multi-lens audit. No workflow,
skill, or shortcut routes around this.

## 1. Why this exists

Independent contextless reviewers converging on the same finding is the project's
strongest priority signal — when two agents who never saw each other's work flag
the same issue, it is almost always the real top bug. This pattern has caught
every headline bug in the project's history. When only one reviewer catches
something, the skeptic persona is usually the one who does, which is why it is
always present.

Evidence (verified against `collaboration-retrospective/phases.md` and
`ai-development-practices/assessment.md`):

- **Phase 1** — both reviewers independently caught that `flytie init` used
  `Base.metadata.create_all` and never stamped Alembic; any later migration would
  have re-run the initial migration and failed. Convergence → correctly triaged
  as top priority.
- **Phase 5** — the skeptic caught the swallowed-streaming bug (the orchestrator
  exposed an `on_chunk` callback the CLI never wired up, so "streaming" was a
  static spinner). Skeptic-only catch.
- **Phase 6** — the skeptic caught the CRITICAL `flytie init` stamped-but-empty
  DB (Alembic stamps `head` before DDL runs; an interrupted init leaves the stamp
  set but tables absent, so every later command dies on `no such table: patterns`).

## 2. The two review shapes

| | Per-phase three-reviewer pass | End-of-version multi-lens audit |
|---|---|---|
| **When** | End of every feature phase | End of every hardening pass (version cycle) |
| **Count** | Exactly 3 subagents | 2–3 subagents |
| **Composition** | Skeptic (always) + 2 rotating specialists | Orthogonal lenses (spec-drift, contributor-friction, CI-as-contract) |
| **Independence** | Never told they are one of three | Each lens is self-contained |
| **Execution** | Parallel by default (serial if briefs overlap) | Parallel (lenses are orthogonal by design) |
| **What it catches** | Per-feature bugs in the new surface | Cross-cutting drift accumulated across a release |
| **After** | Fix findings → paired regression tests → phase summary | Rank findings → user picks impact-ranked slices → fix → tag |

### 2a. Per-phase three-reviewer pass — procedure

1. **Confirm scope with the user** and identify what the phase touched (files
   added/modified).
2. **Pre-flight sandbox integrity check** (see §5). Verify every file the briefs
   name actually exists in the world the reviewers will inspect.
3. **Pick the slate:** the skeptic is always one of the three. Choose the other
   two from the persona library (§4) by what was *new* in the phase. Do not repeat
   specialists across consecutive phases unless the surface genuinely needs it.
4. **Compose three briefs** from the template (§4), inserting the persona text at
   `{persona}`. Fill `{files-to-review}` and the out-of-scope list per phase.
5. **Spawn three contextless subagents** (Agent/Task tool), one brief each, on
   Sonnet (§8). Do **not** tell any of them they are one of three — independence is
   the value.
6. **Triage every finding** (§6). Fix each accepted CRITICAL/HIGH/MEDIUM with a
   paired regression test (§7).
7. **Write the phase summary** (`phase-summaries/phase-N.md` or `phase-x-y.md`)
   per `flytie-docs-and-writing`.

### 2b. End-of-version multi-lens audit — procedure

1. **Confirm the release scope** — what shipped since the last audit. A hardening
   audit can cover two adjacent releases if each already had its own three-reviewer
   pass.
2. **Pre-flight sandbox integrity check** (§5).
3. **Pick 2–3 orthogonal lenses** (§4 lens library). v0.1.1 and v0.1.2 used
   spec-drift + contributor-friction; v0.2.1 added CI-as-contract as a third when
   the CI/release surface had grown enough to drift on its own.
4. **Compose one brief per lens** from the audit template (§4).
5. **Spawn them in parallel** (lenses are orthogonal, so they cannot tread on each
   other), on Sonnet.
6. **Triage** (§6), then **rank findings by severity** and report them back to the
   user, explicitly naming false alarms and why.
7. **User picks impact-ranked slices** (see `flytie-validation-and-qa` /
   `flytie-docs-and-writing` for the slice cadence). Execute a slice, report at the
   boundary, let the user pick the next. Fix each accepted finding with a paired
   regression test. Tag and release at the end.

## 3. Parallel vs serial — the rule

Embed this logic verbatim:

> **Parallel when the briefs are orthogonal** (different surfaces — one reads
> docs and runs commands, another reads spec and greps code; they cannot tread on
> each other). **Serial-with-checkpoints when they are complementary on the same
> surface** (each reviewer builds on the previous). In serial mode the human reads
> each report before the next reviewer starts, which enables mid-flight brief
> expansion.

Worked examples (verified):

- **v0.1.1 dual-lens audit** ran **parallel** — spec-drift reads spec/greps code,
  friction-log runs the CLI; orthogonal, so concurrent and cheaper on wall clock.
- **Phase 6 three-reviewer pass** ran **serial-with-checkpoints** — the briefs
  overlapped on the same surface and the user wanted to react between reports. The
  user expanded reviewer 3's brief mid-flight to add a **meta-review** of the first
  two (does the CRITICAL reproduce? do the HIGH findings hold up?). That mid-flight
  expansion is only possible in serial mode.

## 4. The full brief templates

Both are Sonnet-tier by default (§8). Fill the placeholders; do not rewrite the
boilerplate — the fixed bones (cold-start framing, severity rubric, output format,
length cap) did not change across six phases plus two hardening passes.

### 4a. Per-phase three-reviewer brief

Spawn **three**; one is always the skeptic; the other two rotate from the persona
library by what was new in the phase. Brief each separately with the persona text
at `{persona}`; do not let them know they are one of three.

```
You are reviewing the implementation of {phase-N-name} in the flytie project (a
Python CLI for fly-tying patterns). You start cold — no context from prior
conversations. Your only inputs are the files on disk.

**Project root:** <absolute path to your clone's project root>

**Your role:** {persona}

**Your goal:** Review the implementation listed in "Files to focus on" and produce
a punch list of findings ranked by severity. Be specific. A "finding" is a
concrete issue (bug, design flaw, missing edge case, inconsistency, doc gap), not
a stylistic observation.

**Files to focus on:**
{files-to-review — list specific paths added or modified in this phase, plus a
1-line summary of what changed in each}

**Out of scope — don't flag these:**
{already-deferred — items deliberately deferred to a later release, items
previously triaged in earlier phases, items the user has already declined to fix;
name each with one-line reason so the reviewer doesn't waste tokens re-raising
them}

**Severity rubric:**
- CRITICAL: would mislead a user or break a contract the project promises.
- HIGH: would confuse a contributor or cause an inconsistent install.
- MEDIUM: real issue but bounded impact (stale doc, missing edge-case test, low-
  severity edge case).
- LOW: cosmetic or nice-to-have.

**Output format:** A punch list grouped by severity. For each finding: one line
for the issue, then a "Spec/doc says:" or "Code does:" pair with file:line
citations as appropriate. Skip preamble, skip recommendations, skip a summary at
the end — just the punch list.

**Hard limit:** under 500 words total. If you find more than fits, list the most
severe findings first and end with "(N more LOW findings omitted)".
```

### 4b. End-of-version multi-lens audit brief

Spawn **two or three** in parallel, one lens each. Insert the lens name, goal, and
checks from the lens library (§4d).

```
You are auditing the flytie project (a Python CLI for fly-tying patterns) for
**{lens-name}** at the end of the {version-name} release cycle. You start cold —
no context from prior conversations. Your only inputs are the files on disk.

**Project root:** <absolute path to your clone's project root>

**Goal:** {lens-goal — see Lens library below}

**What {version-name} set out to do (so you know where to look):**
{recent-changes — bullet list of major changes in this release with the
batches/phases that produced them}

**Files to focus on (read these):**
{files-to-review — specific paths the changes touched, plus the affected spec
sections and doc paths}

**What to look for specifically:**
{lens-checks — see Lens library; the 5–10 specific things this lens should catch}

**Severity rubric:**
- CRITICAL: would mislead a user or break a contract the project promises.
- HIGH: would confuse a contributor or cause an inconsistent install.
- MEDIUM: stale text or moderate inconsistency that won't break anything.
- LOW: cosmetic or nice-to-have.

**Output format:** A punch list grouped by severity. For each finding, give one
line for the issue, then a "Spec/doc says:" quote (with file:line) and a
"Reality:" quote (with file:line). For friction-style lenses use "What I tried /
What happened / Suggested fix" format. Skip preamble, skip recommendations, skip a
summary at the end — just the punch list.

**Hard limit:** under 500 words total. If you find more than fits, list the most
severe findings first and end with "(N more LOW findings omitted)".
```

### 4c. Persona library (for the three-reviewer brief)

The **skeptical senior engineer is a constant** — always one of the three. The
other five rotate by what the phase touched.

| Persona | Focus surface | Look for |
|---|---|---|
| **Skeptical senior engineer** (constant) | The whole implementation | See full text below |
| **Packaging / distribution** | `pyproject.toml`, `.github/workflows/`, install paths, extras, native libs | install breakage, missing wheel inclusions, mismatched pins, native-dep footguns (macOS/Linux Pango), tag-vs-version gaps |
| **Testing / CI** | `tests/`, pytest config, CI invocation, coverage, pre-commit hooks | tests that pass by accident, missing edge-case coverage, terminal-width/env/path fragility, CI invariants local runs don't enforce, coverage gaps |
| **LLM / API integration** | `src/flytie/ai/` | env-only key handling, prompt safety (what fields get sent), streaming correctness, error mapping, parsing robustness, model-version assumptions |
| **Data integrity** | `db.py`, `models.py`, `migrations/`, `core/portability.py` | transactional gaps, init/migration races, import/export round-trip fidelity, schema-validation edges, FK enforcement, soft-delete contracts |
| **UX / CLI surface** | `cli.py`, help text, error messages, exit codes | cryptic errors, missing `--help` context for selectors, doc-vs-CLI contradictions, exit-code consistency, fat-finger recovery |

Full persona text (insert one at `{persona}`):

- **Skeptical senior engineer** (constant). Posture: assume the implementation is
  incomplete somewhere. Look for: design flaws masked by passing tests, missing
  edge cases the test suite doesn't cover, abstractions that leak in ways the
  developer hasn't noticed, places where the code passes the spec literally but
  misses the intent, unhandled error paths, naming that will confuse a future
  reader. Push back on confident-looking code that hasn't been stress-tested.
  *Track record:* caught the streaming-swallowed-by-spinner bug in Phase 5 and the
  `flytie init` stamped-but-empty DB CRITICAL in Phase 6.
- **Packaging / distribution specialist.** Focus: `pyproject.toml`,
  `.github/workflows/`, CI configuration, install paths, extras dependencies,
  native-library requirements, version pinning. Look for: install breakage on
  common platforms, missing wheel inclusions, mismatched version pins,
  native-dependency footguns (macOS Pango, libpango on Linux), tag-vs-version
  assertion gaps. *Track record:* Phase 4 missed libpango; Phase 6 caught a
  wheel-inclusion gap for bundled migrations.
- **Testing / CI specialist.** Focus: `tests/`, pytest config in `pyproject.toml`,
  CI test invocation, coverage configuration, pre-commit hooks. Look for: tests
  that pass by accident, missing edge-case coverage, test fragility (terminal
  width, environment variables, file paths), CI invariants that local invocations
  don't enforce, coverage gaps in critical code paths. *Track record:* v0.1.2
  dual-lens audit found the release.yml missing-`--cov` CRITICAL.
- **LLM / API integration specialist.** Focus: `src/flytie/ai/`. Look for: API key
  handling (env-only, never persisted), prompt safety (what fields get sent),
  streaming correctness (chunks not swallowed), error mapping (network/auth/quota
  each surface cleanly), parsing robustness (JSON boundaries, truncation
  detection), model-version assumptions. *Track record:* Phase 5 streaming +
  truncation bugs.
- **Data integrity specialist.** Focus: `src/flytie/db.py`, `models.py`,
  `migrations/`, `core/portability.py`. Look for: transactional gaps, race
  conditions in init/migration, import/export round-trip fidelity, schema
  validation edge cases, foreign-key enforcement, soft-delete contracts.
  *Track record:* Phase 6 CRITICAL on `flytie init` stamped-but-empty DB; v0.1.1
  Alembic head-check gap.
- **UX / CLI surface specialist.** Focus: `src/flytie/cli.py`, help text, error
  messages, exit codes, command discoverability. Look for: cryptic errors (the
  `--hook is required when --from-file is not supplied` example), missing `--help`
  context for selectors, contradictions between docs and CLI behavior, exit-code
  consistency, fat-finger recovery gaps. *Track record:* v0.1.1 friction log
  surfaced most of the surface-level UX issues that became the §B and §D12 fixes.

### 4d. Lens library (for the multi-lens audit brief)

- **Spec-drift lens.** Goal: find places where the spec / changelog / docs claim
  one thing but the code, tests, CI, or configuration deliver something else. A
  "finding" is a concrete mismatch between a claim and reality, not a stylistic
  observation.
  Lens checks: (1) spec claims unmatched by code or vice versa; (2) CHANGELOG
  `[X.Y.Z]` section vs reality; (3) doc drift (stale tool mentions, dead links,
  outdated paths in README / CONTRIBUTING); (4) CI vs config drift (`ci.yml` vs
  `release.yml`, `.pre-commit-config.yaml` stages vs what CONTRIBUTING says);
  (5) version-bump status (`__version__` matches expected new tag).
- **Contributor-friction lens.** Goal: simulate a prospective contributor who just
  cloned the repo for the first time and wants to (a) get the test suite green
  locally, (b) make a one-line change, (c) push it through pre-commit, pre-push,
  and CI without surprises.
  Lens checks: (1) missing setup step in docs; (2) conflicting instructions
  between CONTRIBUTING and pyproject; (3) native-dependency footguns (WeasyPrint
  Pango/Cairo); (4) smoke-vs-full-suite discoverability; (5) pre-commit.ci
  semantics; (6) hook bypass appropriateness; (7) ruff isort `known-third-party`
  requirement for new deps; (8) `pre-commit run --all-files` vs CI gap;
  (9) coverage-gate recovery path.
- **CI-as-contract lens.** Goal: treat each CI workflow as a contract — what each
  workflow's name/description/trigger conditions promise vs. what it actually runs.
  Catches drift between PR and release paths the project may not notice otherwise.
  Lens checks: (1) does each workflow install the extras its tests need; (2) are
  the same gates enforced on PR and release paths (`ci.yml` runs X but
  `release.yml` doesn't = drift); (3) version-bump assertion correctly fails fast
  on mismatched tags; (4) secrets / env vars / OIDC trust-publishing configured
  identically across workflows that need them; (5) matrix Python versions
  consistent; (6) any workflows missing `name:` or with stale `name:` values.

## 5. Briefing discipline

Brief a reviewer **like a smart colleague who walked in cold**: state the goal,
hand over the exact file paths, define the severity rubric, cap the length. Do not
ask them to synthesize — that is your job after they report.

**Heavy out-of-scope section.** Name every item already deferred to a later
release and every item already triaged in earlier phases, each with a one-line
reason. Why it matters both ways: without it, reviewers waste tokens re-raising
known deferrals, *and* you waste triage cycles dismissing them. This is the
"reviewer's sandbox isn't faithful" lesson applied at the briefing stage — tell
them what is not real work up front.

**Pre-flight sandbox integrity check — do this before every spawn.** Verify that
the world the reviewer will inspect contains every file the brief names. A
five-second `ls`/`find` prevents an entire round of wasted triage. The Phase 6
incident is the canonical case: a packaging reviewer "correctly" reported
`LICENSE`, `alembic.ini`, and a populated `docs/` as missing — three false
positives — because it was pointed at an incomplete `/tmp` copy that had only the
changed `.py` files synced into it. The reviewer was scrupulously accurate about
the world it was given; the world was not real. Check the world first.

## 6. Triage protocol (the step that makes reviews safe)

Every finding gets an explicit tag: **real CRITICAL / real HIGH / real MEDIUM /
real LOW / FALSE ALARM with named reason.** Reviewer findings are input to
judgment, not verdicts. Convergent findings across independent reviewers are the
highest-confidence class.

Two documented reviewer failure modes to check for:

- **(a) Confidently wrong about the outside world.** Phase 5: the LLM-integration
  reviewer flagged the model ID `Codex-sonnet-4-6` as non-existent and told you to
  change it. It was a knowledge-cutoff artifact — the reviewer's cutoff predated
  that model's release. **Verify any external-world claim** (current API versions,
  model IDs, library behavior, what is deprecated) **against current reality before
  actioning it.**
- **(b) Correctly wrong about an unfaithful sandbox.** Phase 6 (above): the report
  was accurate for the incomplete world the reviewer was handed, wrong for the real
  repo. The §5 pre-flight check is the prevention; triage against the *real*
  working tree is the catch.

Name every false alarm and its reason so a future audit does not re-raise it.

## 7. After triage

- **Every accepted CRITICAL/HIGH/MEDIUM gets a paired regression test** that fails
  before the fix and passes after. Naming conventions and file placement
  (`test_review_fixes_phase{N}.py` for per-phase, `test_v0_X_Y_fixes.py` for
  hardening passes; docstrings name the reviewer and severity) live in
  `flytie-validation-and-qa`. The contract: no shipped bug ever re-surfaces
  silently.
- **Record every false alarm** with its named reason → `flytie-failure-archaeology`,
  so future audits do not re-raise settled non-issues.
- **Write the phase summary or audit writeup** → `flytie-docs-and-writing`.

## 8. Model economics

**Sonnet-tier subagents are the adopted default for reviewer/audit briefs** —
adopted, not blind-benchmarked. Evidence (verified against `handoff.md` and
`assessment.md`):

- v0.1.2's dual-lens audit ran on Sonnet at roughly half the v0.1.1 (Opus) token
  cost with no quality loss *observed* — 7 real findings + 2 correctly-discarded
  false alarms. This is an impression from the run, not a controlled head-to-head;
  the controlled benchmark is open problem F6 in
  `flytie-research-methodology-and-frontier`.
- v0.2.0's three-reviewer pass ran on Sonnet successfully (1 CRITICAL + 2 HIGH +
  3 MEDIUM + 2 correctly-discarded false alarms).
- Sonnet reviewers were observed **self-correcting mid-review** (the skeptic and
  data-integrity specialist both downgraded their own findings after re-reading) —
  a signal previously only seen on Opus.

Each reviewer brief is self-contained (no conversation context needed), which is
exactly what makes the Sonnet tier safe. **Raise the tier only when convergence
quality matters more than cost.** Deeper economics → `flytie-token-economics-campaign`.

## 9. Non-reviewer subagents

Mechanical-edit briefs (a doc-split, batched anchor-edits) and drafting briefs (a
multi-paragraph doc insert) are **bespoke per use, not templated** — the two
review templates above are the only templated shapes. Rules that carry over from
reviewer briefing:

- Self-contained brief (the subagent starts cold).
- Exact anchor strings and exact destinations for every edit.
- An out-of-scope list.
- **Post-flight verification by the parent.** After any restructure that renames or
  moves files, the parent runs a project-wide `grep` for the old name — do not rely
  on the subagent's "all anchors matched" report. The doc-split incident is the
  proof: the subagent reported success (accurate for what it was asked), and a
  parent-side grep caught 4 leftover references it had never been asked about
  (`AGENTS.md:3`, `AGENTS.md:51`, `CONTRIBUTING.md:45`, `CONTRIBUTING.md:170-171`).

## Hard rules

- **Subagents never mutate git.** No commits, tags, or pushes from a subagent —
  those happen only in the top-level session.
- **Reviewers never see the implementation conversation.** Contextless is the
  point; independence is the value.
- **One persona is always the skeptic** in the three-reviewer pass.
- **Every accepted CRITICAL/HIGH/MEDIUM finding gets a paired regression test.**
- **Every false alarm gets a named reason**, recorded so a future audit does not
  re-raise it.
- **No live-API tests** — inject a fake streamer; never call the real Anthropic API
  from a test.
- **Feature phases require the three-reviewer pass; hardening passes require the
  multi-lens audit.** No skill routes around this.

## Provenance and maintenance

- **Date:** 2026-07-02. **Project version:** flytie 0.2.1 (on PyPI).
- **Sources (all at project root, gitignored):** `subagent-brief-templates.md`
  (templates, persona library, lens library — embedded here in full);
  `ai-development-practices/patterns.md` §2.2, §2.9, §2.18, §2.22;
  `ai-development-practices/assessment.md` §3/§4 (reviewer failure modes);
  `collaboration-retrospective/phases.md` (incident details); `handoff.md`
  (model-economics evidence, project state).
- **Re-verification (run from your clone's project root):**
  - Templates in sync: `wc -l subagent-brief-templates.md` — if the line count has changed since this skill was last verified, re-read the file end to end and confirm §4 here still matches.
  - Persona/lens count: `grep -c '^\*\*' subagent-brief-templates.md` should show 6 personas + 3 lenses.
  - Incident claims: `grep -n "stamped-but-empty\|Codex-sonnet-4-6\|swallowed" collaboration-retrospective/phases.md ai-development-practices/assessment.md`.
  - Model-economics claims: `grep -n "Sonnet" handoff.md ai-development-practices/assessment.md`.
- **Maintenance note:** if `subagent-brief-templates.md` changes, update §4 here in
  the same pass — this skill embeds it so it stays useful in a fresh clone where
  that gitignored file is absent.
