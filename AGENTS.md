# AGENTS.md — flytie operating instructions for Codex agents

This file tells an agent working on flytie how to *operate*, not what's been built. For project state (current version, active files, known issues) read `handoff.md` first. For the catalogue of why each practice exists, start at `ai-development-practices/index.md` (split into per-topic files in v0.1.2). This file is the compressed working-instructions distillation that should govern any session.

## Project at a glance

flytie is a local-first, AI-augmented Python CLI for fly tying recipe management. Patterns are stored in a local SQLite DB with bundled Alembic migrations. The full spec is at `fly-tying-tracker-spec.md`; sections 2 (stack), 3 (functional requirements), 5 (schema), and 6 (six-phase plan) are required reading before non-trivial work. The package source is under `src/flytie/`; tests under `tests/`. CLI entry: `python -m flytie` or `flytie` after `pip install -e .[dev,pdf,ai]`.

**The project has a secondary purpose:** the development practices used to build flytie are being captured for a tech-forum article series on agentic coding. This means `ai-development-practices/` and `collaboration-retrospective/` serve double duty (project memory + article source material). Preserve user quotes verbatim — they're article-worthy. Don't paraphrase when you mean to attribute.

## Workflow shape

Two shapes of work, and the choice of which one applies determines everything that follows.

**Feature phases** (six during v0.1.0; future v0.2+ candidates follow the same shape). One coherent feature per phase. Loop: implement → spawn **three** contextless review subagents (one always a "skeptical senior engineer," the others rotating domain specialists) → fix every CRITICAL/HIGH/MEDIUM finding with a paired regression test → write a `phase-summaries/phase-N.md` summary documenting work, fixes, suggestions accepted vs. deferred, and a candid "how Codex was used" section.

**End-of-version hardening passes** (v0.1.1, v0.1.2). Different shape: dual-lens audit (two contextless subagents with orthogonal lenses — typically spec-drift + contributor/user-friction) → report findings back ranked by severity, **explicitly naming false alarms and why** → user picks impact-ranked slices → execute slice → report → user picks next slice. Tag and release at the end. Don't conflate this shape with a phase — phase-shaped work is for new features, pass-shaped work is for hardening.

**Pick parallel vs. serial reviewer execution by orthogonality.** If briefs are orthogonal (different surfaces — one reads docs, another reads code), run in parallel. If briefs are complementary on the same surface (each reviewer builds on the previous), run serially with checkpoints so the user can course-correct between reviewers.

## Check-in cadence

Don't disappear into autonomous execution for non-trivial multi-step work. The pattern that worked across this project:

- Before non-trivial implementation work, propose a plan with impact-ranked slices and wait for the user to pick. Don't pick for them.
- At natural slice boundaries (one of A/B/C/D delivered), report back what landed and what's next; await direction.
- For mechanical batched edits (e.g., applying 8 audit findings, each one-line), it's fine to execute the batch in one go and report at the end — but only if you've already confirmed scope with the user.
- For ambiguous or judgment-call work, surface the choice rather than make it silently. The D11 v0.1.1 episode (renumbering a suffix vs. leaving it) is the canonical example: an autonomous agent would have implemented and pinned the wrong choice via regression test.

Use `AskUserQuestion` (or just inline questions in your response) early when the brief is underspecified, not late when you've already executed something the user didn't ask for.

## Subagent practices

The dual-lens audit and the per-phase three-reviewer pass both depend on contextless subagents. Rules that emerged across this project:

- **Sonnet, not Opus, for subagents.** v0.1.2's audit ran both lenses on Sonnet at roughly half the v0.1.1 cost with no measurable quality loss. The pattern combines naturally with cost optimization because each brief is self-contained — agents don't need conversation context, just file paths, the brief, and a length cap.
- **Brief them like a smart colleague who walked in cold.** State the goal, hand over the specific files to look at, define the severity rubric, and cap the response length (`under 500 words`). Don't ask them to synthesize — that's your job after they report.
- **Heavy briefing on what's out of scope.** Name items already deferred to a later release or already triaged in earlier phases so the subagent doesn't waste tokens on them and you don't waste triage cycles dismissing them.
- **Audit findings always come back with severity tags.** Triage every finding explicitly: real CRITICAL / real HIGH / real MEDIUM / real LOW / false alarm with reason. Name the false alarms so a future audit doesn't re-raise them.
- **Pair every accepted finding with a regression test.** The contract is "no shipped bug ever re-surfaces silently." Tests go in phase-specific files (`test_review_fixes_phase{N}.py` for per-phase reviews, `test_v0_X_Y_fixes.py` for hardening-pass audits) whose docstrings name the reviewer and severity.
- **Compose reviewer briefs from `subagent-brief-templates.md`** rather than writing from scratch. Fill the placeholders (persona or lens, `{files-to-review}`, `{already-deferred}`) and copy the boilerplate verbatim. The file covers two reviewer shapes — the per-phase three-reviewer brief and the end-of-version dual-lens audit — plus a persona library (skeptic + 5 domain specialists) and a lens library (spec-drift, contributor-friction, CI-as-contract). Non-reviewer subagent briefs (mechanical edits like the v0.2 doc-split, drafting like the v0.1.2 doc-update) remain bespoke per-use — not templated.

