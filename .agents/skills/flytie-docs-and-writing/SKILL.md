---
name: flytie-docs-and-writing
description: >
  Use when updating docs after shipping a feature, writing a CHANGELOG entry,
  backporting an accepted deviation to the spec, deciding where a lesson belongs,
  adding a new internal document and gitignoring it, writing or understanding a
  phase summary, or routing mid-release lessons through pending-lessons.md. Also
  use when checking whether a topical guide has drifted behind a shipped command,
  or when any file in docs/, CHANGELOG.md, CONTRIBUTING.md, README.md, or the
  internal narrative directories needs to change.
---

# flytie-docs-and-writing

Runbook for every writing and documentation task in flytie. Covers what exists,
who each document is for, when it changes, and the templates for recurring
artifacts. As of 2026-07-02 (v0.2.1).

## When NOT to use this skill

- **Quality gates, CI, smoke tests, coverage floor** — see `flytie-validation-and-qa`
- **Subagent review briefs** — see `flytie-subagent-orchestration`
- **Session cost / tail-read vs. full-read decisions** — see `flytie-token-economics-campaign`
- **Article-series novelty claims, positioning, thesis standards** — see `flytie-article-and-positioning`
- **Architecture or spec questions not related to writing** — see `flytie-architecture-contract`

---

## 1. Doc map

### Tier 1: Public (committed to the repo)

| File / directory | Audience | Update trigger | Cadence |
|---|---|---|---|
| `README.md` | End users, first-time evaluators | Any user-visible feature change | Per-feature; sync with `CONTRIBUTING.md` |
| `CONTRIBUTING.md` | Contributors setting up locally | New dev tooling step, CI change | Per-feature; new tooling goes here WITH explanation (README gets high-level only) |
| `CHANGELOG.md` | Users, release managers | Every release | Per-release; Keep-a-Changelog format |
| `fly-tying-tracker-spec.md` | Maintainers, agents, contributors | Accepted deviation from the spec (DOCUMENT-class audit finding) | Per backport; living document — fossilized spec is a smell |
| `LICENSE` | Legal | Never (MIT, unchanged) | — |
| `docs/index.md` | Users navigating docs | Feature additions that add new doc pages | Per-feature |
| `docs/quickstart.md` | New users | Feature changes that affect the getting-started path | Per-feature |
| `docs/commands.md` | Users looking up syntax | Every new or changed command | Per-command; this is the canonical command reference |
| `docs/shopping-list.md` | Users of `flytie shop` | Changes to `shop` command behavior | Per-feature |
| `docs/ai-suggestions.md` | Users of `flytie suggest` / `--from-suggestion` | Any change to the AI suggestion surface | Per-feature (see docs-drift trap below) |
| `docs/migrating-from-notebook.md` | Users coming from manual methods | Major workflow additions | Low cadence |
| `docs/json-schema.md` | Developers integrating the export format | Schema changes to `ExportDocument` | Per schema change |
| `docs/pattern-file-format.md` | Users authoring pattern files | Changes to `--from-file` format | Per format change |

### Tier 2: Internal (gitignored; exist in the maintainer's working copy only)

These files do **not** appear in a fresh `git clone`. They exist for the maintainer and for agents working with the maintainer's copy. The skill teaches how to maintain them when present.

| File / directory | Audience | Update trigger | Cadence |
|---|---|---|---|
| `handoff.md` | Agents starting a new session | Every release | After each release — 5 sections (see §2) |
| `AGENTS.md` | Agents; operating instructions | Workflow changes, new non-negotiable rules | Sparingly; compressed instruction distillation |
| `ROADMAP.md` | Maintainer planning | Post-release planning | Per-release or on significant scope shift |
| `pending-lessons.md` | Agents; lessons staging area | Mid-release, whenever a lesson surfaces | Append-only during a release; cleared at end-of-release |
| `project-FAQ.md` | Agents; recurring-question index | Second time a question recurs | On second recurrence, never the first |
| `subagent-brief-templates.md` | Agents authoring reviewer briefs | New reviewer persona or lens added | Rarely; see `flytie-subagent-orchestration` |
| `spec-drift-audit.md` | Maintainer; audit record | Post-audit | Per hardening pass |
| `v0.2.0-phase1-spec.md` | Historical reference | Never (frozen) | — |
| `phase-summaries/` | Maintainer, article series | End of each phase | One file per phase at phase end; naming: `phase-X-Y.md` where X=version, Y=number within version (e.g., `phase-2-1.md`) |
| `ai-development-practices/` | Maintainer, article series, agents | Once per release | 6 files: `index.md`, `patterns.md`, `assessment.md`, `composition.md`, `phases.md`, `open-questions.md` |
| `collaboration-retrospective/` | Maintainer, article series | Once per release | 6 files: `index.md`, `phases.md`, `revisions.md`, `practices.md`, `vignettes.md`, `theses.md` |

---

## 2. Update-cadence rules (full)

