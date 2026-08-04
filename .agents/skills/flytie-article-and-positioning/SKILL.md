---
name: flytie-article-and-positioning
description: >-
  External positioning for flytie: what the project can claim publicly (agentic-coding
  article series + PyPI package), what must be proven before claiming it, and where the
  evidence lives. Use when drafting an article or blog post from this project, deciding
  whether a workflow practice is claimable as novel vs. standard-well-executed, hunting a
  verbatim maintainer quote, fact-checking a workflow claim against a repo artifact,
  describing flytie publicly, or writing PyPI/README positioning copy. Enforces the
  no-oversell, evidence-traced, quotes-verbatim discipline the series depends on.
---

# flytie: article & public positioning

This skill governs what flytie says about itself in public — the article series and the
PyPI listing — and the standard of proof every public claim must meet. It is a runbook,
not an essay. The core rule: **no oversell.** The article series' credibility is the
product; a single unprovable claim damages it more than ten unmade ones.

Definitions used once here: *thesis* = an article-ready claim recorded in
`collaboration-retrospective/theses.md`. *Lens* = a single-purpose reviewer brief
(spec-drift, contributor-friction, CI-as-contract). *Artifact* = a concrete, checkable
repo object (test file, config stanza, doc section, git tag) that grounds a claim.
*Gitignored internal docs* = `handoff.md`, `ai-development-practices/`,
`collaboration-retrospective/`, `phase-summaries/`, `AGENTS.md` — project memory that
doubles as article source and is NOT in the public repo.

## When NOT to use this skill

- Deciding *how* internal docs update (cadence, which file) → `flytie-docs-and-writing`.
- The actual reviewer brief templates, severity rubric, triage protocol (the reproducible
  methodology a reader would copy) → `flytie-subagent-orchestration`.
- The session-cost campaign numbers and interventions → `flytie-token-economics-campaign`.
- Settled incident facts (FUSE, WeasyPrint SIGSEGV) → `flytie-failure-archaeology`.
- Evidence/QA standards for internal gating (not publication) → `flytie-validation-and-qa`.
- Open problems that could *become* claimable → `flytie-research-methodology-and-frontier`.

This skill is about the *outward-facing* claim and its proof. Use those siblings for the
mechanics; use this one to decide what is publishable and how to defend it.

## 1. The two public surfaces

flytie has two public faces, and they must be positioned differently.

| Surface | What it is | Honest positioning |
| --- | --- | --- |
| **Article series** (primary ambition) | Tech-forum writing on agentic-coding methodology, sourced from the gitignored internal docs. The maintainer has confirmed the "beyond state of the art" ambition is the *methodology*, not the CLI features. | The workflow is the claim. Every methodology claim traces to an artifact or a verbatim exchange. Negatives (failed experiments, false alarms) are reported alongside wins. |
| **PyPI package** (secondary) | `flytie` on PyPI, v0.2.1 (as of 2026-07-02). Single-maintainer local-first fly-tying CLI. | Modest and accurate. Verified `pyproject.toml` classifiers: `Development Status :: 3 - Alpha`; a 0.x version; single author (Finn Gidden). Do NOT describe it as production-ready, battle-tested, or feature-complete. It is an alpha tool that exists partly to generate the article material. |

**PyPI/README copy rules.** State the alpha status. State Python `>=3.10`. Do not imply
scale, adoption, or a team. The interesting story is the *how it was built*, not the
tool's maturity — link the two honestly rather than inflating the tool.

## 2. Source-material map

Which internal file feeds which article content. All paths below are gitignored — their
*contents* are article source, not public.

| Internal file | Feeds | Nature |
| --- | --- | --- |
| `collaboration-retrospective/theses.md` | The claims themselves | 24 numbered theses (see §3). The header still says "16" — stale; count the entries, do not trust the header. |
| `collaboration-retrospective/revisions.md` | Workflow-evolution narrative | 10 numbered Revisions (1–10) as of 2026-07-02. Header prose says "eight"/"three times" — stale; the file has ten. |
| `collaboration-retrospective/phases.md` | Incident/phase narratives | Per-phase story. (Read host-side; EDEADLK on bash.) |
| `collaboration-retrospective/vignettes.md` | Color, small human moments | e.g. the "改ing" kanji-glitch vignette; the v0.2.1 five-moment set. Good for openings/asides. |
| `collaboration-retrospective/practices.md` | Cross-cutting practice narrative | (Read host-side; EDEADLK on bash.) |
| `ai-development-practices/patterns.md` | The practice catalogue | Per-practice §2.N entries with cost/value observations. The reproducible detail lives here + in `flytie-subagent-orchestration`. |
| `ai-development-practices/assessment.md` | Lessons, least-effective notes, `quotes.md` proposal | §4 candidate practices. |
| `ai-development-practices/open-questions.md` | What is NOT yet claimable | §8; each entry marked answered or still-open. |
| `phase-summaries/*.md` | Per-phase detail | 8 files (phase-1-1..1-6, phase-2-1, phase-2-2) as of 2026-07-02. |
| `CHANGELOG.md` | Public-facing timeline | The one *public* source in this list; safe to quote directly. |

