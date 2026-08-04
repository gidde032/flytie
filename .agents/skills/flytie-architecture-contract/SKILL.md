---
name: flytie-architecture-contract
description: >
  Use when you need to understand load-bearing design decisions before making
  structural changes to flytie. Trigger when: adding a table, column, or
  migration; touching the DTO/session boundary; adding a top-level import to
  cli.py; asking why a specific design is the way it is; evaluating whether a
  change to build_prompt, db.py, or models.py is safe; or before any PR that
  crosses layer boundaries. Third-person: "Use when the engineer needs the
  architectural contract for flytie before touching core structure."
---

# flytie Architecture Contract

*As of 2026-07-02, v0.2.1. Re-verify with commands in §6.*

---

## When NOT to use this skill

| Your question | Go here instead |
|---|---|
| How do I run quality gates / set up the dev environment? | `flytie-build-and-env` |
| Which config keys / exit codes / env vars? | `flytie-config-and-flags` |
| What fly-tying domain concepts does the schema model? | `flytie-domain-reference` |
| A bug is happening — how do I triage it? | `flytie-debugging-playbook` |
| What change class is this? Does it need sign-off? | `flytie-change-control` |
| Running subagent reviews? | `flytie-subagent-orchestration` |

---

## 1. System map

```
cli.py (Typer surface, 1330 lines)
  │  thin command shells; no business logic
  │  imports: typer, rich, sqlalchemy.select/func, all core.*, db, models, render
  │
  ├─► core/
  │     dto.py         — Pydantic DTOs (PatternDTO, PatternVersionDTO,
  │                       MaterialLineDTO, PatternInput); session-free
  │     patterns.py    — CRUD repo; returns ORM rows internally, DTOs at CLI seam
  │     versions.py    — version history helpers
  │     shop.py        — shopping-list aggregation
  │     dedupe.py      — fuzzy duplicate detection
  │     portability.py — export-db / import-db (JSON round-trip)
  │     stats.py       — summary statistics
  │     suggestions.py — persist/load last AI suggestion run (JSON file)
  │     parsing.py     — YAML/TOML pattern-file parser
  │
  ├─► models.py        — SQLAlchemy ORM (Pattern, PatternVersion, Material,
  │                       PatternMaterial, Species, Tag, association tables)
  │                       also: normalize_name(), _utcnow(), _pattern_before_update event
  │
  ├─► db.py            — Database dataclass (engine + session factory + Alembic wrapper)
  │                       IncompatibleDatabaseError; lazy alembic imports
  │
  ├─► config.py        — Settings (frozen dataclass); ConfigFile (TOML read/write);
  │                       atomic tmp+rename saves; env-var overrides
  │
  ├─► render.py        — Rich table/panel rendering; consumes DTOs only
  │
  ├─► pdf/export.py    — Jinja2 + WeasyPrint rendering; lazy-imported extras
  │
  ├─► ai/suggest.py    — build_prompt, parse_suggestions, anthropic_streamer,
  │                       Streamer seam; lazy SDK import; privacy boundary
  │
  ├─► migrations/      — Alembic env + single revision 5af955bd607b (initial schema)
  │     __init__.py    — exports MIGRATIONS_DIR (Path to this package directory)
  │
  └─► templates/       — pattern_card.html, pattern_card.css (bundled Jinja2 templates)
```

**Import discipline.** cli.py may import from any layer. `core/` modules may import from
`models.py`, `core/dto.py`, and each other but must NOT import from `cli.py` or `render.py`.
`render.py` consumes DTOs only — it must not import ORM models or open sessions.
`db.py` imports from `config.py` and `models.py` only.
`ai/suggest.py` imports from `core/dto.py` and `models.normalize_name` only; Anthropic SDK
is lazy-imported inside `_require_anthropic()`.
`pdf/export.py` imports from `core/dto.py` only; Jinja2 and WeasyPrint are lazy-imported.

---

## 2. Load-bearing decisions

### 2.1 DTO / repository / CLI boundary

**Decision.** `core/patterns.py` (and all other core repos) return Pydantic DTOs
(`PatternDTO`, `PatternVersionDTO`, `MaterialLineDTO` from `core/dto.py`) at the
point they cross into `cli.py` or `render.py`. They may return raw ORM rows
internally for further composition within the same session, but nothing that
carries a live SQLAlchemy session escapes `db.session()`.