## Token-economics rules

This project hit a doc-cost inflection point at v0.1.2. The rules that emerged:

- **Files under ~200 lines: full Read on Opus is fine.**
- **Files over ~200 lines (the spec, or any narrative doc that grows past the threshold): default to tail-read + anchor-edit.** As of v0.1.2 the narrative docs are split into per-topic files in `ai-development-practices/` and `collaboration-retrospective/`, each typically under the threshold; full-read on Opus is fine for those. `Read(file, offset=N, limit=80)` grabs just the relevant tail; identify an anchor string; `Edit` applies with that anchor as `old_string`. The Edit tool only requires the file was Read once in the conversation — not the whole body.
- **For multi-paragraph additions or batched anchor-Edits across large files, spawn a Sonnet subagent.** Brief it with the exact text to insert, the exact anchor strings, the file paths, and style notes. Verify post-flight on Opus with a small tail-read per touched file.
- **What stays on Opus**: synthesis, judgment calls, wording-sensitive drafting (audit triage, CHANGELOG entries, spec backports, plan proposals), and verification reads. Lean on Sonnet subagents and tail-reads for file-loading and mechanical-edit work.
- **General shape**: Opus thinks, Sonnet types, Opus verifies.
- **Batching heuristic**: update the narrative docs (`ai-development-practices/`, `collaboration-retrospective/`) **once per release**, not once per batch within a release. Each touch pays the file-load cost; batching amortizes it.
- **Session lifecycle.** Start fresh sessions at major workflow boundaries (between releases, between phases, after a major slice closes) rather than continuing extended threads. Compaction cost grows with conversation length; the warm-up cost of a fresh session is bounded by the size of `handoff.md` + this file (currently ~340 lines combined, well under the threshold). **Proactively suggest a fresh session** when: (a) the conversation has already compacted at least once, (b) the active task has shifted to a clearly different surface than earlier turns (e.g., we just shipped a release and are about to start feature work), or (c) you're noticing repeated re-reads of the same files because context isn't holding. Frame the suggestion as a recommendation with the rationale — name the boundary, name the cost trend, point at the bounded warm-up — and let Finn decide. Don't insist; he picks. A fresh session reads `handoff.md` and `AGENTS.md` as primary context, plus any task-specific files.

## Documentation update discipline

