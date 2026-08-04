---
name: flytie-change-control
description: >-
  The change-control constitution for flytie: how any change is classified,
  which quality gates must be green before it lands or ships, the non-negotiable
  rules you can never route around, and the release-tag procedure. Covers the
  feature-phase / hardening-pass / mechanical-edit / docs-only / release change
  classes; the exact gate commands and their pass criteria; the four ratified
  hard-nevers (git immutability, no gate-weakening, no live-API tests, subagents
  never mutate git); and how to change the rules themselves. Use when you are
  about to modify flytie and ask "what process applies here", "what gates must
  pass before I commit/tag", "am I allowed to lower the coverage floor / skip a
  test / re-tag a release / force-push", "how do I cut a release", "do I need
  maintainer sign-off for this", or when reviewing whether a proposed change
  respects project discipline.
---

# flytie change control

The definitive answer to: *"I want to change something in flytie — what process
applies, what gates must be green, and what am I never allowed to do?"*

This is the governance layer. It does not teach you how to run reviewers (see
`flytie-subagent-orchestration`), how to cut a release step-by-step (see
`flytie-run-and-operate`), or what counts as a good test (see
`flytie-validation-and-qa`). It tells you which process a given change requires,
the gates that must pass, and the rules that have no override.

Date-stamped facts below are current as of **2026-07-02, flytie v0.2.1** (on
PyPI). Re-verify volatile numbers with the commands in *Provenance* before
relying on them.

Terms defined at first use: **gate** = an automated check that must pass before a
change is allowed to proceed; **regression test** = a test written to fail if a
specific fixed bug ever comes back; **reviewer / audit subagent** = a fresh
Codex instance given a self-contained brief and no conversation history, used to
review code or docs (Cowork sessions only — a plain-clone contributor plays this
role themselves or via PR review); **finding** = a single issue a reviewer
reports, tagged with a severity.

---

## 1. Classify the change first

Every change in flytie belongs to exactly one of these classes. The class
determines the process. Pick it before you write code.

| Class | Examples | Required process |
|---|---|---|
| **(a) Feature phase** | A new `flytie` command or capability (`undelete`, `stats`, `material dedupe`, `--from-suggestion`). One coherent feature (or a bundle touching non-overlapping surfaces). | Implement → run a **three-reviewer pass** (one skeptic + two rotating domain specialists) → fix **every** CRITICAL / HIGH / MEDIUM finding, each with a paired regression test → write the phase summary at `phase-summaries/phase-X-Y.md` (X = minor version, Y = phase number within it — naming convention in `flytie-docs-and-writing`). See `flytie-subagent-orchestration` for reviewer mechanics. |
| **(b) End-of-version hardening pass** | v0.1.1, v0.1.2, v0.2.0, v0.2.1 pre-tag hardening. | **Multi-lens audit** (2–3 orthogonal lenses: spec-drift + contributor-friction + optionally CI-as-contract) → report findings ranked by severity, **naming false alarms explicitly** → maintainer picks impact-ranked slices → execute a slice → report → maintainer picks next → tag when done. |
| **(c) Mechanical batched edits** | Applying N one-line audit fixes; a doc-split; renaming across files. | Confirm scope with the maintainer **first**, then execute the whole batch in one go and report at the end. No per-edit check-in once scope is agreed. |
| **(d) Docs-only change** | README / CONTRIBUTING / `docs/` / CHANGELOG / spec wording, no code. | No reviewer pass required. Still runs the hygiene gates (pre-commit hygiene hooks apply). Keep the docs-of-record in sync (see `flytie-docs-and-writing`). |
| **(e) Release / tag** | Cutting `v0.2.2`, publishing to PyPI. | All quality gates green + version bump + CHANGELOG section + docs updated, then push a `v*` tag. See §5 and `flytie-run-and-operate`. |

If a change looks like it spans classes (e.g. "a feature plus the release"),
split it: build under (a), then release under (e). **Do not conflate a hardening
pass with a feature phase** — phase-shaped work is for new features; pass-shaped
work is for hardening an existing surface before a tag.

---

## 2. Check-in cadence — don't decide silently

Non-trivial multi-step work follows a propose-then-execute rhythm:

- **Before non-trivial implementation, propose a plan with impact-ranked slices
  and let the maintainer pick.** Do not pick for them. Slices are typically
  grouped A (CLI/safety) / B (help-text polish) / C (docs) / D (optional polish).
- **Report at slice boundaries.** When one slice lands (tests green, result
  describable in a paragraph), report what landed and what's next; await
  direction.
- **Mechanical pre-confirmed batches are the exception** — execute the batch, then
  report once at the end (class (c) above).