### handoff.md — after every release

Update exactly five sections:
1. Current-state table — add a new row for the release
2. Active-files — mention any new files added to the source tree
3. History paragraph — append a paragraph covering what changed
4. Known-issues triage — move resolved issues to the resolved-list line; add new issues
5. Next-step section — rewrite to point at v0.3.0 or the next planned work

### Narrative docs: ai-development-practices/ and collaboration-retrospective/

**Update ONCE PER RELEASE, not per-batch within a release.** Each touch of a narrative doc pays a file-load cost. Mid-release lessons go to `pending-lessons.md` instead (see below). For the rationale on why this batching discipline matters, see the `flytie-token-economics-campaign` skill.

When the release ends, spawn a Sonnet subagent to route each `pending-lessons.md` entry to its destination file:
- New named practices → `ai-development-practices/patterns.md` §2.N
- Lessons about what worked/didn't → `ai-development-practices/assessment.md` §3, §4, §6
- Per-release notes → `ai-development-practices/phases.md` §7
- Deferred questions → `ai-development-practices/open-questions.md` §8
- Workflow shifts → `collaboration-retrospective/revisions.md` §3 (new Revision N entry)
- Generalizable article-ready claims → `collaboration-retrospective/theses.md` §6

### pending-lessons.md — the batching implementation

`pending-lessons.md` is a scratch staging area. Its six sections (one per destination doc) force you to decide where a lesson belongs before you write it.

Append format (required):
```
- [YYYY-MM-DD] [context] one-to-three-sentence lesson.
```
For named entries (patterns, theses, revisions), lead with a bold title:
```
- [YYYY-MM-DD] **Pattern: name** — content.
```

Do **not** open the destination doc to add a single entry during a release — that is exactly the workflow this file exists to prevent. At end-of-release, a single Sonnet subagent pass routes all entries to their destination files and resets the scaffolding (six empty section headers, empty body). Verify post-flight with a project-wide grep.

### project-FAQ.md

Add an entry the **second** time a question recurs, never the first. Once is a one-off; twice is a pattern worth canonical-referencing. Answers stay one paragraph. Cross-link to deeper explanations in `ai-development-practices/`, `collaboration-retrospective/`, or `handoff.md` rather than duplicating content. If an answer would exceed a paragraph, it belongs in `patterns.md` or `handoff.md` instead.

### CHANGELOG.md

Format: Keep a Changelog. Every release gets a section:
```
## [X.Y.Z] — YYYY-MM-DD
### Added
### Changed
### Fixed
### Removed
```
After each release, update the compare links at the bottom of the file. Current pattern (as of v0.2.1):
```
[Unreleased]: https://github.com/finngidden/flytie/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/finngidden/flytie/compare/v0.2.0...v0.2.1
[0.1.0]: https://github.com/finngidden/flytie/releases/tag/v0.1.0
```
The `[Unreleased]` link always points `vCURRENT...HEAD`; each version link points `vPREV...vCURRENT`.

### fly-tying-tracker-spec.md (living spec)

The spec is a **committed** public document (not gitignored — confirmed against `.gitignore`). When an audit produces a DOCUMENT-class finding — an accepted deviation the project knowingly made but the spec had not recorded — backport it to the spec in the same PR. Real precedents: flag-driven `add`/`edit` replaced "interactive prompt"; TOML replaced YAML; the cold-start budget was raised to 600 ms with a rationale recorded in §4.

A fossilized spec — one that no longer matches the implementation — is a smell and will mislead agents.

### README.md and CONTRIBUTING.md

Keep in sync with feature changes. Rule: new dev tooling steps go in **both** — README at high level, CONTRIBUTING with explanation. Commands and options visible to end users go in README; contributor-facing setup details (hook stages, CI gate rationale) go in CONTRIBUTING.

### phase-summaries/phase-X-Y.md

Written at the end of each phase; **never updated retroactively**. Naming: `phase-X-Y.md` where X is the version number and Y is the phase number within that version (e.g., v0.2 phase 1 → `phase-2-1.md`). Current files: `phase-1-1.md` through `phase-1-6.md`, `phase-2-1.md`, `phase-2-2.md`.

---

## 3. The docs-drift trap

Shipped features can outpace topical guides. Real incident recorded in `pending-lessons.md` (2026-06-15): `--from-suggestion` shipped in v0.2.1, `docs/commands.md` was updated, but `docs/ai-suggestions.md` still described the pre-v0.2.1 manual workflow two releases later. The topical guide was missed because it lives in a different file from the command reference.

**Current state (as of 2026-07-02):** `docs/ai-suggestions.md` IS updated and correctly describes `--from-suggestion`, suggestion persistence, and `last_suggestions.json`. The drift was caught and resolved.

**Rule going forward:** per-feature docs checklist = the command reference (`docs/commands.md`) AND every topical guide that mentions the surface. When you add or change a feature that touches the AI surface, check `docs/ai-suggestions.md`. When you add shopping-list behavior, check `docs/shopping-list.md`. Do not assume updating `commands.md` is sufficient.

