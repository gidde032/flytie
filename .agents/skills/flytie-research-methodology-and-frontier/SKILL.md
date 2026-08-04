---
name: flytie-research-methodology-and-frontier
description: >-
  The discipline that turns a hunch into an accepted result on flytie, plus the
  ranked inventory of open problems where this project can advance agentic-workflow
  methodology. Use when proposing a workflow experiment, evaluating whether a hunch
  is proven, picking an open problem to advance, deciding whether a candidate practice
  can be promoted to canon, or closing out an open question. Third person: consult this
  skill when someone wants to run a methodology experiment or pick up a frontier problem
  on this project.
---

# flytie research methodology and frontier

flytie's declared frontier ambition is the agentic-workflow **methodology itself**. The
project doubles as a laboratory: experiments ride real feature work and hardening passes,
results feed the practices catalogue and an article series. This skill is the runbook for
(a) the evidence bar a claim must clear to be accepted, (b) the lifecycle an idea travels
from hunch to canon, (c) where good ideas historically come from, and (d) the ranked
inventory of genuinely-open frontier problems and how to attack each one.

As of 2026-07-02, flytie is at v0.2.1 (six feature phases + hardening passes v0.1.1, v0.1.2,
v0.2.0, v0.2.1). Every fact below is grounded in the project's real record; open problems are
drawn from the open-questions (§8) and assessment (§6) records, not invented. Answered
questions are excluded. Unverifiable claims are marked UNVERIFIED.

---

## When NOT to use this skill

| If you are... | Use instead |
|---|---|
| Changing a workflow rule or gate | `flytie-change-control` (change classes, gates, sign-off) |
| Running a reviewer pass or composing briefs | `flytie-subagent-orchestration` (the machinery experiments run on) |
| Deciding a cost rule can be promoted | `flytie-token-economics-campaign` (owns cost-rule promotion) |
| Deciding what is publicly claimable | `flytie-article-and-positioning` (owns the claimable list) |
| Recording a result in a doc | `flytie-docs-and-writing` (owns WHERE results get recorded) |
| Setting evidence/QA standards for a fix | `flytie-validation-and-qa` (evidence standards) |
| Building a feature on the roadmap | That is roadmap work, **not** frontier research (see fence below) |

This skill is upstream of all of those: it decides **whether a hunch is proven** and **which
open problem is worth attacking next**. It does not itself run reviewers, edit gates, or write
docs — it routes to the siblings that do.

---

## 1. The evidence bar — when a workflow claim is accepted

A workflow claim is not accepted because it sounds right or because one reviewer asserted it.
It is accepted when it clears four tests. All four are grounded in real precedents on this project.

### (a) The mechanism explains ALL observations, including negatives

A claim is not settled until one mechanism accounts for every observation — especially the ones
that contradict the first guess.

> **Precedent — the ruff isort investigation (v0.1.2).** CI started failing on `I001`
> import-sorting errors that local `ruff check` could not reproduce, and local `ruff check --fix`
> would actively *revert* a CI-correct ordering on every run. The investigation did **not** stop at
> "CI is flaky." It found the one mechanism — ruff's isort heuristic classifying first-party vs.
> third-party packages differently across environments (sandbox treated `alembic` and
> `alembic.config` as one package and `flytie.*` as ambiguous; CI treated them differently) — that
> explained BOTH the CI failure AND the local `--fix` reverting it. The cure (explicit
> `[tool.ruff.lint.isort] known-first-party`/`known-third-party`) followed directly from the
> mechanism. A mechanism that explains only the positive observation is a coincidence; one that
> also explains the negative is a finding.

### (b) It survives adversarial checking — reviewer findings are inputs, not verdicts

A reviewer's finding is an *input to judgement*, verified against reality before being actioned.
This applies to factual claims as much as to opinions.

> **Precedent — the `Codex-sonnet-4-6` false alarm (Phase 5).** The LLM-integration reviewer
> flagged the model constant `Codex-sonnet-4-6` as a non-existent model ID and recommended
> changing it — a clear, specific, high-priority-sounding finding. It was wrong: the reviewer's
> knowledge cutoff predated the Sonnet 4.6 release, so it "knew" the ID could not exist. Triage
> caught it because triage exists as a deliberate layer between the reviewers and the code. The
> mirror lesson (Phase 6) is that a reviewer can be *correctly* wrong when the sandbox it inspected
> was not faithful (it reported `LICENSE`/`alembic.ini` missing from an incomplete `/tmp` copy).
> Both argue: keep a human-or-orchestrator triage layer that does not simply execute the review.

