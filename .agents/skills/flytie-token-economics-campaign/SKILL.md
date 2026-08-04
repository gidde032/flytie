---
name: flytie-token-economics-campaign
description: >-
  The executable, decision-gated campaign for keeping an agent session's token
  cost proportional to the work it delivers on the flytie project. Use when
  starting a session on this project and want to set a cost posture; when
  planning a release's documentation updates; when you notice yourself re-reading
  the same file, or the conversation has compacted; when deciding whether a task
  runs on Opus (this session) or a Sonnet subagent; when budgeting a reviewer or
  audit pass; or any time the session simply "feels expensive." Covers both the
  standing cost-discipline rules every session follows and the diagnose-and-fix
  campaign to run when a cost problem has already appeared. Third-person triggers:
  session start, doc-update planning, repeated file re-reads, a compaction event,
  Opus-vs-Sonnet delegation decisions, review-pass budgeting.
---

# flytie token-economics campaign

This skill is the standing cost discipline AND the recovery campaign for flytie's
hardest live operational problem: **unmeasured file-load and doc-update costs
silently dominating a session's token budget.** It is written for a zero-context
mid-level engineer or a Sonnet-class model that is *running an agent session* on
this project. Because the subject is session mechanics, terms are defined inline
as they appear.

Term glossary (used throughout):
- **Context window** — the total text (files, conversation, tool output) the model
  is holding at once. Every file you Read is loaded into it and counts against the
  per-session budget.
- **Compaction** — when the conversation grows too large, the harness summarizes
  older turns to free space. Each compaction costs tokens and loses detail. You can
  observe it happening (the transcript is replaced by a summary).
- **Full-read** — reading an entire file into context with one Read call.
- **Tail-read** — reading only a slice of a file: `Read(file, offset=N, limit=80)`.
- **Anchor / anchor-edit** — editing a file by matching a short unique string
  (the "anchor") as `old_string`, without having loaded the whole file. The Edit
  tool only requires the file was Read *once* in the conversation — not fully.
- **Subagent** — a fresh agent you spawn with its own context window. It starts
  cold; it does not inherit this conversation. You brief it, it works, it reports
  back. Its file-load cost is paid in *its* context, not yours.
- **Opus / Sonnet** — the expensive high-judgment model (this session, by default)
  vs. the cheaper model used for subagents. Rule of thumb: "Opus thinks, Sonnet
  types, Opus verifies."

## The problem, with recorded history

The campaign exists because of a specific, recorded maintainer complaint (verbatim,
preserve it — it is article source material):

> "the git repo is good, why are you killing my usage so fast? i didn't think that
> the doc updates and checking my gitignore changes would take 2 sessions worth of
> usage"

The diagnosis: **file-load and doc-update costs were invisible.** Nobody measured
them, so nobody managed them, and they silently ate the budget. Recorded incidents
(these are HISTORICAL observations from project records — cite them as history, not
as numbers you can re-verify today):

| Incident (recorded history) | Recorded cost |
|---|---|
| Phase 3 FUSE deadlock, recovered in place instead of pivoting | ~20k tokens |
| A doc-update-plus-gitignore-check episode (the quote above) | ~2 sessions of usage |
| v0.1.2 doc-split one-time restructuring cost | +5% lines, once |
| v0.1.2 doc-split ongoing benefit | ~10x per-update read-cost reduction |
| Dual-lens audit moved from Opus (v0.1.1) to Sonnet (v0.1.2) | ≈half cost, no measured quality loss |
| A 12-file doc restructure done by one Sonnet subagent | ~117k tokens (vs. 2–3x that on Opus) |

The fix batch that emerged at the v0.1.2 inflection point — tail-reads, Sonnet
subagents for mechanical work, once-per-release batching, and the narrative-doc
split — is now standing discipline. This skill turns that discipline into gates.

**None of the token figures above are re-verifiable now.** They are recorded
outcomes. What you CAN verify live are file sizes (`wc -l`), your own re-read count,
and compaction events. The campaign is built on those measurable proxies, never on
eyeballing "this feels cheap."

## When NOT to use this skill