**Why.** Session-leak bugs (lazy-load explosions, detached-instance errors) plagued
Phase 1 reviews and were eliminated once DTOs became the contract. `expire_on_commit=False`
on the session factory (`db.py` line 57) is a belt-and-suspenders backup, but the
real protection is that renderers never hold an ORM reference.

**What breaks if violated.** Detached-instance errors at render time, or phantom
reads if a session is kept alive longer than a single command. `render.py` is typed
to accept only DTOs — passing an ORM object will fail type-checking (`mypy`).

### 2.2 Alembic bundled inside the package

**Decision.** Migrations live in `src/flytie/migrations/` and ship inside the wheel.
`MIGRATIONS_DIR` (from `migrations/__init__.py`) points to the installed package path
so migrations run from wherever flytie is installed, without a separate checkout.

**Why.** A CLI tool installed from PyPI must be able to create its own schema; requiring
users to find a separate migrations directory would be broken UX.

**The stamped-but-empty DB trap (Phase 6 CRITICAL).** SQLite auto-commits every DDL
statement. If `flytie init` is interrupted mid-run, Alembic may have written
`alembic_version` to the DB before all tables are created. On the next `init`, Alembic
sees the stamp, believes the DB is current, runs nothing, and returns cleanly — leaving
the DB with `alembic_version` set to head but no `patterns` table.

`Database.create_schema()` in `db.py` defends against this by calling
`schema_is_complete()` (which checks `inspect(engine).has_table("patterns")`) after
`upgrade_to_head()`. If the check fails, it calls `_build_schema_directly()` which
runs `Base.metadata.create_all(engine)` followed by `stamp_alembic_head()`.

`flytie init` also surfaces this case before running: if the DB file exists but
`schema_is_complete()` returns False, it prints a repair notice and proceeds without
`--force`.

### 2.3 validate_compatibility and exit code 4

**Decision.** `Database.validate_compatibility()` compares the DB's `alembic_version`
row against the set of revisions this build's bundled migrations contain. If the DB is
stamped at an unknown revision (user installed a newer flytie, ran a migration, then
downgraded), it raises `IncompatibleDatabaseError`.

`_open_db()` in `cli.py` catches this and raises `typer.Exit(code=4)`.

**Exception: `flytie info`.** The `info` command deliberately does NOT call
`validate_compatibility()` via `_open_db()`. It calls `validate_compatibility()` directly
and catches the error, printing a diagnostic message and continuing. `info` is the one
command that must remain usable when every other command is broken — it is the user's
only tool for diagnosing the incompatibility.

**Verify:**
```bash
grep -n "validate_compatibility\|_open_db\|incompatibility_msg" src/flytie/cli.py | head -20
```

### 2.4 SQLite pragmas

**Decision.** Every new connection fires `_enable_sqlite_pragmas()` (registered via
`sqlalchemy.event.listen` in `Database.from_settings()`), which sets:
- `PRAGMA foreign_keys=ON` — enforces referential integrity (cascades, RESTRICT)
- `PRAGMA journal_mode=WAL` — Write-Ahead Logging for concurrent read access

WAL produces `.sqlite3-wal` and `.sqlite3-shm` sidecar files. These are gitignored.
Do not suppress WAL mode — it is load-bearing for concurrent read access patterns.

### 2.5 Soft-delete semantics

**Decision.** `Pattern.is_deleted` (Boolean, `server_default=false()`) marks deleted
patterns rather than removing rows. `get_pattern(..., include_deleted=True)` in
`core/patterns.py` can still retrieve them.

**Why.** Deleted patterns still have `PatternVersion` rows. If a user deletes a pattern
and then creates one with the same name, the old version history remains reachable.
This also makes `undelete` trivial.

**What breaks if violated.** Hard-deleting a Pattern cascades to PatternVersion rows
(cascade="all, delete-orphan"), permanently destroying version history. The
`name_key` uniqueness constraint would also block re-creating a same-named pattern
until the row is gone.

### 2.6 Versioning model and timestamp preservation