- `handoff.md` — keep current after every release (it's small enough to full-read on Opus). Update sections: current state table row, active-files mentions of new files, history paragraph, known-issues triage (move resolved to the resolved-list line), next-step section.
- `ai-development-practices/` — update once per release via Sonnet subagent. New patterns go in `patterns.md` (§2.N); new lessons go in `assessment.md` (§4); per-release notes go in `phases.md` (§7); new questions go in `open-questions.md` (§8).
- `collaboration-retrospective/` — update once per release via Sonnet subagent. New workflow shifts go in `revisions.md` (§3 Revision N); new generalizable claims go in `theses.md` (§6).
- `CHANGELOG.md` — Keep-a-Changelog format. Every release gets an `[X.Y.Z] — YYYY-MM-DD` section with Added/Changed/Removed/Fixed subsections. Update the `[Unreleased]` compare link at the bottom.
- `fly-tying-tracker-spec.md` — backport when audits produce DOCUMENT-class findings (deviations the project knowingly accepted but the spec hadn't been updated for). Living spec is a feature; fossilized spec is a smell.
- `README.md`, `CONTRIBUTING.md` — keep in sync with feature changes. Specifically: any new dev tooling step goes in both the README dev block (high-level) and CONTRIBUTING (with explanation).
- `phase-summaries/phase-N.md` — write at the end of each phase; not updated retroactively.
- `pending-lessons.md` (gitignored, project root) — **the implementation of the batching heuristic.** When a lesson surfaces mid-release, append a one-line bullet here under the section for its destination file. **Don't open the destination doc to add a single entry** — that's the workflow this file exists to prevent. At end-of-release, one Sonnet subagent pass routes each entry to its destination file and clears this file back to its empty scaffolding. The file's own structure (six sections, one per destination doc) is a forcing function: writing an entry requires deciding where it belongs, which clarifies the lesson.
- `project-FAQ.md` (gitignored, project root) — two-line answers to questions that recur across sessions. **Add an entry the second time a question comes up, not the first.** Once is a one-off; twice is a pattern worth canonical-referencing. Cross-link to deeper explanations in the practices doc, retrospective, or handoff rather than duplicating content. If an answer would grow past a paragraph, it probably belongs in `ai-development-practices/patterns.md` or `handoff.md` instead.

## Quality gates (must be green before tag)

```bash
ruff format --check src tests
ruff check src tests
mypy src
pytest --cov=src/flytie --cov-report=term-missing   # 85% gate enforced via fail_under
pytest -m smoke                                     # 5 tests, ~3 s sanity
```

The pre-commit + pre-push hooks (registered in `.pre-commit-config.yaml`) catch most of this locally. CI gates everything on PR and release paths. **Coverage floor: 85% via `[tool.coverage.report] fail_under`**, measured against the omit-list in `[tool.coverage.run]` (inert files excluded — same list `pytest` and `ruff` already use).

**Cold-start budget**: `flytie --version` best-of-5 under 600 ms (spec NFR §4). Catches regressions to the import graph; new top-level imports of heavy deps (`weasyprint`, `anthropic`, `alembic`) will fail this gate. Diagnose with `python -X importtime -m flytie --version 2>importtimes.log`.

**Smoke marker as checked contract**: exactly five tests carry `@pytest.mark.smoke` (init success, add+list round-trip, view, shop dedupe, export-db→import-db round-trip). The regression test in `tests/test_v0_1_2_fixes.py` asserts this exact count. If you need to mark a sixth test, update the regression test deliberately — don't loosen it.

## Safety constraints (non-negotiable)

- **The Anthropic API key is read ONLY from the `ANTHROPIC_API_KEY` environment variable.** Never written to disk. Never logged. Never appears in error strings. Never returned by `flytie info` or `flytie config show`. Excluded from `_CONFIG_KEYS`.
- **Only pattern names, hook sizes, and material names are sent to the Codex API as grounding** — never instructions, notes, or the full database. The `build_prompt` function in `src/flytie/ai/suggest.py` is the boundary; new fields added to `Pattern` must NOT be added to the prompt without an explicit privacy review.
- **`.gitignore` excludes internal documents, env files, API keys, and sensitive info.** The current list: `handoff.md`, `spec-drift-audit.md`, `phase-summaries/`, `ai-development-practices/`, `collaboration-retrospective/`, `cards/`, `.env`, `*.key`, `*.pem`, `secrets.*`, SQLite WAL/SHM sidecars. Adding new internal docs? Add them to `.gitignore` in the same commit.
- **`AGENTS.md` (this file) is also gitignored**, alongside the other internal documents. Project conventions are part of the development process, not the public-facing project surface.

## FUSE workaround (do this first if reads start failing)

If reads or edits start returning `OSError: [Errno 35] Resource deadlock avoided`, **ask the user to re-open the project folder before engaging any recovery playbook.** The Cowork mount comes back with fresh inodes; the deadlock clears project-wide for one user action plus a `pip install -e .` to re-point the editable install. That's order-of-magnitude cheaper than the in-place recovery playbook (rsync, retry stragglers with per-file timeouts, reconstruct via host-side `Read` + bash heredoc).

The `*_old.py` stragglers in `src/flytie/` and `tests/` are FUSE-poisoned inodes from the Phase 3 recovery. They cannot be deleted from the sandbox; they're inert (excluded via `pyproject.toml` `addopts` and `[tool.ruff].exclude`). A fresh `git clone` elsewhere will not have them.

## Where to read more

Loaded as needed (don't full-read unless the task requires it):

- `handoff.md` — current project state, active files, known issues, next-step direction
- `ai-development-practices/` — practices catalogue split into per-topic files; start with `index.md` for navigation, `patterns.md` for the catalogue, `phases.md` for per-release notes, `open-questions.md` for §8
- `collaboration-retrospective/` — collaboration narrative split into per-topic files; start with `index.md`, `revisions.md` for workflow revisions, `theses.md` for article-ready theses
- `fly-tying-tracker-spec.md` — the project spec, kept current through audit backports
- `CONTRIBUTING.md` — contributor-facing setup, hook layout, CI gates (public; in the repo)
- `CHANGELOG.md` — release history, Keep-a-Changelog format
- `phase-summaries/phase-{1..6}.md` — per-phase development write-ups (historical, not updated)

## One-line philosophy

The workflow is the product, as much as the code. Practices catalogued in writing compound — both forward (the next session benefits) and backward (a structural fix made today applies a lesson to all prior code). Don't delete entries from the practices catalogue even if a practice is later superseded; the article series wants the evolution, not just the final state.