- **FUSE recovery mechanics** (EDEADLK, re-open-the-folder, `cp`-to-refresh-inode) →
  `flytie-debugging-playbook` owns the recovery steps. This skill only tells you the
  *cost* of fighting FUSE in place (~20k tokens) and that the cheap move is to ask
  the user to re-open the folder.
- **Which doc updates when / doc cadence mechanics** → `flytie-docs-and-writing`.
  This skill references the batching heuristic; that skill owns pending-lessons.md
  routing and the per-doc update rules.
- **How to write a subagent brief / reviewer shapes** → `flytie-subagent-orchestration`.
  This skill decides *what runs where* on cost grounds; that skill owns the briefing.
- **Unproven token experiments as frontier research** → `flytie-research-methodology-and-frontier`
  owns the lifecycle of candidate rules. This skill lists current CANDIDATEs and the
  promotion protocol, but retired experiments live there.
- **Quality gates / change classes** → `flytie-change-control`. Any rule change this
  campaign proposes must route through that skill's sign-off; the campaign never
  weakens a gate.

---

## PHASE 0 — Measure before acting

**Gate: you have numbers in hand before you spend on reads or edits.**

You cannot manage what you do not measure. The measurable proxies available on this
project, cheapest first:

1. **`wc -l` on every file before you Read it.** One `wc -l` is nearly free; a full
   Read of a 300-line file is not. Run the sweep at session start:

   ```bash
   # Run from your clone's project root. (Cowork sandbox sessions only: cd to
   # your session's mount path, e.g. /sessions/<session>/mnt/flytie, and
   # `export PATH="$HOME/.local/bin:$PATH"` first.)
   cd <absolute path to your clone's project root>
   wc -l AGENTS.md handoff.md fly-tying-tracker-spec.md \
         ai-development-practices/*.md collaboration-retrospective/*.md
   ```

   If the bash sandbox is unavailable (it sometimes is — see the fenced path on FUSE
   below), you can approximate a file's length with the Read tool: a Read whose
   `offset` exceeds the file length returns "the file has N lines." That N is the
   count. Slower than `wc -l`; use only when bash is down.

2. **Re-read count (self-observable).** Notice when you Read a file you already Read
   this session. Once is normal. **Twice on the same file = context isn't holding →
   branch to Phase 2.**

3. **Compaction events (self-observable).** When the harness compacts, note it. One
   compaction is a yellow flag; it is trigger (a) for a fresh session (Phase 2).

4. **Subagent token reports.** When a subagent finishes, it can report its token use.
   Capture that number — it is your only ground-truth measurement of delegated cost,
   and the raw material for the promotion protocol at the end of this skill.

**Decision gate (Phase 0 → Phase 1):**
- File > ~200 lines → do NOT full-read it on the expensive model. Tail-read or
  delegate (Phase 1 / Phase 3).
- You have re-read the same file twice → context isn't holding → **branch to Phase 2.**
- Otherwise → proceed with standing rules (Phase 1).

**Verified current file sizes (as of 2026-07-02, v0.2.1)** — re-verify with the sweep
above:

| File | Lines (verified 2026-07-02) | Over ~200? |
|---|---|---|
| AGENTS.md | 111 | no — full-read OK |
| handoff.md | 180 | no — full-read OK |
| fly-tying-tracker-spec.md | 156 | no — full-read OK |
| ai-development-practices/patterns.md | 306 | **yes — tail-read** |
| ai-development-practices/assessment.md | 130 | no |
| ai-development-practices/open-questions.md | 41 | no |
| collaboration-retrospective/revisions.md | 114 | no |
| collaboration-retrospective/theses.md | 44 | no |

The narrative docs were split per-topic in v0.1.2 precisely so most land under the
threshold. As of 2026-07-02 the one narrative file over ~200 lines is
`patterns.md` (306). Full-read the rest freely; tail-read patterns.md.

---

## PHASE 1 — Standing rules (every session, always on)

**Gate: apply these to every read and edit; they are not optional.** Status column
distinguishes rules validated by recorded outcomes (VERIFIED) from proposals still
under test (CANDIDATE). CANDIDATE rules must not be enforced as if settled.

