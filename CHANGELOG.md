# Changelog

All notable changes to **flytie** are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.2.1] — 2026-06-09

### Added

- **`flytie material dedupe`** — scan the materials table for likely
  duplicates using Levenshtein edit distance and Jaccard token overlap.
  Interactive flow: review each candidate pair, choose which name to keep,
  and the other is merged away. Supports `--threshold` (default 0.6) and
  `--dry-run`. Shorthand inputs `s`/`q` accepted alongside `skip`/`quit`.
- **`flytie add --from-suggestion <n>`** — create a draft pattern from a
  saved AI suggestion by its number (as shown by `flytie suggest`).
  Materials are added with category `other`; a draft notice reminds the
  user to refine via `flytie edit`. Supports all the same CLI overrides as
  `--from-file`. Cannot be combined with `--from-file`.
- **Suggestion persistence** — `flytie suggest` now saves results to a JSON
  file so `--from-suggestion` can reference them without re-querying the API.

### Changed

- `flytie suggest` hint text now reads `flytie add --from-suggestion <n>`
  instead of the generic `flytie add`.
- `flytie add` `NAME` argument is now optional when `--from-suggestion` is
  used (the suggestion's name is used by default).

### Fixed

- **Hook placeholder warning** — `--from-suggestion` with a suggestion that
  has no hook size now warns that hook `"0"` is a placeholder, rather than
  storing it silently.
- **Stale dedupe candidates** — the interactive dedupe loop now skips
  candidates whose materials were already merged away in an earlier step,
  instead of showing a confusing "Merge failed" error.
- **Unit-mismatch quantity warning** — `material merge` (and by extension
  `material dedupe`) now warns explicitly when a source quantity is
  discarded because the units differ from the target.
- **`save_suggestions` failure warning** — if saving suggestions to disk
  fails (e.g., full disk), a warning is printed instead of silently
  swallowing the error.
- **CI `COLUMNS=80`** — added to both `ci.yml` and `release.yml` test steps
  as defense-in-depth against Rich terminal-width wrapping bugs.

## [0.2.0] — 2026-06-08

Four user-facing features bundled into a single release. No schema migrations
required — existing databases work unchanged.

### Added

- **`flytie undelete <name>`** — restore a soft-deleted pattern to active
  status with its full version history intact. Closes the soft-delete
  contract gap where a deleted pattern's history was invisible.
- **`flytie stats`** — read-only library overview: active/deleted pattern
  counts, total materials/species/tags, top-5 most-used materials,
  most-tagged species, most-versioned patterns, and timeline info (oldest,
  newest, last edited, average versions per pattern). Deleted patterns are
  counted separately and excluded from all rankings.
- **`flytie material merge <from> <to>`** — rewrite all references from one
  material to another across every version of every affected pattern.
  Eliminates duplicates caused by inconsistent naming (e.g., "Grizzly
  Hackle" vs. "grizzly hackle"). Supports `--dry-run` for previewing.
  Duplicate-within-version collisions are handled (quantities summed when
  units match, target kept with a warning when they differ). Orphaned
  source materials are cleaned up automatically.

### Changed

- **`flytie diff` sorts materials alphabetically** before comparison, so
  reordering materials without changing them produces no diff. Only actual
  additions, removals, and quantity changes appear. Previously, moving a
  material to a different position in the list generated misleading diff
  lines.
- **Documentation updated** — `docs/commands.md`, `docs/quickstart.md`,
  `docs/index.md`, and `README.md` reflect the new commands.
  `docs/quickstart.md` gained three new sections (delete/undelete, stats,
  material merge).

### Fixed

- `stats` with only deleted patterns (no active) now correctly shows
  "No active patterns (N deleted)" instead of the misleading "No patterns
  yet" message, and reports accurate reference-table totals instead of
  zeros.
- `material merge` self-merge (same source and target) now exits with
  code 2 (input error) instead of code 1, consistent with other
  input-validation errors.
- `material merge --dry-run` now always shows the version-rows count, even
  when no active patterns are affected (previously hidden behind a guard).
- Material lookup in the merge path now uses `normalize_name` consistently
  with every other lookup in the codebase, instead of a bare
  `func.lower()` comparison.
- `pdfminer.six` added to the `[dev]` extra so PDF content-assertion tests
  run instead of silently skipping via `pytest.importorskip`.

[Unreleased]: https://github.com/finngidden/flytie/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/finngidden/flytie/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/finngidden/flytie/compare/v0.1.2...v0.2.0

## [0.1.2] — 2026-06-05

A CI / quality-hardening release. No user-visible behavior changes — every
fix is in the development workflow, test infrastructure, release pipeline,
or documentation. The goal was to make the project safer to contribute to
and harder to silently regress. No breaking changes; existing scripts and
databases keep working.

### Added

- **Three-tier pre-commit gating** via a new `.pre-commit-config.yaml`:
  commit-stage hooks (`ruff format`, `ruff check --fix`, basic file
  hygiene), pre-push hook running the full pytest suite at `COLUMNS=80`
  to surface Rich-wrap regressions before they reach CI, and
  [pre-commit.ci](https://pre-commit.ci) enrollment via the `[ci]` block
  for PR-time enforcement when a contributor pushes without installing
  hooks locally.
- **Coverage gate at 85%** via `[tool.coverage.report] fail_under` in
  `pyproject.toml`, enforced on both the PR path (`ci.yml`) and the
  release path (`release.yml`). A change that drops total coverage under
  85% fails the Test step before reaching publish.
- **`@pytest.mark.smoke`** attached to exactly five happy-path tests
  (`init` success, `add`+`list` round-trip, `view` renders, `shop`
  dedupes across patterns, `export-db` → `import-db` round-trip). A
  regression test asserts the marker carries exactly five tests so the
  "quick local feedback" promise from spec §7 holds.
- **Cold-start regression test** pinning best-of-5 `flytie --version`
  under 600 ms (spec NFR §4). Catches re-introduction of eager top-level
  imports of heavy dependencies like `weasyprint`, `anthropic`, or
  `alembic`.
- **Autouse `_wide_cli_runner_env` fixture** in `tests/conftest.py`
  patches `CliRunner.invoke` to default `env={"COLUMNS": "200"}` for
  every in-process CLI test. Eliminates the class of bug where Rich
  inserts a newline mid-substring (e.g., `JSON\nparse error`) and breaks
  assertions on the narrow GitHub Actions terminal.
- **`tests/_helpers.py`** with a `cli_help()` helper, replacing the
  ad-hoc per-file `_help()` functions that had drifted between modules.
- **`CONTRIBUTING.md`** covering local setup, the three-tier hook
  layout, what each CI workflow runs, pre-commit.ci enrollment, the
  formatter policy, and the coverage / smoke / known-third-party
  contracts.
- **Subprocess probe pattern** for native-library imports in the test
  suite. `weasyprint` can SIGSEGV on macOS when Anaconda Python meets a
  Homebrew Pango binary mismatch, which `try / except (ImportError,
  OSError)` cannot catch. A short subprocess `python -c "import
  weasyprint"` probe before the in-process import survives the segfault
  and lets the affected tests skip cleanly.

### Changed

- **`ruff` is the sole formatter.** `black` was dropped from `[project.optional-dependencies] dev`; `ruff format`
  produces Black-compatible output, so there's no behavior change for
  contributors who were used to Black.
- **`[tool.ruff.lint.isort]` adds explicit `known-first-party` and
  `known-third-party` lists.** Without them, ruff's import-classification
  heuristic produced different results on a developer's laptop vs. the
  GitHub Actions runner, causing CI to fail on import order after a
  clean local `ruff check --fix`. The explicit lists make classification
  deterministic across environments.
- **Spec NFR §4 startup budget raised from 300 ms to 600 ms.** The
  original target was tight on real CI hardware; the new budget gives ~2x
  headroom over the warm steady-state and keeps the gate meaningful for
  its real purpose (detecting regressions in the import graph) without
  flaking. Documented inline in the spec.
- **`release.yml` test job** now installs `.[dev,pdf,ai]` (with the
  native Pango library) and runs `pytest --cov` plus `ruff format
  --check`, so the release path exercises the PDF and AI code paths and
  enforces the same coverage and formatting gates as the PR path.
- **`ci.yml` lint step** runs `ruff format --check` and `ruff check`
  without `--fix`. Auto-fixing happens in the local pre-commit hooks
  (which persist the fix) and in pre-commit.ci (which pushes a follow-up
  commit). Auto-fixing in CI would only mutate the runner's ephemeral
  filesystem and silently weaken the gate.
- **`fly-tying-tracker-spec.md` §4 and §7** backported with the new
  600 ms cold-start budget and the realized smoke-marker contract.

[0.1.2]: https://github.com/finngidden/flytie/compare/v0.1.1...v0.1.2

## [0.1.1] — 2026-06-02

A hardening release. After a dual-lens audit pass — a prospective-user
friction log and a fresh spec-drift re-audit — eleven targeted improvements
were applied across the CLI surface, the docs, the spec, and the safety
guarantees. No breaking changes; existing scripts and databases keep working.

### Added

- **`flytie info`** — a single diagnostic command that prints the resolved
  database path, config file path, data directory, current Alembic schema
  revision, and pattern/tag/species counts. Safe to run before `flytie init`
  (reports "not initialized") and against an incompatible database (reports
  the situation rather than failing). The Anthropic API key is never
  displayed by this command — by design it lives only in the
  `ANTHROPIC_API_KEY` environment variable and is never written to disk.
- **`flytie tag list`** — new subcommand under `flytie tag` that lists every
  tag currently attached to a non-deleted pattern, with per-tag usage counts,
  so `flytie tag list` and `flytie list --tag <name>` never disagree about
  what's selectable.
- **Schema-compatibility safety check** — flytie now refuses to operate
  against a database whose Alembic revision this build doesn't recognize
  (typical scenario: user upgraded flytie, ran a migration, then downgraded).
  Surfaced as a new exit code 4 ("incompatible environment") with a recovery
  path that names `flytie export-db` on the newer install, then
  `flytie init --force` and `flytie import-db backup.json` on this one.
  This makes good on the spec §8 promise that the app refuses to start
  against a DB newer than its known head. `flytie info` deliberately bypasses
  the check so it remains usable as a diagnostic when other commands fail.
- **Pattern file format documentation** — new `docs/pattern-file-format.md`
  covering the JSON and TOML formats accepted by `flytie add --from-file`
  and `flytie edit --from-file`, with field tables for both pattern-level
  and material-object fields and a bulk-loading example. Cross-linked from
  `commands.md`, `migrating-from-notebook.md`, `index.md`, and the Typer
  help text on `--from-file` itself.

### Changed

- **`jinja2` is now a core dependency** (moved out of the `[pdf]` extra).
  `flytie export <name> --html` works on a bare `pip install flytie` — no
  extras, no native libraries — as the spec FR-5 has always promised. The
  `[pdf]` extra retains WeasyPrint and its native libpango/Cairo
  requirement. A core install is now sufficient to produce printable,
  styled HTML pattern cards that any browser can open and print.
- **CLI help text is comprehensive.** `flytie add --help` and
  `flytie edit --help` now describe `--material` (with the
  `name,category,quantity,unit` mini-grammar and the 13 valid categories
  inline), `--hook` (with both `14` and `12-16` range examples), `--tag`,
  and `--species`. `flytie shop --help` describes every selector
  (`--pattern`, `--tag`, `--species`, `--exclude`), with `--exclude`'s
  "drop materials you already own" use case called out by name.
- **`--hook is required` error rewritten.** Running `flytie add <name>`
  without `--hook` no longer produces the cryptic
  `--hook is required when --from-file is not supplied.` (which references
  a flag the user hasn't met). It now reads:
  *Hook size is required — pass --hook (e.g. --hook 14, or --hook 12-16
  for a range). Run `flytie add --help` to see every option, including
  --from-file for loading all fields at once.*
- **Quickstart §2 path-disambiguation.** The "where does my database live?"
  step now uses `flytie info` (the new diagnostic) rather than
  `flytie config path` (which returns the TOML config file location
  specifically). The same disambiguation flows through `commands.md` and
  `index.md` so all three docs agree.
- **Quickstart §6 defines the `?` marker** in shopping-list output at the
  point where it first appears, rather than burying the definition in the
  shopping-list cookbook.
- **Spec backport.** `fly-tying-tracker-spec.md` now reflects the shipped
  design: flag-driven `add`/`edit` (rather than the original interactive
  prompt / `$EDITOR` design), JSON/TOML pattern files (rather than the
  original YAML/JSON), search covering `instructions` in addition to name,
  materials, and notes, the `Qty` column wording reconciled with the
  implementation, and the new `flytie info` and `flytie tag list` commands
  documented.

[0.1.1]: https://github.com/finngidden/flytie/compare/v0.1.0...v0.1.1

## [0.1.0] — 2026-05-22

First public release. flytie is a local-first, AI-augmented command-line
manager for fly tying patterns.

### Added

- **Project setup** — `flytie init` creates a local SQLite database, applying
  the schema through bundled Alembic migrations so future upgrades migrate
  cleanly.
- **Pattern management** — `add`, `list` (with `--tag`, `--species`, and
  `--hook-size` filters), `view`, `search`, `edit` (with explicit `--rename-to`),
  `delete` (soft by default, `--hard` to purge), and `tag add` / `tag remove`.
  Patterns can be supplied inline or loaded from a JSON/TOML file.
- **Versioning** — every edit appends an immutable version. `versions` lists
  the history, `view --version N` shows a past version, `diff` compares two,
  and `restore` brings an old version back as a new one.
- **Shopping lists** — `shop` aggregates and deduplicates materials across any
  set of patterns selected by `--pattern`, `--tag`, or `--species`, with
  `--format markdown|text|json` and `--exclude` for materials already owned.
- **PDF export** — `export` renders a styled pattern card to PDF via WeasyPrint
  and a customizable Jinja2/CSS template, single or batch (`--tag`/`--species`).
  `--html` renders the card without WeasyPrint's native libraries.
- **AI suggestions** — `suggest` asks the Anthropic Claude API for fly
  recommendations grounded in the local library, streaming the response. Only
  pattern names, hook sizes, and material names are sent; the API key is read
  solely from `ANTHROPIC_API_KEY` and is never written to disk.
- **Portability** — `export-db` and `import-db` move a pattern library between
  machines as documented JSON, preserving full version history. Imports are
  transactional and offer `--on-conflict skip|overwrite|rename`.
- **Configuration** — `config get/set/path/show` manages user settings in a
  TOML file; `FLYTIE_CONFIG_DIR`, `FLYTIE_DATA_DIR`, and `FLYTIE_DB_PATH`
  override resolved locations.

[0.1.0]: https://github.com/finngidden/flytie/releases/tag/v0.1.0