### (c) Predictions are stated as numbers BEFORE running, where possible

A falsifiable numeric prediction, declared before the run with its measurement method, is worth
more than a post-hoc narrative. This project already runs several as checked gates:

| Predicted quantity | Method (declared up front) | Where enforced |
|---|---|---|
| Cold-start budget | `flytie --version` best-of-5 under 600 ms | `tests/test_v0_1_2_fixes.py` (spec NFR §4, raised from 300 ms with rationale) |
| Smoke suite size | `pytest --collect-only -m smoke` == exactly 5 | `tests/test_v0_1_2_fixes.py` |
| Smoke suite speed | smoke suite finishes under 5 s | `tests/test_v0_1_2_fixes.py` |
| Coverage floor | measured coverage ≥ 85% against the omit-list | `pyproject.toml [tool.coverage.report] fail_under` |

The exact-count contract (==5, not ≥5) is the shape to imitate: it fails in both directions
(marker removed, or marker added to a slow test), which a lower-bound could not.

### (d) Convergence across independent contextless observers is the strongest confidence signal

When two or three contextless agents, arriving from independent paths, land on the same finding,
that is the highest-confidence signal the project produces. Convergence is strongest *across
different lenses* — a spec reader and a confused-user friction log converging on the same bug
(the `flytie config path` confusion in v0.1.1) is more trustworthy than two code reviewers agreeing.
Divergent findings broaden coverage; convergent findings rank priority.

**The bar, in one line:** a workflow claim is accepted when its mechanism explains the negatives,
it survives adversarial triage, its prediction was numeric and stated before the run, and (ideally)
independent observers converged on it.

---

## 2. The idea lifecycle — hunch to canon

This is how the project actually moves an idea. Do not skip stages; the record is the product.

```
hunch
  → recorded as a suggestion (assessment.md §6) or an open question (open-questions.md §8)
  → experiment run DURING a real phase or release (experiments ride real work)
  → result recorded with an "Answered (vX.Y.Z)" annotation on the §8/§6 entry
  → if adopted: a §2.N catalogue entry in patterns.md tagged [ADOPTED]
       + (if it is a session rule) a line in AGENTS.md
  → if superseded/failed: documented retirement, NEVER deleted (the article wants the evolution)
```

**Worked examples from the record — note how adoption can reshape the proposal:**

| Idea | Proposed as | Outcome | Reshaping |
|---|---|---|---|
| Specialist reviewer personas | suggestion (§6), fix for reviewer-prompt sameness | **[ADOPTED Phase 4+]**; skeptic persona carried every phase, others rotate | adopted roughly as proposed |
| Adversarial-user subagent | suggestion (§6), as a *third per-phase reviewer* | **[ADOPTED v0.1.1]** as the friction-lens of the dual-lens audit | adoption **reshaped** the proposal: it became one of two orthogonal end-of-version lenses, not a third per-phase reviewer, because orthogonal lenses run cheaper in parallel |
| Dual-lens audit on Sonnet | open question (cost) | **validated v0.1.2** — ran at ≈half the v0.1.1 cost, no measurable quality loss | confirmed by running |
| Narrative-doc split | open question (v0.1.2 §8) | **Answered (v0.2)** — net +5% lines, ~10x per-update read-cost reduction | confirmed by measurement, entry marked answered at consolidation |

The lifecycle is auditable because each stage leaves an artifact: the §8/§6 entry, the
"Answered (vX.Y.Z)" annotation, the `[ADOPTED]` §2.N catalogue entry, the AGENTS.md line. If an
idea cannot point to those artifacts, it has not completed the lifecycle — it is still a hunch.

---

## 3. Where good ideas have historically come from

Frontier ideas on this project do not come from one source. Watch these five, because the next
frontier item probably arrives the same way one of these did.