**Verified counts (2026-07-02, v0.2.1):** theses.md = **24 theses** (1–24, no gaps);
revisions.md = **10 Revisions** (1–10). The context brief's "1–16+/1–8+" estimate
undercounts both — always recount before citing a number in an article.

## 3. The theses inventory

The 24 theses with a one-line summary and the repo artifact that grounds each. "Evidence"
means a checkable object; where it is weak, it says so.

| # | Summary | Evidence artifact (verified unless noted) |
| --- | --- | --- |
| 1 | The workflow is the product, not one clever prompt | Whole repo history; phase-summaries/. Narrative, not a single artifact. |
| 2 | Independent multi-agent review produces real signal (convergence) | Reviewer reports (internal); convergence points named in revisions.md §5. Evidence is the internal record, not a test — label as reported. |
| 3 | Tooling failures deserve post-mortems | FUSE playbook in `AGENTS.md`; `flytie-failure-archaeology`. |
| 4 | Revise the process from evidence | revisions.md 1–10 (the whole file is the artifact). |
| 5 | A good agent is a workflow collaborator (proposes practices) | Quoted proposals in revisions.md §"agent as source of proposals". Verbatim quotes. |
| 6 | Human-in-loop at expensive/uncertain moments | Phase 5 estimate-checkpoint quotes, revisions.md Revision 3. |
| 7 | A user is a reviewer (friction-log as 4th reviewer) | libpango bug, `init` bug, `--out` bug (in CHANGELOG/phase-summaries). |
| 8 | Reviewer failure modes are diagnostic | Named patterns in `patterns.md`: "confidently wrong" / "correctly-wrong-about-unfaithful-sandbox". Verified present. |
| 9 | End-of-version hardening has its own structure | v0.1.1/v0.1.2/v0.2.1 CHANGELOG sections; `test_v0_1_1_fixes.py`, `test_v0_1_2_fixes.py`, `test_audit_fixes.py`. Verified. |
| 10 | Three-tier gating beats single-tier | `.pre-commit-config.yaml` (commit/push stages); `ci.yml` + `release.yml`. Verified via CHANGELOG 0.1.2. |
| 11 | Catalogued lessons compound *backward* | `tests/conftest.py` `_wide_cli_runner_env` autouse fixture (verified, line 86); caught latent wrap bugs in prior tests. Strong. |
| 12 | try/except only catches Python exceptions; native crashes need subprocess | WeasyPrint SIGSEGV subprocess-probe pattern, CHANGELOG 0.1.2 "Subprocess probe". `flytie-failure-archaeology`. |
| 13 | Explicit beats implicit for env-varying heuristics | `[tool.ruff.lint.isort]` `known-first-party`/`known-third-party` in `pyproject.toml` (verified, lines 172–181). Strong. |
| 14 | Markers as contracts, not conventions | `tests/test_v0_1_2_fixes.py::test_smoke_marker_collects_exactly_five_happy_path_tests` — asserts `collected == 5` (verified, line 86). Strong. |
| 15 | Operating cost is a workflow constraint | Revisions.md Revision 8; `flytie-token-economics-campaign`. Numbers are observed-once — label as such. |
| 16 | A living spec is a feature | Spec NFR §4 300→600 ms backport, CHANGELOG 0.1.2 + `pyproject.toml` `fail_under` context. Cold-start test `test_cli_cold_start_under_budget` (verified). |
| 17 | Doc cost is a function of file granularity, not project size | The v0.2 split of `ai-development-practices/` + `collaboration-retrospective/` into ~12 files. The ~10x figure is observed-once — label. |
| 18 | Workflow-improvements-before-features is a legit release shape | revisions.md Revision 9. Narrative; the "pays off after 3–4 updates" figure is a projection, not a measurement — flag. |
| 19 | Trust-but-verify works at file granularity, not anchor granularity | The doc-split caught 4 stale refs a subagent's anchor-matching missed (revisions.md §19). Reported, not test-backed. |
| 20 | Operating-instructions deserve their own file | The `AGENTS.md` / `handoff.md` / practices / retrospective separation itself. Structural, self-evident. |
| 21 | Graceful degradation masks gaps (importorskip hid 22 PDF tests 4 releases) | `pdfminer.six` added to `[dev]`, CHANGELOG 0.2.0; `pyproject.toml` line 70 comment. Verified. |
| 22 | Bundling non-overlapping features into one review trades depth for breadth | v0.2.0 bundled review; cross-feature bugs in CHANGELOG 0.2.0 Fixed. Reported. |
| 23 | Any new assertion on existing output is a potential regression | `test_v0_2_phase1.py::test_merge_duplicate_different_units_keeps_target` — `len(result.warnings) == 2` after a new warning (verified, line 542). Strong worked example. |
| 24 | A third audit lens pays for itself when infra accumulates | CI-as-contract lens caught `release.yml` missing Python matrix; CHANGELOG 0.2.1 "CI `COLUMNS=80`" + patterns.md §2.22. Verified. |