**Before changing any doc:** grep tests for assertions on it first:
```bash
grep -rn "ai-suggestions\|quickstart" tests/ | head -20
```
Current pinning tests for docs content live in `tests/test_review_fixes_phase6.py`. See `flytie-validation-and-qa` for docs-content smoke test mechanics.

---

## 4. Gitignore discipline

Any new internal document must be added to `.gitignore` in the **same commit** it is created. The current internal-doc block in `.gitignore`:
```
handoff.md
spec-drift-audit.md
phase-summaries/
ai-development-practices/
collaboration-retrospective/
AGENTS.md
ROADMAP.md
pending-lessons.md
subagent-brief-templates.md
project-FAQ.md
v0.2.0-phase1-spec.md
```
If a new doc's category is ambiguous (internal vs. public), ask the maintainer before deciding. Do not guess.

---

## 5. House style

- **Narrative docs** (`ai-development-practices/`, `collaboration-retrospective/`): prose-first — paragraphs, not bullet spam. The catalogue is article source material.
- **Phase summaries**: conversational register. They read like a post-mortem report to a colleague, not a changelog.
- **Verbatim quotes**: maintainer quotes are article source material. Never paraphrase when attributing. Quote the actual words.
- **Severity writeups**: name false alarms explicitly and say why they were false alarms. Vague dismissals don't help future audits.
- **Practices catalogue**: never delete entries from `ai-development-practices/patterns.md` even when a practice is superseded. The article series wants the evolution, not just the final state. Mark superseded practices as such; do not remove them.

---

## 6. Templates

### CHANGELOG release section
```markdown
## [X.Y.Z] — YYYY-MM-DD

One-sentence release framing (e.g., "Two user-facing features; no schema migrations.").

### Added

- **`flytie <command>`** — one-sentence description of what it does, followed by
  key flags if any.

### Changed

- **`flytie <command>` behavior** — what changed and why.

### Fixed

- **Description of fix** — what was wrong and what the correct behavior is now.
```

### Phase summary skeleton
```markdown
# Phase X-Y Summary — <Feature name>

## Goal

One paragraph: what this phase set out to ship and why it was scoped this way.

## Work completed

One paragraph per major surface (core function, CLI command, tests, docs).
Include test counts at the end.

## Bugs found by the review subagents and corrected

Name each reviewer role. For each finding: what the bug was, why it mattered,
and exactly what the fix was. Include regression test name.

## Suggestions accepted vs. deferred

Explicit list: what was accepted (and acted on), what was deferred (and to
when/why). Deferred items should reference the relevant spec section or known
issue.

## How Codex was used

Candid description of what worked, what needed human correction, and any
workflow observations worth recording.
```

### pending-lessons.md entry
```
- [YYYY-MM-DD] [phase/context] Lesson stated concisely in one to three sentences.
```
Named entry (pattern, thesis, revision):
```
- [YYYY-MM-DD] **Pattern: Short Name** — Full content of the pattern, written
  in the register of the destination file.
```

### Spec backport note (DOCUMENT-class finding)
When backporting an accepted deviation to `fly-tying-tracker-spec.md`, add a
parenthetical or inline note at the relevant section, e.g.:
```
(Updated in vX.Y.Z: [brief description of accepted deviation and rationale].)
```
Then record the backport in the CHANGELOG under the release that accepted it.

---

## Provenance and maintenance

**Date:** 2026-07-02. **Source version:** flytie v0.2.1.

**Sources verified for this skill:**
- `.gitignore` — read directly; confirms gitignored internal doc list and that `fly-tying-tracker-spec.md` is NOT in it (spec is public)
- `CHANGELOG.md` — read in full; compare-link format confirmed from lines 288–293
- `docs/ai-suggestions.md` — read in full; confirmed it IS updated to describe `--from-suggestion` and `last_suggestions.json`
- `pending-lessons.md` — read in full; confirmed the docs-drift lesson and the append format
- `phase-summaries/phase-1-1.md`, `phase-2-1.md` — read for naming convention and register
- `handoff.md` — read for phase-summary naming convention and internal doc list
- `ai-development-practices/index.md` — read for directory structure (6 files)
- `collaboration-retrospective/index.md` — read for directory structure (6 files)
- `CONTRIBUTING.md` — read for structure
- Glob of `docs/` — confirmed 8 files exist

**Re-verification commands (run from repo root):**
```bash
# Confirm spec is committed (not gitignored)
git ls-files fly-tying-tracker-spec.md

# Confirm internal doc list in .gitignore
grep -A 12 "Internal project documents" .gitignore

# Check ai-suggestions.md drift status
grep -n "from-suggestion\|last_suggestions" docs/ai-suggestions.md | head -10

# Confirm pending-lessons append format
head -15 pending-lessons.md

# Confirm phase-summary naming convention
ls phase-summaries/
```