| Source | What it looks like | Worked example |
|---|---|---|
| Maintainer reshaping a plan mid-execution | Finn asks a "does it make sense to…" question that collapses two items into one better one | The three-tier gating model came from *"do you think it makes sense to do bullet 1.2 as a pre-commit hook and add ruff formatting into the hook as well?"* — the answer turned out richer than yes/no (pre-commit's stage system powers three latency tiers) |
| Reviewer reports | contextless reviewers surface findings the implementer missed | the Phase 6 CRITICAL `flytie init` stamped-but-empty DB bug (skeptic, then independently reproduced by the user) |
| Tooling incidents becoming practices | a workflow failure gets a post-mortem + prevention checklist | the FUSE deadlock post-mortem → the "ask the user to re-open the folder first" playbook |
| The user acting as fourth reviewer | Finn runs real commands on macOS and finds what a sandbox could not | Phase 4 libpango `OSError`; Phase 6 `--out` directory bug; the friction-log subagent is the deliberate synthetic proxy for this |
| Writing summaries surfaces half-formed views | drafting a phase summary or handoff forces synthesis and crystallizes a view the author did not know they held | spec deviations (TOML config vs. config-row table; Python 3.10 vs 3.11+) were only written down when the handoff doc forced them out |

Practical consequence: when a maintainer question, a reviewer report, or a summary-writing session
surfaces something new, **record it as a §8/§6 entry immediately** — that is the front door of the
lifecycle in §2.

---

## 4. Frontier inventory

Genuinely-open problems, drawn from the open-questions record (§8) and the candidate-practices
record (§6). Answered items are excluded. Each item has the same four-part structure:
**gap** (why current practice falls short) / **asset** (this project's specific lever) /
**first three steps in this repo** / **falsifiable milestone** (you have a result when…).

Ranked by leverage × feasibility. The top pick is justified after the table.

**Ranked index (leverage × feasibility):**

| ID | Title | Rank keyword |
|----|-------|--------------|
| **F1** | Structured reviewer return format (JSON findings) | **TOP PICK — unblocks F4/F6/F9/F10, no unbuilt deps** |
| F2 | Per-phase token budget with a tripwire | cost-governance, self-contained |
| F3 | Marker-as-contract generalized to other markers | contract-generalization |
| F4 | Four-reviewer scaling / diminishing-returns | reviewer-scaling, needs F1 |
| F5 | pending-lessons signal-filter hypothesis | process-signal |
| F6 | Sonnet-vs-Opus review-quality benchmark | the open head-to-head behind the Sonnet default |
| F7 | Codex-written vs. hand-written next-step handoff | handoff-quality |
| F8 | Coverage-headroom compression tracking | metric-drift |
| F9 | Rotate vs. reuse the hardening-audit lens pair | lens-strategy |
| F10 | Per-phase parallel-vs-serial reviewer rule as a checked choice | orchestration-rule |
| F11 | Three-tier gating: does each tier catch a different failure class? | gate-differentiation (re-ask) |
| F12 | Docs-content smoke tests: do they catch a real-world regression? | docs-smoke (open) |

**Why F1 leads:** high leverage (it unblocks or amplifies F4, F6, F9, F10 by making
cross-reviewer/cross-tier comparison programmatic), low cost (no feature work, no live
API calls — validated by replaying a past phase against the JSON schema), and no
dependency on anything unbuilt. The full justification follows the table.

### F1 — Structured reviewer return format (JSON findings)  ⟵ TOP PICK

- **Gap.** Reviewer reports come back as unstructured text; the orchestrator triages a wall of prose
  by hand into a fix list. Convergence detection (the strongest confidence signal, §1d) is done by
  eye. This does not scale and is not reproducible. (§6 "Structured subagent return format"; §4
  "Subagent reports are unstructured text.")
- **Asset.** 10+ recorded review passes exist to compare against: per-phase three-reviewer passes
  (Phases 1–6), the v0.1.1 dual-lens audit, the v0.1.2 Sonnet dual-lens audit, the v0.2.0 bundled
  three-reviewer pass, the v0.2.1 triple-lens audit. Their findings and manual triage outcomes are
  in the phase summaries and `test_review_fixes_*` / `test_v0_*_fixes` docstrings.
- **First three steps.** (1) Add a JSON return schema to the reviewer brief in
  `subagent-brief-templates.md`: `bugs: [{file, line, severity, summary, suggested_fix}]`,
  `suggestions`, `test_gaps`, `integration_risks`. (2) Run it on one *past* phase's file set as a
  replay (no new feature work needed) and collect structured output. (3) Write a small dedupe /
  convergence-detection pass over the JSON and compare its convergence set to that phase's
  hand-triaged convergent findings recorded in the phase summary.
- **Milestone.** You have a result when programmatic convergence detection over the JSON reproduces
  the manual triage on a past phase's reports — same convergent findings, same severity ranking — with
  zero hand-correction.

### F2 — Per-phase token budget with a tripwire

- **Gap.** Token budgeting is only **partially adopted**: from Phase 5 the user added an
  estimate-and-approve gate before expensive steps, and v0.1.1 extended it to the slice grain. But a
  *per-phase numeric budget with an automatic tripwire* is still hypothetical (§6 "Token budget per
  phase [PARTIALLY ADOPTED]").
- **Asset.** Recorded per-incident costs: Phase 3 ≈80k useful + 20k FUSE recovery; the v0.1.2
  dual-lens audit at ≈half the v0.1.1 cost; the doc-split subagent restructure at ≈117k tokens;
  reviewer passes at ≈50–60k per reviewer. Enough data points to set a defensible budget.
- **First three steps.** (1) From the recorded costs, declare a numeric budget for the next release's
  phase (e.g. implement ≤ X, three-reviewer pass ≤ Y). (2) Instrument the run to report actual token
  spend at each slice boundary against the declared budget. (3) Define the tripwire action (pause and
  ask the maintainer) when a slice exceeds its line item.
- **Milestone.** You have a result when a real release runs under a declared per-phase budget and the
  end-of-release report states actual vs. budgeted spend with the variance, and the tripwire either
  did or provably would have fired at the right point.

### F3 — Marker-as-contract generalized to other markers

- **Gap.** The exact-count + wall-clock contract exists only for `@pytest.mark.smoke`. Other
  semantically-meaningful markers (`slow`, `integration`, `network`, `requires_api_key`) are still
  "convention," not checked contracts (§8 "Could the marker-as-contract pattern be applied to other
  pytest markers"; §2.14).
- **Asset.** A proven, cheap template: one `pytest --collect-only -m X` subprocess assertion plus an
  optional budget test, already working for `smoke` in `test_v0_1_2_fixes.py`.
- **First three steps.** (1) Identify a marker category that has emerged (e.g. a `slow` PDF/render
  category, or a `network`/`requires_api_key` category for AI paths). (2) Tag the tests and add the
  paired `--collect-only -m X` count/composition assertion in the release's fixes file. (3) Add a
  budget assertion if the marker implies a runtime property (e.g. `slow` has a floor, a "quick" set
  has a ceiling).
- **Milestone.** You have a result when at least one non-smoke marker has a merged exact-count (or
  composition) regression test that fails in both directions, and the pattern's per-marker cost is
  recorded against the §8 hypothesis.

### F4 — Four-reviewer scaling / diminishing-returns measurement

- **Gap.** Three reviewers was confirmed to work and stay legible through Phase 6, "**but four wasn't
  tried**" (§8, answered-partial). Whether a fourth reviewer adds non-redundant findings or just cost
  is unmeasured.
- **Asset.** A stable three-reviewer baseline with recorded find-rates per phase, plus the reviewer-brief
  template and persona/lens libraries in `subagent-brief-templates.md` to compose a fourth brief cheaply.
- **First three steps.** (1) On the next bundled phase, run the standard three-reviewer pass and record
  its findings. (2) Add a fourth reviewer with a genuinely distinct persona/lens (not a fourth
  restatement) and record its findings separately. (3) Classify the fourth reviewer's findings as
  net-new vs. redundant with the first three.
- **Milestone.** You have a result when a phase's fourth-reviewer findings are classified net-new vs.
  redundant with a stated ratio, and that ratio supports a keep/drop recommendation recorded in §8.

### F5 — pending-lessons signal-filter hypothesis

- **Gap.** The hypothesis (§8, v0.2) is that the `pending-lessons.md` scratch file produces
  *higher-signal* lessons than writing them immediately, because marginal lessons do not survive the
  end-of-release "is this worth consolidating" filter. It is stated but not yet measured; v0.2.1 is
  the second release to accumulate entries and is called out as the "first data point."
- **Asset.** Two releases' worth of accumulated `pending-lessons.md` entries with a consolidation step
  that routes survivors to their destination docs.
- **First three steps.** (1) At the next consolidation, record the raw entry count in
  `pending-lessons.md` before routing. (2) Record how many entries survive routing to a destination
  doc vs. how many are dropped as too marginal. (3) Compare survivor count to entry count and note
  whether dropped entries would plausibly have been low-value if written immediately.
- **Milestone.** You have a result when entry-count-vs-survivor-count is reported for at least two
  releases and the survival ratio (plus a judgement on the dropped entries) confirms or refutes the
  higher-signal hypothesis.

### F6 — Sonnet-vs-Opus review-quality benchmark

- **Gap.** Sonnet reviewers are known to *work* (v0.1.2 dual-lens audit ran on Sonnet at ≈half cost,
  no measurable quality loss; v0.2.0 Sonnet reviewers even self-corrected mid-review). But there has
  been no *blind head-to-head*: same brief, both tiers, blind triage of the outputs. The "no
  measurable quality loss" claim rests on impression, not a controlled comparison. (§3/§6; token-economics notes.)
- **Asset.** Self-contained reviewer briefs (a reviewer needs no conversation context), the persona/lens
  library, and past phases whose findings are recorded — so a replay comparison is possible.
- **First three steps.** (1) Take one phase's reviewer brief verbatim and run it on both a Sonnet and an
  Opus reviewer against the same file set. (2) Strip tier labels from both reports. (3) Triage both
  blind against the phase's known-correct findings and score find-rate + false-alarm rate per tier.
- **Milestone.** You have a result when blind triage scores both tiers on the same brief and the
  find-rate / false-alarm delta is small enough (or not) to justify Sonnet-by-default, recorded as a
  cost-quality trade in the token-economics record.

### F7 — Would Codex-written next-step instructions outperform the maintainer's hand-written handoff?

- **Gap.** Recorded in §8 as **"Still untested."** The handoff's "Next step for the new agent" section
  is hand-written by the maintainer; whether an agent-authored next-step brief would onboard a fresh
  session better (or worse) has never been run.
- **Asset.** A mature `handoff.md` with a hand-written next-step section and a fresh-session-onboarding
  practice, plus the fresh-session cost being bounded (handoff + AGENTS.md).
- **First three steps.** (1) At a release boundary, have an agent draft its own "what the next agent
  should do" section from the same state the maintainer sees. (2) Keep the maintainer's hand-written
  version separately; do not merge them. (3) Start two fresh sessions cold, one on each next-step
  version, on the same first task, and compare warm-up cost + time-to-first-correct-action.
- **Milestone.** You have a result when two cold fresh-session onboardings — one on the agent-written
  next-step, one on the hand-written — are compared on warm-up cost and first-task correctness, with a
  recommendation recorded against the §8 entry. (Design note: keep the two sessions blind to which
  next-step they received where feasible.)

### F8 — Coverage-headroom compression tracking

- **Gap.** §8 (v0.1.2) asks whether the coverage gate's headroom (≈6 points above the 85% floor at
  v0.1.2) compresses over time as features land without commensurate tests, or whether the
  regression-test-per-finding discipline keeps it high. "Worth checking at end of v0.2." Not yet
  answered.
- **Asset.** A measured baseline (91.3% real coverage at v0.1.2, ≈6 points headroom) and the omit-list
  pattern that makes the number meaningful, plus the regression-test-per-finding discipline generating
  "free" coverage.
- **First three steps.** (1) Record the current measured coverage against the same omit-list at the
  latest release (v0.2.1). (2) Compare it to the v0.1.2 baseline of 91.3% and compute the headroom
  delta. (3) Interpret: if headroom dropped below ~2 points, that signals either raising the floor
  (testing compounds) or hunting under-tested features (testing failing).
- **Milestone.** You have a result when the headroom trend across ≥2 releases is recorded with a
  raise-the-floor or find-under-tested-features recommendation, closing the §8 question.

### F9 — Rotate vs. reuse the hardening-audit lens pair

- **Gap.** §8 (v0.1.1, still open) asks whether hardening should keep the proven spec-drift+friction
  pair (now a triple with CI-as-contract) or rotate to a different orthogonal pair (e.g.
  security-audit + performance-audit). The personas-rotate-per-phase principle argues rotate; the pair
  worked so well it argues keep. Unresolved.
- **Asset.** Multiple hardening passes on record (v0.1.1, v0.1.2, v0.2.1) with their lens compositions
  and find-rates, plus the lens library in `subagent-brief-templates.md`.
- **First three steps.** (1) At the next hardening pass, run the standard triple-lens set. (2) Add or
  swap in one rotated lens (e.g. security-audit) and record its findings separately. (3) Classify the
  rotated lens's findings as net-new vs. covered by the standard set.
- **Milestone.** You have a result when a rotated lens's findings are classified net-new vs. redundant
  with a recommendation to keep-standard or rotate recorded against the §8 entry.

### F10 — Per-phase parallel-vs-serial reviewer rule as a checked choice

- **Gap.** §8 (v0.1.1, still open) asks whether the per-phase three-reviewer pass should adopt the
  parallel-when-orthogonal / serial-when-complementary rule as an explicit per-phase decision rather
  than defaulting to parallel-with-personas. The rule exists; whether making it a per-phase checked
  choice improves outcomes is untested.
- **Asset.** Both forms proven once (Phase 6 serial-with-checkpoints; v0.1.1 parallel-with-orthogonal)
  and the unified rule already stated in the practices catalogue.
- **First three steps.** (1) At the next phase, classify the three briefs as orthogonal or complementary
  before running. (2) Pick parallel or serial per the rule and record the classification + choice. (3)
  Note whether the chosen form produced the expected benefit (course-correction value if serial;
  cheaper concurrency if parallel).
- **Milestone.** You have a result when at least two phases record a pre-run orthogonality
  classification and the resulting form choice, and the outcomes support (or refute) making the rule a
  standing per-phase step.

### F11 — Three-tier gating: does each tier catch a *different* failure class? (re-ask)

- **Gap.** §8 (v0.1.2) has only a **partial answer**: pre-commit.ci caught one push of unformatted
  code, but pre-push pytest "hasn't caught anything novel yet — barely been exercised. Worth
  re-asking after v0.2." Whether the tiers are genuinely non-redundant is unsettled.
- **Asset.** The three-tier config in `.pre-commit-config.yaml` running across several releases, with a
  running tally of what each tier has caught.
- **First three steps.** (1) Over the next release, log every gate catch by tier (commit / pre-push / CI).
  (2) Classify each by failure class (formatting, wrap-fragility, coverage, matrix, release). (3) Check
  whether any class was caught *only* at one tier.
- **Milestone.** You have a result when the release's catches are tabulated by tier × failure class and
  at least one class is shown caught only at a specific tier (or the tiers shown redundant), closing the
  §8 re-ask.

### F12 — Docs-content smoke tests: do they catch a *real-world* production regression? (open)

- **Gap.** §8 (v0.1.1) notes the docs-content smoke tests caught a development-time regression, but the
  post-release value "will only show up if someone Edits a doc in a way that contradicts the code" —
  not yet observed in the wild.
- **Asset.** ~14 docs-content assertions across quickstart/commands/README/spec in `test_v0_1_1_fixes.py`.
- **First three steps.** (1) Track any doc edit a docs-content smoke test rejects going forward. (2)
  Distinguish development-time catches from post-release catches. (3) Record the first post-release catch
  (or the continued absence of one) against the §8 entry.
- **Milestone.** You have a result when a docs-content smoke test catches a doc-vs-code contradiction
  introduced *after* a release, or a stated observation window passes with none (weak evidence the
  practice is mostly self-validating).

**Why F1 is the top pick.** Leverage: structured reviewer output unblocks or amplifies F4, F6, F9,
and F10 — every experiment that needs to *compare findings across reviewers or tiers* currently
depends on hand triage, and F1 makes that programmatic and reproducible. It directly operationalizes
the strongest confidence signal the project has (convergence, §1d). Feasibility: it needs no new
feature work and no live API calls — it can be validated by *replaying* a past phase's file set
against the JSON schema and checking the convergence set against the already-recorded manual triage.
High leverage, low cost, no dependency on anything unbuilt — that combination is why it ranks first.

---

## 5. Experiment protocol (checklist)

Run every frontier experiment through this checklist. It is what keeps an experiment a *result* and
not an anecdote.

1. **Declare the hypothesis and the predicted numbers** before running. State the measurement method
   (as the cold-start "best-of-5" and smoke "==5" gates do). No number → weaker result (§1c).
2. **Get maintainer sign-off if it touches gates or workflow rules.** Change control routes through
   the maintainer; never weaken a gate to make an experiment pass. Use `flytie-change-control`.
3. **Run it within a normal phase or release.** Experiments ride real work — that is this lab's method.
   Do not build synthetic exercises; the signal comes from the experiment surviving contact with a real
   feature or hardening pass. (F1's *replay* of a past phase is still riding real recorded work, not a
   toy dataset.)
4. **Record the result** in the open-questions (§8) or assessment (§6) record with an
   "Answered (vX.Y.Z)" annotation, following the `flytie-docs-and-writing` cadence (once per release,
   via `pending-lessons.md` mid-release). Name false alarms explicitly; never delete catalogue history.
5. **Promote or retire.** Adopted → §2.N `[ADOPTED]` entry in `patterns.md` (+ a AGENTS.md line if it
   is a session rule). Failed/superseded → documented retirement, kept in the record.
6. **Update the claimable list** in `flytie-article-and-positioning` if the result is publishable —
   but only after it clears the §1 evidence bar. Open problems stay OPEN; candidate practices stay
   CANDIDATE until promoted.

---

## 6. What is NOT frontier (the fence)

| Not frontier | Why | Where it belongs |
|---|---|---|
| CLI feature work (v0.3.0 `edit --from-suggestion`, semantic material matching, `material categorize`) | that is the roadmap, not methodology research | `ROADMAP.md` / normal phases |
| Anything that weakens a gate | project canon: no gate-weakening; changes route through the maintainer | `flytie-change-control` |
| Experiments requiring live API calls in tests | tests inject a fake `Streamer`; live calls are non-deterministic and out of bounds | `flytie-validation-and-qa` (evidence standards) |

Feature work can *host* an experiment (experiments ride real work), but shipping a feature is not by
itself a methodology result. The frontier is the workflow, not the CLI surface.

---

## Provenance and maintenance

- **Date-stamp:** authored 2026-07-02, against flytie **v0.2.1**.
- **Sources (all gitignored internal docs; embedded here because fresh clones will not have them):**
  `ai-development-practices/open-questions.md` (§8, read in full), `ai-development-practices/assessment.md`
  (§3/§4/§6, read in full), `ai-development-practices/patterns.md` (§2 adoption-evolution notes),
  `collaboration-retrospective/revisions.md` (Revisions 1–10), `collaboration-retrospective/theses.md`
  (theses 1–24), `handoff.md` (state, known issues, next-step).
- **§8 status verified at authoring:** confirmed STILL-OPEN — F5 pending-lessons signal filter,
  F8 coverage-headroom compression, F3 marker-as-contract generalization, F11 three-tier
  differentiation (partial answer, "re-ask after v0.2"), F12 docs-smoke real-world catch, F9 lens
  rotate-vs-reuse, F10 per-phase parallel/serial choice, F7 Codex-written next-step ("Still
  untested"), F4 four-reviewer scaling ("four wasn't tried"). Confirmed ANSWERED and therefore
  EXCLUDED — three/meta-reviewer scaling to three (Phase 5–6), review-the-reviewers (Phase 6),
  regression-test-per-finding suite growth, spec-drift audit justification (post-Phase 4), dual-lens
  non-redundancy, impact-ranked slices, `cli_runner` conftest fixture + `COLUMNS=80` pre-push (v0.1.2),
  narrative-doc split (v0.2), CI-as-contract third lens (v0.2.1). F1/F2/F6 drawn from §6
  candidate-practices recorded as not-yet or only-partially adopted.
- **UNVERIFIED / caveat:** the "no measurable quality loss" Sonnet claim (basis for F6) is recorded as
  an impression, not a controlled result — that is precisely why F6 remains open. The ruff-isort and
  Codex-sonnet-4-6 precedents are drawn from `assessment.md §4` as written and were not independently
  re-derived here.
- **Re-verification commands (from the repo root):**
  - `grep -n "still open\|Still untested\|Partial answer\|Answered" ai-development-practices/open-questions.md` — re-check which §8 items remain open.
  - `grep -n "\[ADOPTED\]\|\[PARTIALLY ADOPTED\]\|Structured subagent\|Token budget" ai-development-practices/assessment.md` — re-check §6 candidate-vs-adopted status.
  - `grep -n "smoke\|600\|fail_under\|best-of-5" tests/test_v0_1_2_fixes.py pyproject.toml` — confirm the numeric gates in §1c.
  - `grep version src/flytie/__init__.py` — confirm the version this skill was stamped against (expect 0.2.1).