**Weak-evidence theses to hedge in writing:** 1, 2, 15, 17, 18, 19, 22 rest on the
internal narrative or observed-once numbers, not a repeatable measurement or a test. Claim
these as *experience-report observations*, not established results.

## 4. Honest novelty assessment

Three buckets. This is judgment, made explicit and hedged. Do not upgrade a claim between
buckets without new evidence.

### (a) STRONGEST — uncommon in public writing AND well-evidenced here

Claimable as genuinely interesting, still framed as "what we did," not "what everyone
should do":

- **Convergence across contextless reviewers as a priority signal** (thesis 2) — two/three
  independent agents landing on the same bug ranks it. Uncommon to see written up rigorously.
- **Orthogonal-lens end-of-version audits** — spec-drift + contributor-friction +
  CI-as-contract (theses 9, 24; Revisions 5, 10). The parallel-when-orthogonal rule is a
  crisp, transferable heuristic.
- **Marker-as-contract with exact-count regression** (thesis 14) — a test asserting
  `smoke collected == 5`. Turning a convention into a checked contract is rarely written up.
- **Docs-content smoke tests** as a regression class (patterns.md §2.10).
- **Catalogued lessons compounding backward** (thesis 11) — a documented lesson applied as a
  structural fix (the conftest fixture) that retroactively protects pre-existing code. The
  strongest single artifact-backed story.
- **Reviewer failure-mode taxonomy** (thesis 8) — "confidently wrong about an external fact"
  vs. "correctly wrong because the inspected sandbox wasn't faithful."
- **Token-economics as a first-class workflow variable with measured interventions**
  (theses 15, 17; Revision 8). Rare to treat session cost as an engineered constraint.

Hedge even these: "uncommon in *public writing*" is a claim about the literature we've seen,
not a proof of first-invention. Never write "first" or "nobody has."

### (b) SOLID but known territory — claim as experience report, not invention

These are established practices; write "here's how it played out on flytie," never "we
invented":

- Multi-agent / independent code review.
- Regression-test-per-fix.
- Spec-drift audits.
- Three-tier gating (commit/push/CI).
- Living-spec backports.

### (c) NOT YET CLAIMABLE — open/candidate; must be proven first

From `open-questions.md` §8, still-open as of 2026-07-02. **Rule: an open question becomes
claimable only after the experiment runs and the result is recorded.**

- Four-reviewer scaling (three works; four never tried).
- Structured reviewer JSON output (proposed, not built).
- Per-phase token budgets (proposed, not measured as a standing practice).
- Pending-lessons signal filter — does the scratch-file "does this survive consolidation?"
  gate actually raise lesson quality? (open; v0.2.1 is only the 2nd data point.)
- Rotating the audit lens pair vs. keeping spec-drift+friction as standard (open).
- `quotes.md` as a standing practice (candidate only — see §6; the file does not yet exist).

If you find yourself wanting to claim one of these, stop and check `open-questions.md`: if
the entry is not marked "Answered," it is bucket (c).

## 5. Evidence standard for any public claim

Every workflow claim in an article MUST satisfy all of:

1. **Traces to a named artifact** — a test file, config stanza, doc section, or git
   commit/tag — OR to a verbatim quoted exchange. If you cannot name the artifact, cut the
   claim.