| # | Rule | Threshold / trigger | Status |
|---|---|---|---|
| 1 | Full-read on the expensive model is fine | file < ~200 lines | VERIFIED |
| 2 | Tail-read + anchor-edit instead of full-read | file > ~200 lines | VERIFIED |
| 3 | Delegate multi-paragraph insertions into large files to a Sonnet subagent, then verify post-flight with a small tail-read | insertion spans several paragraphs OR touches a >200-line file | VERIFIED |
| 4 | "Opus thinks, Sonnet types, Opus verifies" — reserve the expensive model for judgment; push file-loading and mechanical edits to Sonnet | always | VERIFIED |
| 5 | Update narrative docs once per release, not per batch; mid-release lessons go to `pending-lessons.md` | release cadence | VERIFIED |
| 6 | Sonnet is the **adopted default** for reviewer/audit briefs; raise the model tier when convergence quality matters more than cost | any review or audit pass | ADOPTED (see caveat below) |
| 7 | Per-phase numeric token budget with a tripwire | (not implemented) | CANDIDATE |

**Rule 2 mechanic — tail-read + anchor-edit, step by step.** This is the single
highest-leverage move and it is worth spelling out:

1. `Read(file, offset=N, limit=80)` — grab only the ~80-line slice near where the
   change goes. You now have enough of the file loaded to edit it, without paying the
   full-file read cost.
2. Pick a **unique anchor string** from that slice — a phrase that appears exactly
   once in the file (a header line, a distinctive sentence). Uniqueness matters: the
   Edit tool refuses a non-unique `old_string`.
3. `Edit(file, old_string=<anchor>, new_string=<anchor + your addition>)`. The Edit
   tool only requires the file was Read at least once this conversation — NOT that
   the whole body is in context. That is why the tail-read is sufficient.

**Rule 3 mechanic — delegate + verify.** For a multi-paragraph addition or a batch of
anchor-edits across several sections of a big file: spawn a Sonnet subagent (briefing
mechanics owned by `flytie-subagent-orchestration`) with the exact text to insert, the
exact anchor strings, the file paths, and style notes ("match the existing register,
factual not narrative"). The file load happens in the subagent's cheaper context.
Then **verify on the expensive model with one small tail-read per touched file** —
this post-flight check is mandatory and cheap (~500 tokens of tail-reads, per project
records, vs. thousands to silently ship a mis-anchored edit). After a *restructure*
(files moved/renamed), add a parent-side project-wide `grep` for the old reference:
the doc-split caught 4 stale references that the subagent's literal anchor-matching
missed, because a subagent only guarantees the anchors *named in its brief* were
updated, not that no stale references remain (recorded, v0.2 doc-split).

Rules 5 and 6 are owned in detail by sibling skills (`flytie-docs-and-writing` and
`flytie-subagent-orchestration` respectively); they appear here because they are cost
rules first. Rule 6 is the **adopted default**, not a blind-benchmarked result: the
v0.1.2 dual-lens audit and the v0.2.0 three-reviewer pass both ran on Sonnet at
≈half the Opus cost with no quality loss *observed* — but that is an impression
from two runs, not a controlled head-to-head. The controlled benchmark is open
problem F6 in `flytie-research-methodology-and-frontier`. **Escape hatch: raise the
model tier when convergence quality matters more than cost** (matches the rule
`flytie-subagent-orchestration` §8 already carries).

---

## PHASE 2 — Session lifecycle

**Gate: decide, with the maintainer, whether to continue this session or hand off to a
fresh one.**

A fresh session's warm-up cost is **bounded and cheap**: it re-reads `AGENTS.md` +
`handoff.md` and little else. Verified 2026-07-02: 111 + 180 = **291 lines combined**
(re-verify: `cat AGENTS.md handoff.md | wc -l`). Compare that bounded cost against the
unbounded, growing cost of dragging a long, already-compacted conversation forward.

**The three proactive fresh-session triggers** (any one fires the recommendation):

- **(a)** The conversation has already compacted at least once.
- **(b)** The active task has shifted to a clearly different surface than earlier turns
  (e.g., you just shipped a release and are about to start feature work).
- **(c)** You are re-reading the same files because context isn't holding (the Phase 0
  re-read proxy — twice is the tripwire).