**Decision.** Every edit creates a new `PatternVersion` row. `Pattern.current_version_id`
points to the latest. `PatternVersion` rows are append-only; their `created_at` is set
at insert time and never updated.

**Timestamp preservation on import.** JSON import must preserve historical timestamps
(the source DB's `updated_at`). The `_pattern_before_update` event listener in
`models.py` only refreshes `updated_at` if the caller did NOT explicitly set it during
the same flush (it checks SQLAlchemy's history for the attribute). This means import
code can set `pattern.updated_at = historical_value` and it will not be overwritten.

**Verify:**
```bash
grep -A 8 "_pattern_before_update" src/flytie/models.py
```

### 2.7 Single-source version

**Decision.** `__version__` lives only in `src/flytie/__init__.py` (currently `"0.2.1"`).
`pyproject.toml` uses hatchling's `dynamic = ["version"]` with `source = "vcs"` or
the `__init__.py` path. The release workflow asserts the git tag matches this value.

**What breaks if violated.** Updating version in more than one place creates drift.
Never manually edit both `__init__.py` and `pyproject.toml` version fields.

### 2.8 Atomic writes for cross-invocation state

**Decision.** Any file written between CLI invocations uses `tmp + os.replace()`:
- `config.py` `ConfigFile.save()`: writes to `.tmp`, then `os.replace()`
- `core/suggestions.py` `save_suggestions()`: same pattern

**The v0.2.1 criterion for new persistent state.** Cross-invocation data you would never
`SELECT` against gets a JSON file (like `last_suggestions.json`), not a new table and
migration. If you are tempted to add a table for something that does not need querying,
reach for a JSON file with atomic writes instead.

### 2.9 Cold-start discipline and lazy imports

**Decision.** Heavy optional dependencies are never imported at module top-level.
They are imported inside guard functions that are called only when the feature is used:

- `ai/suggest.py`: `_require_anthropic()` lazy-imports the `anthropic` SDK
- `pdf/export.py`: `_require_jinja2()` and `_require_weasyprint()` lazy-import those packages
- `db.py`: `upgrade_to_head()`, `stamp_alembic_head()`, `known_revisions()`, and
  `validate_compatibility()` each `from alembic import ...` locally (commented as
  "Lazy alembic imports" in `upgrade_to_head`)

**The 600 ms gate.** `flytie --version` best-of-5 must run under 600 ms (spec NFR §4).
Any new top-level import in `cli.py` or in a module `cli.py` imports at the top risks
failing this gate. Diagnose with `python -X importtime -m flytie --version 2>importtimes.log`;
the full importtime-parsing walkthrough lives in the owner, `flytie-diagnostics-and-tooling` §5.

### 2.10 The Streamer seam (AI testability)

**Decision.** `ai/suggest.py` defines `Streamer = Callable[[str, str], Iterator[str]]`.
The real implementation (`anthropic_streamer`) is built and passed in by the CLI command.
Tests inject a fake streamer that yields pre-canned chunks — no network, no API key needed.

**Why this matters.** This is what makes the no-live-API-tests rule practical. Any change
to the AI path must keep `generate_suggestions()` accepting an injected `Streamer`.
Do not inline the Anthropic call into the orchestration function.

### 2.11 Privacy boundary

**Decision.** `build_prompt()` in `ai/suggest.py` is the sole boundary for what reaches
the Anthropic API. It sends only:
- Pattern name (`p.name` via `PatternDTO`)
- Hook size (`v.hook_size`)
- Material canonical names (`m.canonical_name`)

It never sends `instructions`, `notes`, `tags`, `species`, or any user-authored text.
Materials are capped at `MAX_MATERIALS_PER_PATTERN = 12` per pattern; patterns capped
at `MAX_GROUNDING_PATTERNS = 40`.

**Rule.** New fields added to `Pattern` or `PatternVersion` must NOT enter `build_prompt`
without an explicit privacy review. The prompt content list above is exhaustive.

**The API key.** `resolve_api_key()` reads only `os.environ.get("ANTHROPIC_API_KEY")`.
It is never written to disk, never logged, never interpolated into error strings, and
absent from `_CONFIG_KEYS` in `cli.py`.

### 2.12 Error-handling spine in cli.py

Four helpers gate all error paths:

| Helper | Purpose | Exit code |
|---|---|---|
| `_fail(message, code=1)` | Print red error to stderr, return `typer.Exit` | 1 (default) |
| `_format_pydantic_error(exc)` | Format ValidationError into human-readable lines | — |
| `_build_pattern_input(**fields)` | Validate PatternInput, exit code 2 on failure | 2 |
| `_load_file_or_exit(path)` | Load YAML/TOML pattern file, exit code 2 on failure | 2 |

**Exit code map (verified in `cli.py`):**

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Data error (pattern not found, version not found, import failure) |
| 2 | Input error (bad argument, validation failure, file not found; also the non-TTY `delete` guard — `delete` without `--yes` on non-TTY stdin exits 2, `cli.py:919`) |
| 3 | Missing optional dependency (`pdf` or `ai` extra not installed) |
| 4 | Incompatible database (future schema; must upgrade or restore) |
| 130 | User cancelled via `KeyboardInterrupt` during `suggest` (`cli.py:644`) — NOT the non-TTY delete guard, which exits 2 |

---

## 3. Invariants

These must hold at all times. Each has a pinning test where one exists.

1. **Pattern names are unique case-insensitively.** `normalize_name()` lowercases, strips,
   and collapses whitespace before storing as `name_key`. The DB enforces `UNIQUE` on
   `patterns.name_key`. Application-level check in `create_pattern()` raises
   `DuplicatePatternError` before the DB constraint fires.
   Pinning test: `tests/test_patterns_repo.py` (duplicate create tests).

2. **`flytie init` always leaves the DB Alembic-stamped at head.** Both paths
   (`upgrade_to_head` success and `_build_schema_directly` fallback) stamp the DB.
   Pinning test: `tests/test_db.py::test_init_creates_db_file` (`@pytest.mark.smoke`).

3. **No ORM objects cross the DTO boundary.** `render.py` and `cli.py` rendering code
   must consume only `PatternDTO` / `PatternVersionDTO` / `MaterialLineDTO`. Violations
   are caught by `mypy` (renderers are typed to accept DTOs).

4. **`ANTHROPIC_API_KEY` is not in `_CONFIG_KEYS`.** The three allowed config keys are
   `database.path`, `pdf.template`, `pdf.output_dir`. Verified in `cli.py` lines 66-70.
   No test pins this specific absence; it is enforced by code review and this document.

5. **Smoke marker is exactly 5 tests.** The five smoke tests are: `test_init_creates_db_file`,
   `test_add_and_list_round_trip`, `test_view_renders_pattern`, `test_shop_dedupes_across_patterns`,
   `test_cli_import_db_round_trip`. Adding a sixth requires updating the regression test.
   Pinning test: `tests/test_v0_1_2_fixes.py::test_smoke_marker_collects_exactly_five_happy_path_tests`.

6. **Migrations are never edited after release.** `5af955bd607b_initial_schema.py` is
   pinned. Future schema changes require a new revision file. This is a convention, not
   mechanically enforced — label it as such.

7. **`*_old.py` files are excluded from pytest, ruff, and coverage.** The `addopts` in
   `pyproject.toml` explicitly ignores `tests/test_patterns_repo_old.py` and
   `tests/test_review_fixes_old.py`. The `[tool.ruff].exclude` list covers all six
   `*_old.py` source files. The `[tool.coverage.run].omit` list covers the same.
   Do not remove these exclusions.

8. **Cold-start best-of-5 under 600 ms.** Enforced via NFR §4; gate is manual but
   expected on every release.

---

## 4. Known weak points

State these plainly to the next engineer.

**`*_old.py` fossils.** Eight `*_old.py` paths are tracked in git
(`src/flytie/cli_old.py`, `src/flytie/render_old.py`, `src/flytie/core/parsing_old.py`,
`src/flytie/core/shop_old.py`, `src/flytie/core/versions_old.py`,
`src/flytie/migrations/env_old.py`, `tests/test_patterns_repo_old.py`,
`tests/test_review_fixes_old.py`) — so fresh clones get all eight, inert and excluded
from pytest/ruff/coverage. They are FUSE-recovery placeholders from the Phase 3
development sandbox and contain no shipping code. As of 2026-07-02 all eight are physically
present in the working copy (verify: `find src tests -name "*_old.py"`). The inodes
are FUSE-poisoned in Cowork sandbox sessions — unlink fails there, so they cannot
be removed from a sandboxed session. Do not delete or 'fix' any of them without maintainer
sign-off. Verify with:
```bash
git ls-files | grep _old
```

**Only one Alembic migration exists — the migration PATH is untested.** `5af955bd607b`
is the initial schema. No subsequent migration has ever been written or applied in
production. The `upgrade_to_head` path works correctly for a fresh DB, but the behavior
of a real incremental migration (new column, data backfill, downgrade) is unvalidated.
This is the riskiest future surface. The first real migration is expected around v0.4.0
(inventory feature). When that migration is written, the smoke suite should include an
upgrade-from-previous-revision test.

**`cli.py` is a 1330-line monolith.** All Typer command definitions live in a single
file. It is functionally correct and well-factored at the logic level (thin shells
delegating to `core/`), but navigating it is non-trivial. This is a known UX debt for
contributors, not a correctness risk.

**Coverage floor is 85%; actual is 89.2% in a sandbox without `[pdf]` extras (weasyprint absent drags `pdf/export.py`); higher with all extras installed as in CI; the enforced floor is 85%.**
New defensive branches that are difficult to exercise (e.g., OS-level error handlers)
can consume some of it without failing CI, but the floor is real — do not weaken it.

---

## 5. Change checklist

Before any structural change, answer each question:

- [ ] **New top-level import in `cli.py` or a module it top-level imports?**
      Run cold-start gate: `flytie --version` best-of-5. Must stay under 600 ms.
      Heavy deps (`weasyprint`, `anthropic`, `alembic`) must stay lazy.

- [ ] **Crossing the DTO boundary?**
      Renderers (`render.py`, `pdf/export.py`) must receive DTOs, not ORM objects.
      Update `core/dto.py` if the DTO shape changes; update `_to_pattern_dto()` in
      `core/patterns.py` to populate new fields.

- [ ] **Adding a table or column (needs a migration)?**
      This requires a new Alembic revision file. There is no prior precedent.
      Get maintainer sign-off before writing the migration. See `flytie-change-control`.

- [ ] **Touching `build_prompt()` or adding a field to `Pattern`/`PatternVersion`?**
      Privacy review required. Confirm the new content is acceptable to send to the
      Codex API. The approved list is: pattern name, hook size, material canonical names.

- [ ] **New cross-invocation state that doesn't need querying?**
      Use a JSON file with `tmp + os.replace()`. Do not add a table.

- [ ] **Any accepted review finding?**
      Pair it with a regression test in the appropriate test file
      (`test_review_fixes_phase{N}.py` or `test_v0_X_Y_fixes.py`).

For all structural changes, route through `flytie-change-control` for the full gate list.

---

## 6. Provenance and maintenance

Written 2026-07-02, v0.2.1. Sources: direct reads of `src/flytie/cli.py`,
`db.py`, `models.py`, `config.py`, `ai/suggest.py`, `pdf/export.py`,
`core/dto.py`, `core/patterns.py`, `core/suggestions.py`,
`migrations/__init__.py`, `migrations/versions/5af955bd607b_initial_schema.py`,
`pyproject.toml`, and `tests/` grep passes.

Re-verify key facts after any structural change:

```bash
# Layer structure
find src/flytie -name "*.py" | grep -v __pycache__ | sort

# Lazy alembic import
grep -n "from alembic" src/flytie/db.py

# Exit codes
grep -n "code=[0-9]" src/flytie/cli.py | sort -t= -k2 -n

# Config keys (confirm API key absent)
grep -A 5 "_CONFIG_KEYS" src/flytie/cli.py

# _old.py fossil count
git ls-files | grep _old

# Smoke marker count
grep -r "pytest.mark.smoke" tests/ | grep -v "def test_smoke" | wc -l

# Privacy boundary
grep -n "build_prompt\|grounding_block\|MAX_GROUNDING\|MAX_MATERIALS" src/flytie/ai/suggest.py

# Cold-start
for i in 1 2 3 4 5; do time python -m flytie --version; done
```