2. **Numbers are labeled by strength** — *observed-once* (a single session's token figure,
   the ~10x doc-cost drop, the "pays off after 3–4 updates" projection) vs.
   *measured-repeatedly* (the smoke count, the coverage floor). Never present an
   observed-once number as if it were a benchmark.
3. **Negatives are included** — failed experiments and false alarms ship alongside wins. The
   FUSE incident, the reviewer-confidently-wrong finding, the ruff `--fix` thrash, the
   importorskip coverage gap. The series' credibility depends on the negatives being visible.
4. **No gitignored content leaked without approval** — an article may *describe* what an
   internal doc says, but quoting internal-doc text, transcript excerpts, or maintainer
   messages requires maintainer sign-off. Flag every such quote or internal detail for
   sign-off before publication.

If a claim fails any of these, it is not publishable yet.

## 6. Quote discipline

Maintainer quotes are article source material. This is project canon.

- **Verbatim always.** Never paraphrase when attributing. If the internal record already
  marks a quote *(paraphrased)* (some v0.2.1 quotes are, due to a compaction boundary),
  carry that label through — do not present a paraphrase as verbatim.
- **Mark ellipses** with `...` when trimming; never silently drop words that change meaning.
- **Attribution:** "the maintainer" or "Finn" per his stated preference — confirm which he
  wants for a given piece before publishing.
- **Keep a quotes ledger while drafting.** `assessment.md` §4 proposes a `quotes.md` for
  verbatim capture. **This is a candidate practice — the file does NOT yet exist** (verified
  2026-07-02). Label it as a candidate if you mention it; do not describe it as an
  established artifact.

## 7. Reproducibility standard

- **Methodology claims** must carry enough procedural detail that a reader could run the same
  pattern on their own project: the reviewer brief templates, the severity rubric, the triage
  protocol. Those live in `flytie-subagent-orchestration` — cite/embed from there, don't
  re-derive.
- **Code claims** must be version-pinned ("as of v0.2.1") with the exact command or file
  path. A claim about behavior that isn't reproducible at a named version is a bug report,
  not an article claim.

## 8. Pre-publication checklist

Before any article or public copy ships, confirm every item:

- [ ] Every workflow claim traces to a named artifact or a verbatim exchange (§5.1).
- [ ] Numbers labeled observed-once vs. measured-repeatedly (§5.2).
- [ ] Negatives / false alarms included, not just wins (§5.3).
- [ ] Quotes verbatim, ellipses marked, `(paraphrased)` labels preserved (§6).
- [ ] Attribution style ("Finn" vs. "the maintainer") confirmed with the maintainer (§6).
- [ ] No gitignored file *contents* quoted without maintainer sign-off (§5.4).
- [ ] Version + date stamps present on all volatile facts (§7).
- [ ] PyPI/alpha status stated honestly where the tool is described (§1).
- [ ] Novelty claims bucketed correctly; nothing from open-questions §8 claimed as done (§4).
- [ ] Maintainer sign-off obtained on the final draft.

## Provenance and maintenance

- **Date:** 2026-07-02. **Project version:** flytie 0.2.1 (PyPI, Alpha).
- **Sources read for this skill:** `collaboration-retrospective/theses.md` (24 theses),
  `.../revisions.md` (10 Revisions), `.../vignettes.md`; `ai-development-practices/patterns.md`,
  `.../assessment.md`, `.../open-questions.md`; `pyproject.toml` (classifiers, ruff isort);
  `CHANGELOG.md`; `tests/conftest.py`, `tests/test_v0_1_2_fixes.py`, `tests/test_v0_2_phase1.py`.
- **Re-verification one-liners** (run from repo root):
  - Thesis count: `grep -cE '^[0-9]+\. \*\*' collaboration-retrospective/theses.md` (expect 24; some are blank-line separated — cross-check by eye).
  - Revision count: `grep -c '^### Revision' collaboration-retrospective/revisions.md` (expect 10).
  - PyPI status: `grep 'Development Status' pyproject.toml` (expect `3 - Alpha`).
  - Smoke exact-count contract: `grep 'collected == 5' tests/test_v0_1_2_fixes.py`.
  - Backward-compounding fixture: `grep -n '_wide_cli_runner_env' tests/conftest.py`.
  - `quotes.md` still a candidate: `ls **/quotes.md 2>/dev/null` (expect: no output).
- **Staleness watch:** theses.md and revisions.md have stale header counts ("16", "eight").
  Always recount; never cite a header number. Re-verify counts every release.