**How to act on a trigger.** You do NOT restart unilaterally. Frame a recommendation to
the maintainer with the rationale: name the boundary you're at, name the cost trend
(growing compaction cost vs. bounded 291-line warm-up), point at the bounded warm-up.
Then let the maintainer decide. Do not insist. (This mirrors the plan-then-execute
cadence: surface the choice, don't make it silently.)

**If you're mid-task and cannot restart** (the maintainer wants to press on): tighten
scope and delegate remaining reads to Sonnet subagents so the file-load cost lands in
cheaper contexts rather than this one.

---

## PHASE 3 — Delegation economics

**Gate: is the brief self-contained enough to hand off?** A subagent starts cold. If
you cannot state the task with exact paths, exact text/anchors, and an explicit
out-of-scope list, the brief is not ready — writing it half-formed wastes a whole
subagent spawn.

**What runs where** (decide on cost + judgment grounds):

| Task | Runs on |
|---|---|
| Synthesis, judgment calls | Opus / this session |
| Wording-sensitive drafting (CHANGELOG, spec backports, plan proposals) | Opus / this session |
| Audit triage (severity ranking, naming false alarms) | Opus / this session |
| Verification reads (post-flight tail-reads) | Opus / this session |
| File-heavy reads (loading large docs to extract a fact) | Sonnet subagent |
| Mechanical batched edits (anchor-edits across sections) | Sonnet subagent |
| Reviewer / audit passes | Sonnet subagent |
| Doc-routing passes (pending-lessons.md → destination docs) | Sonnet subagent |

**Post-flight verification is MANDATORY and cheap.** Trust-but-verify at *file*
granularity: ~500 tokens of tail-reads (recorded) beats thousands lost to a silent
mis-anchor shipping unnoticed. And after any restructure, the parent-side project-wide
`grep` for the old reference is the complete check — a subagent's "all anchors matched
first try" is honest but only covers the anchors it was told about (recorded: the
doc-split's 4 stale references). Briefing mechanics: `flytie-subagent-orchestration`.

---

## PHASE 4 — Doc-cost management

**Gate: release-end consolidation is done before you tag.**

1. **The batching heuristic.** Update narrative docs (`ai-development-practices/`,
   `collaboration-retrospective/`) **once per release**, not once per batch within a
   release. Each touch pays the file-load cost; batching amortizes it. Mid-release
   lessons accumulate as one-line bullets in `pending-lessons.md`; at release end one
   Sonnet subagent routes each entry to its destination doc and clears the scratch
   file. (Mechanics owned by `flytie-docs-and-writing`.)

2. **The doc-split precedent.** When a single narrative doc crosses ~400 lines *and*
   gets regular updates, split it per-topic (one section per file + an `index.md` nav
   block). Recorded worked example (v0.2 split): one-time cost ~+5% lines; ongoing
   benefit ~10x per-update read-cost reduction, because each update now touches one
   small file instead of the whole monolith. Threshold: under ~200 lines, leave it
   monolithic; over ~400 with regular updates, split.

3. **AGENTS.md is itself tracked.** Verified 2026-07-02 it is **111 lines**, well under
   the ~200-line split threshold. CANDIDATE rule: if AGENTS.md crosses ~200 lines,
   propose a split (operating-rules / safety / token-economics / where-to-read-more)
   before adding more content. Not yet triggered.

---

## Fenced-off wrong paths (with recorded cost)

Do not walk these. Each cost the project real budget (HISTORICAL figures):

| Wrong path | Why it's wrong | Recorded cost |
|---|---|---|
| Fighting FUSE deadlocks in place | The cheap move is asking the user to re-open the folder (fresh inodes clear it project-wide) | ~20k tokens (Phase 3) |
| Updating narrative docs per-batch | Each batch pays the full file-read cost again; batching amortizes it | the "2 sessions" episode |
| Full-reading large docs on the expensive model "to be safe" | The tail-read + anchor-edit path gives the same edit at a fraction of the load | doc-cost inflection point, v0.1.2 |
| Continuing a compacted session across a workflow boundary | Compaction cost is unbounded and growing; a fresh session's warm-up is bounded (291 lines) | (recorded rationale) |
| Skipping post-flight verification of subagent edits | Silent mis-anchors ship unnoticed; the check is ~500 tokens | 4 stale refs, v0.2 doc-split |
| Spawning a reviewer without a sandbox pre-flight check | The reviewer correctly reports on an unfaithful sandbox; you pay triage cost on false positives | Phase 6 ate 3 false positives |

FUSE recovery details are owned by `flytie-debugging-playbook`; the reviewer sandbox
pre-flight is owned by `flytie-subagent-orchestration`. Listed here only for their cost.

---

## Solution menu — cost already blown mid-session

When you realize the session is already expensive, apply in order (most → least value):

1. **Delegate all remaining file work to Sonnet subagents.** Moves the load off this
   context immediately; highest leverage.
2. **Propose a fresh-session handoff at the next slice boundary.** Update `handoff.md`
   FIRST so the fresh session warms up correctly, then recommend the handoff to the
   maintainer with the Phase 2 rationale.
3. **Tighten the slice scope with the maintainer.** Cut the remaining work down to what
   fits the remaining budget; surface the trade-off, don't decide it silently.
4. **Tail-read-only mode for the rest of the session.** No full-reads; every remaining
   read is `Read(file, offset, limit)`. Lowest value of the four but always available.

---

## Validation & promotion protocol (how a cost rule becomes canon)

New cost rules do NOT get adopted on intuition. They earn canon status by measurement,
and any adoption routes through change control (maintainer sign-off — owned by
`flytie-change-control`). The campaign never weakens a quality gate to save tokens.

1. **Measure a baseline.** Capture the current cost of the thing you want to improve —
   subagent token reports, session count per release, per-update read cost.
2. **Run the candidate for one release.** Apply the proposed rule through exactly one
   release cycle. Keep it labeled CANDIDATE the whole time.
3. **Compare.** Baseline vs. candidate, using the same measurable proxies. Success =
   **a measured reduction with no quality-gate regression.** Never "it felt cheaper."
4. **Propose to the maintainer via change control.** If it passes, the maintainer signs
   off and it becomes a VERIFIED standing rule (Phase 1).
5. **Retire failures explicitly.** A candidate that doesn't show measured benefit gets a
   documented retirement — point to `flytie-research-methodology-and-frontier`, which
   owns the experiment lifecycle. Don't silently drop it; the retirement is data.

**Current OPEN / CANDIDATE items** (as of 2026-07-02, v0.2.1 — none yet promoted):

- **Per-phase numeric token budget with a tripwire.** Partially approximated by the
  estimate-and-approve gate since Phase 5, but no hard numeric budget exists yet.
- **Structured JSON reviewer returns** (`bugs: [{file, line, severity, ...}]`) to make
  triage cheaper — currently reviewers return free text triaged by hand.
- **Measuring pending-lessons signal-filter quality** — whether the scratch-file's
  "does this survive consolidation?" filter genuinely raises lesson quality, measured
  by comparing pending-entry count to the count that survives routing at release end.

---

## Provenance and maintenance

- **Date:** 2026-07-02. Project state: flytie v0.2.1, tagged, on PyPI.
- **Sources:** `AGENTS.md` (token-economics section), `handoff.md` ("Working
  efficiently — token-economics notes"), `collaboration-retrospective/revisions.md`
  (Revision 8) + `theses.md` (theses 15, 16, 17, 19),
  `ai-development-practices/patterns.md` §2.15/§2.16/§2.17,
  `ai-development-practices/open-questions.md` §8 token entries,
  `ai-development-practices/assessment.md` §4 (FUSE cost, edit-spamming).
- **Live-verifiable numbers** carry an "as of 2026-07-02" stamp and were confirmed by
  reading the files this session; token costs of past incidents are RECORDED HISTORY
  and are not re-verifiable.
- **Re-verification commands:**
  - File-size sweep (the Phase 0 proxy):
    `wc -l AGENTS.md handoff.md fly-tying-tracker-spec.md ai-development-practices/*.md collaboration-retrospective/*.md`
  - Fresh-session warm-up bound: `cat AGENTS.md handoff.md | wc -l` (expect ~291 as of 2026-07-02).
  - AGENTS.md split tripwire: `wc -l AGENTS.md` (split candidate at >200; 111 as of 2026-07-02).
- **Maintenance cadence:** re-run the sweep at the start of any release that touches
  docs; update the verified-size table and the fenced-path costs if a file crosses a
  threshold or a new incident is recorded. Route any rule promotion/retirement through
  change control and reflect it in the Phase 1 status column.