- **Surface judgment calls; never resolve them silently.** If a change turns on
  taste or maintainer preference rather than correctness, ask.

### The D11 cautionary tale (v0.1.1) — why silent resolution is banned

During the v0.1.1 hardening pass, a finding proposed renumbering an `(imported)`
suffix on pattern names. The maintainer **rejected** it: the decision turned on
user taste, not optimization. An autonomous agent would have implemented the
renumbering **and pinned the wrong choice with a regression test** — cementing a
maintainer-rejected decision into the contract, where a later audit would treat
it as settled. The lesson, verbatim from the practices catalogue:

> "An agent making the call alone would likely have implemented the renumbering
> and added a regression test pinning it."

This is why every judgment call goes to the maintainer, and why regression tests
are powerful enough to be dangerous when aimed at the wrong decision. The same
pass shows the upside: the maintainer kept slices A + C, deferred B, and picked
D12 while rejecting D11 — exactly the strategic prioritization a fully autonomous
run would have gotten wrong.

---

## 3. Quality gates — must all be green before any tag

These are the gates. All must pass before a `v*` tag is pushed; CI re-runs them
on every PR (`ci.yml`) and on the release path (`release.yml`).

### Plain-clone form (a normal `git clone` + terminal)

Run from the repo root after `pip install -e ".[dev,pdf,ai]"`:

```bash
ruff format --check src tests
ruff check src tests
mypy src
pytest --cov=src/flytie --cov-report=term-missing   # 85% floor via fail_under
pytest -m smoke                                       # exactly 5 tests, <5s
```

Plus the cold-start budget (regression guard on the import graph; heavy deps
stay lazy — importtime walkthrough in `flytie-diagnostics-and-tooling` §5):

```bash
# best-of-5 `flytie --version` must be under 600 ms
for i in 1 2 3 4 5; do /usr/bin/time -p flytie --version; done
```

### Cowork-session form (sandbox only)

**Cowork sessions only:** the sandbox mount trips `sqlite3.OperationalError: disk
I/O error` on pytest/mypy default cache dirs. Redirect them:

```bash
pytest -p no:cacheprovider -o cache_dir=/tmp/.pytest_cache --cov=src/flytie --cov-report=term-missing
mypy --cache-dir /tmp/.mypy_cache src
```

These flags are a workaround for the FUSE mount, **not** part of the contract —
never bake them into `pyproject.toml` or CI.

### Gate reference

| Gate | Command | Pass criterion | What failure means |
|---|---|---|---|
| Format | `ruff format --check src tests` | `... files already formatted` | Unformatted code. Run `ruff format src tests` (pre-commit does this automatically on commit). |
| Lint | `ruff check src tests` | `All checks passed!` | Lint violation. Auto-fixable ones: `ruff check --fix`. Non-auto-fixable: address by hand. |
| Types | `mypy src` | `Success: no issues found` | Type error. mypy runs in `strict` mode with `warn_unused_ignores`. |
| Coverage | `pytest --cov=src/flytie --cov-report=term-missing` | All tests pass **and** total coverage ≥ 85% (`fail_under = 85`) | A test failed or coverage dropped below 85%. Add tests — **never** lower the floor or widen the omit-list (see §4). Expect ~380 passed, ~5 PDF skips when WeasyPrint/Pango is absent (that skip is expected, not a failure). |
| Smoke | `pytest -m smoke` | Exactly **5** tests pass in under 5 s | The 5-test happy-path contract. A count other than 5 means the marker set drifted — a regression test in `tests/test_v0_1_2_fixes.py` asserts the exact count. |
| Cold start | best-of-5 `flytie --version` | Under **600 ms** | A heavy import crept into the top-level graph (e.g. eager `import weasyprint`/`anthropic`/`alembic`). Diagnose with `python -X importtime -m flytie --version 2>importtimes.log`. |

**Live-verified 2026-07-02 (v0.2.1, Cowork sandbox):** `pytest -m smoke` →
`5 passed, 2 skipped, 378 deselected` in ~1.1 s; best-of-5 `flytie --version`
wall-clock 0.21–0.30 s; `__version__ = "0.2.1"`; `pyproject.toml` has
`fail_under = 85`.

The pre-commit hooks enforce most of this locally: commit-stage runs `ruff
format` + `ruff check --fix` + hygiene; pre-push runs the full suite at
`COLUMNS=80` (a narrow-terminal stress check for Rich-wrap fragility). Install
them once: `pre-commit install --hook-type pre-commit --hook-type pre-push`.

---

## 4. Non-negotiables — rule, why, and the incident behind it

These have no override without explicit maintainer sign-off (and some have no
override at all). Each exists because a real incident, near-miss, or ratified
decision made it load-bearing.

| Rule | Why | Incident / origin |
|---|---|---|
| **Tag must equal package version** | A mismatched tag uploads an irreplaceable wrong release; PyPI files are immutable and can only be yanked, never replaced. | `release.yml` `build` job greps `__version__` from `src/flytie/__init__.py`, prefixes `v`, and fails the build if `GITHUB_REF_NAME` differs. Added after the v0.1.1 release reviewer flagged the mis-tag risk. |
| **Coverage floor stays at 85% with the exact omit-list** | Naive coverage measurement read low because inert `*_old.py` FUSE placeholders and subprocess-only Alembic migrations dragged the number down. The omit-list excludes only genuinely-inert code so 85% measures real modules (real coverage is 89.2% in a sandbox without `[pdf]` extras (weasyprint absent drags `pdf/export.py`); higher with all extras installed as in CI; the enforced floor is 85%). | `[tool.coverage.run] omit` lists the `*_old.py` placeholders, `__main__.py`, and `migrations/env.py` + `versions/*.py`; `[tool.coverage.report] fail_under = 85`. **Never** lower the floor or widen the omit-list to make a gate pass. |
| **Smoke marker = exactly 5 tests** | `>= 5` would let slow tests silently drift into the fast-feedback suite and erode the "3-second sanity check" budget. | Exactly five tests carry `@pytest.mark.smoke` (init success, add+list round-trip, view, shop dedupe, export-db→import-db round-trip). `tests/test_v0_1_2_fixes.py` asserts the count. Marking a sixth requires deliberately updating that regression — not loosening it. |
| **Cold-start budget = 600 ms** | Guards the import graph; a new top-level import of a heavy dep (weasyprint/anthropic/alembic — all lazy today) would regress startup. | Spec NFR §4. Originally 300 ms; raised to 600 ms in v0.1.2 **with documented rationale** (300 ms was flaky on CI hardware without improving UX; the gate's job is regression detection, not chasing 100 ms). |
| **API key is env-only** | Leaking a key to disk, logs, or the config surface is an unrecoverable secret exposure. | `ANTHROPIC_API_KEY` is read only from the environment; never written to disk, never logged, never in error strings, and **excluded from `_CONFIG_KEYS`** in `src/flytie/cli.py` (verified: the three config keys are `database.path`, `pdf.template`, `pdf.output_dir` — no key entry). `flytie config show`/`info` never surface it. |
| **Privacy boundary: only names + hooks + material names to the API** | Sending instructions, notes, or the full DB to a third-party API is a privacy breach. | `build_prompt` in `src/flytie/ai/suggest.py` is the boundary; `_grounding_block` includes only pattern name, hook size, and (capped) material names — deliberately not instructions or notes. Any new `Pattern` field must pass an explicit privacy review before entering the prompt. |

### The four ratified hard-nevers (maintainer, 2026-07-02)

1. **Git / release immutability.** Never force-push `main`. Never re-tag or reuse
   a published version — PyPI files are immutable; bump the patch instead. Never
   push with `--no-verify` (it skips the pre-push gate suite).
2. **No gate-weakening.** Never lower the coverage floor, widen the coverage
   omit-list, loosen the smoke exact-count contract, or relax the cold-start
   budget to make a gate pass. Any gate change requires explicit maintainer
   sign-off (§6).
3. **No live-API tests.** AI tests use injected fake streamers only (the
   `Streamer` seam replays canned chunks). The suite never calls the real
   Anthropic API — no key, no network, in CI or locally.
4. **Subagents never mutate git.** Commits, tags, and pushes happen only from the
   top-level session (Cowork sessions only — this constrains reviewer/audit
   subagents). A reviewer reads and reports; it does not stage, commit, or tag.

There is no legitimate path that routes around these. If a task seems to require
one, the task is wrong or needs maintainer sign-off — stop and ask.

---

## 5. Release procedure — gate summary

Before pushing a `v*` tag, all of the following must be true. This is the
pre-flight checklist; `flytie-run-and-operate` has the full step-by-step runbook.

- [ ] `__version__` in `src/flytie/__init__.py` **matches** the tag you will push
      (tag `v0.2.2` ⇔ `__version__ = "0.2.2"`). `release.yml` fails the build on
      mismatch.
- [ ] `CHANGELOG.md` has a `[X.Y.Z] — YYYY-MM-DD` section (Keep-a-Changelog
      format: Added / Changed / Removed / Fixed), and the `[Unreleased]` compare
      link at the bottom is updated.
- [ ] **All quality gates green** (§3): ruff format check, ruff check, mypy,
      pytest with the 85% coverage floor, `pytest -m smoke` = 5, cold-start
      under 600 ms.
- [ ] Docs of record updated for any feature change: `README.md`,
      `CONTRIBUTING.md`, `docs/`, and — if an audit produced a DOCUMENT-class
      finding — the spec backported (see `flytie-docs-and-writing`).
- [ ] The tag is a **new** version never published before (hard-never #1).

The tag push triggers `release.yml`: it re-runs lint + mypy + the coverage-gated
test suite across the Python 3.10 / 3.11 / 3.12 matrix, verifies tag-vs-version,
builds sdist + wheel, and publishes via PyPI Trusted Publishing (OIDC — no stored
token).

---

## 6. How to change the rules themselves

The gates and the spec are living, not frozen — but they change through a
controlled path, never by an autonomous agent editing a threshold to make a red
gate green.

- **Gate changes require explicit maintainer sign-off.** Lowering the coverage
  floor, widening the omit-list, changing the smoke count, or relaxing the
  cold-start budget are all gate changes. Propose the change with rationale; wait
  for the maintainer to approve. Never do it as a side effect of "getting the
  build to pass."
- **Spec deviations get backported, not hidden.** When the project knowingly
  accepts a deviation from `fly-tying-tracker-spec.md` (an audit DOCUMENT-class
  finding), backport the decision into the spec. A living spec is a feature; a
  fossilized spec is a smell. Examples already backported: Python 3.10+ target
  (spec said 3.11+), the superset `MATERIAL_CATEGORIES`, TOML-over-YAML, the
  flag-driven-over-interactive design, env-only API-key policy.
- **The 300 ms → 600 ms cold-start raise is the precedent.** In v0.1.2 the
  budget was raised because the tighter number was flaky on CI hardware without
  improving UX. The change was made **with the rationale documented in spec NFR
  §4** and maintainer agreement — not silently, and not to paper over a
  regression. That is the template for any future gate change: name the reason,
  document it in the spec/config, get sign-off.

---

## When NOT to use this skill

| If you are trying to… | Use instead |
|---|---|
| Actually run the reviewer / audit subagents (personas, lenses, briefing, triage) | `flytie-subagent-orchestration` |
| Follow the full step-by-step release / publish runbook | `flytie-run-and-operate` |
| Recreate the dev environment or fix an environment trap | `flytie-build-and-env` |
| Diagnose why a gate is *failing* (symptom → cause) | `flytie-debugging-playbook` |
| Decide what makes a good test / what counts as evidence | `flytie-validation-and-qa` |
| Add or change a config axis or CLI flag | `flytie-config-and-flags` |
| Update docs of record, CHANGELOG, or the spec | `flytie-docs-and-writing` |
| Understand a load-bearing design invariant | `flytie-architecture-contract` |

This skill answers "what process and what rules"; the siblings answer "how to do
the thing."

---

## Provenance and maintenance

- **Date:** 2026-07-02. **Project version:** flytie v0.2.1 (on PyPI).
- **Sources consulted (working-copy paths; some are gitignored and absent in a
  fresh clone — substance embedded above):** `AGENTS.md` (workflow shapes,
  cadence, gates, safety), `handoff.md` (state, history, incidents),
  `ai-development-practices/patterns.md` §2.11 (impact-ranked-slice pattern; D11
  story, quoted), `.pre-commit-config.yaml`, `.github/workflows/ci.yml` and
  `release.yml`, `pyproject.toml` (`[tool.coverage.*]`, `[tool.ruff.*]`,
  `[tool.pytest.ini_options]`, `[tool.hatch.version]`), `src/flytie/cli.py`
  (`_CONFIG_KEYS`), `src/flytie/ai/suggest.py` (`build_prompt`,
  `_grounding_block`), `fly-tying-tracker-spec.md` §4 (NFR) and §10.
- **Deeper reading, if present in your working copy** (gitignored — not in a
  plain clone): `handoff.md`, `ai-development-practices/`,
  `collaboration-retrospective/`, `phase-summaries/`, `subagent-brief-templates.md`.

### One-line re-verification commands (run at repo root)

```bash
grep -n 'fail_under' pyproject.toml                                  # expect: fail_under = 85
grep -n '__version__' src/flytie/__init__.py                         # tag must match this
grep -nA3 '_CONFIG_KEYS' src/flytie/cli.py                           # must NOT include any api key
pytest -m smoke -q                                                   # expect exactly 5 passed
grep -n 'Verify tag matches package version' .github/workflows/release.yml   # tag-vs-version gate present
grep -n '600 ms\|600ms' fly-tying-tracker-spec.md                    # cold-start budget documented
```
