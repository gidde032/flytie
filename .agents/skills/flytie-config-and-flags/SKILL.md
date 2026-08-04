---
name: flytie-config-and-flags
description: >
  Use when resolving where the flytie database or config file lives, understanding
  the env-var/config-file/platformdirs precedence chain, adding a new config key
  or env var, interpreting exit codes, choosing which install extras to use,
  understanding pytest markers or COLUMNS conventions, or checking what is and
  is not behind a flag. Covers: FLYTIE_CONFIG_DIR, FLYTIE_DATA_DIR, FLYTIE_DB_PATH,
  _CONFIG_KEYS, exit codes 0/1/2/3/4/130, [pdf]/[ai]/[dev] extras,
  smoke marker contract, coverage floor, ruff isort known-* lists, and the
  checklist for adding a config key, env var, or exit code.
---

# flytie — Config, Flags, and Project Axes

**Audience:** zero-context mid-level engineer or Sonnet-class agent with a plain
git clone and a terminal. No Cowork tooling assumed.

**When NOT to use this skill:**
- Setting up the dev environment from scratch → `flytie-build-and-env`
- Triaging a failure or reading a stack trace → `flytie-debugging-playbook`
- Understanding the domain model (Pattern, Species, Tag) → `flytie-domain-reference`
- CLI command anatomy or the release runbook → `flytie-run-and-operate`
- Change-class rules and quality gates → `flytie-change-control`

---

## 1. Resolution chain

flytie resolves config and data locations in this order (highest wins):

```
env var  >  config file (TOML)  >  platformdirs default
```

The logic lives in `src/flytie/config.py`: `load_settings()` calls three
private resolvers in sequence; each one checks its env var first, falls back to
a config-file value, then falls back to `platformdirs`.

### Environment variables

| Variable | Overrides | Default when unset |
|---|---|---|
| `FLYTIE_CONFIG_DIR` | Config directory (and thus config file path) | `platformdirs.user_config_dir("flytie")` |
| `FLYTIE_DATA_DIR` | Data directory (DB lives here by default) | `platformdirs.user_data_dir("flytie")` |
| `FLYTIE_DB_PATH` | Full database path (takes precedence over `database.path` in config too) | `<data_dir>/flytie.sqlite3` |

`ANTHROPIC_API_KEY` is handled separately — see the API key guard below.

### `flytie info` — ground-truth resolver

Run this at any time to see the resolved paths for the current environment:

```
$ flytie info
Database path      /home/alice/.local/share/flytie/flytie.sqlite3
Config file        /home/alice/.config/flytie/config.toml
Data directory     /home/alice/.local/share/flytie
Schema revision    5af955bd607b
Patterns           0
Tags               0
Species            0
```

Real output shape verified live against v0.2.1 (as of 2026-07-02). Fields
shown are always present; `Schema revision` is the Alembic head.

**Test isolation pattern** (also used in `conftest.py`):

```bash
export FLYTIE_CONFIG_DIR=/tmp/my_test_config
export FLYTIE_DATA_DIR=/tmp/my_test_data
# FLYTIE_DB_PATH deliberately unset — resolves to <data_dir>/flytie.sqlite3
flytie init
flytie info
```

---

## 2. Config file

**Location:** `<config_dir>/config.toml` (resolved by `flytie config path`).

**Format:** TOML, organized in sections. Two sections exist today:

```toml
[database]
path = "/custom/path/flytie.sqlite3"   # optional — env var takes precedence

[pdf]
template = "default"     # template name or path; default: "default"
output_dir = "~/pdfs"    # optional; default: none (write next to the pattern)
```

**`_CONFIG_KEYS` (exact set from `src/flytie/cli.py` lines 66–70, v0.2.1):**

```python
_CONFIG_KEYS = {
    "database.path": "Path to the SQLite database file.",
    "pdf.template": "Default PDF template name or path.",
    "pdf.output_dir": "Default directory for exported PDFs.",
}
```

These are the only keys `flytie config get/set/show` will accept. Supplying
any other key yields exit code 2 and lists the known keys.

**Config subcommands:**

| Command | Effect |
|---|---|
| `flytie config path` | Print the config file path (no read/write) |
| `flytie config show` | Print all keys that are set; message if nothing is configured |
| `flytie config get <key>` | Print one key's value, or a "default in effect" message |
| `flytie config set <key> <value>` | Write one key; atomic tmp+rename so a crash never corrupts config |

Write is atomic: `ConfigFile.save()` writes to `<config_file>.tmp` then
`os.replace(tmp, config_file)`. A `ConfigError` is raised on malformed TOML
at load time (exit code 2 from the CLI).

### API key guard (non-negotiable)

`ANTHROPIC_API_KEY` is **env-only**. It is never written to disk, never
logged, never returned by `flytie info` or `flytie config show`, and is
explicitly excluded from `_CONFIG_KEYS`. The guard is enforced by:

- `_CONFIG_KEYS` not containing any `api.*` or `anthropic.*` key.
- Regression test `test_config_has_no_api_key_setting` in
  `tests/test_audit_fixes.py`: `flytie config set api.key secret` must exit 2.
- Regression test `test_info_never_mentions_api_key` in
  `tests/test_v0_1_1_fixes.py`: sets `ANTHROPIC_API_KEY` to a known sentinel,
  runs `flytie info`, asserts the sentinel is absent from stdout.

Do not add any key related to authentication or secrets to `_CONFIG_KEYS`.
Secrets are env-only by design.

---

## 3. Exit codes

Verified from `src/flytie/cli.py` (`_fail()` helper and `typer.Exit` calls):

| Code | Meaning | Raised when | Recovery |
|---|---|---|---|
| 0 | Success | Normal completion | — |
| 1 | Runtime / data error | Record not found, write failed, import/export error, validation failure at runtime | Read the error message; check DB integrity with `flytie info` |
| 2 | Usage / input error | Bad arguments, unknown config key, malformed TOML config, mutually exclusive flags, Pydantic validation on input | Re-read command help (`--help`); fix the argument |
| 3 | Missing optional extra | `PDFDependencyError` (pdf extra absent) or `AIDependencyError` (ai extra absent) | `pip install 'flytie[pdf]'` or `pip install 'flytie[ai]'` |
| 4 | Incompatible database | `IncompatibleDatabaseError` from `validate_compatibility()` — DB was migrated by a newer flytie | Install the newer flytie, export with `export-db`, then `init --force` + `import-db` on the older build |
| 130 | User cancellation | `KeyboardInterrupt` during `flytie suggest` (the only interactive streaming command) | Normal; user pressed Ctrl-C |

Typer's built-in argument parsing errors also produce exit code 2 (Typer's
own `UsageError`), consistent with the project's usage-error convention.

---

## 4. Install extras matrix

| Extra | Package added | Requires | Enables |
|---|---|---|---|
| *(none)* | — | — | Core CLI, `export --html` (Jinja2 is a core dep, not in `[pdf]`) |
| `[pdf]` | `weasyprint>=61,<70` | Native libs: Pango, Cairo (see below) | `flytie export --pdf` |
| `[ai]` | `anthropic>=0.30,<1.0` | `ANTHROPIC_API_KEY` env var at use-time | `flytie suggest` |
| `[dev]` | pytest, pytest-cov, syrupy, ruff, mypy, pre-commit, pdfminer.six | — | Full test + lint suite |

**Bare install note:** Jinja2 is a *core* dependency (not in `[pdf]`). This is
intentional — the spec (FR-5) promises `flytie export --html` works without
WeasyPrint. HTML export is always available.

**WeasyPrint native library requirement:**

```bash
# macOS
brew install pango

# Debian/Ubuntu
sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0

# Fedora/RHEL
sudo dnf install pango
```

If the native libs are missing but `weasyprint` is installed, `PDFDependencyError`
is raised with the above install hint embedded in the message.

**Friendly error messages (verified from source):**

- PDF extra absent: `"PDF export needs the optional 'pdf' extra. Install with: pip install 'flytie[pdf]'"` → exit 3
- AI extra absent: `"AI suggestions need the optional 'ai' extra. Install with: pip install 'flytie[ai]'"` → exit 3

---

## 5. Test and CI configuration axes

### Pytest markers

`--strict-markers` is set in `pyproject.toml` `addopts`. Only one custom
marker is registered:

```toml
[tool.pytest.ini_options]
markers = ["smoke: minimal happy-path tests run before commit"]
```

**Smoke contract (checked by regression test):** exactly **5** tests carry
`@pytest.mark.smoke`. The count is pinned by
`test_smoke_marker_collects_exactly_five_happy_path_tests` in
`tests/test_v0_1_2_fixes.py`. If you add a sixth, that test will fail — update
it deliberately, do not loosen it silently.

The golden inventory of the five tests and the full exact-count mechanics live in
`flytie-validation-and-qa` §3 (the owner). Run smoke suite: `pytest -m smoke -q` (~3 s).

### `addopts` ignores

```toml
addopts = "-ra --strict-markers --ignore=tests/test_patterns_repo_old.py --ignore=tests/test_review_fixes_old.py"
```

The `*_old.py` files are FUSE-poisoned inodes from a Phase 3 sandbox recovery.
They contain no shipping code and cannot be deleted from the sandbox; they are
excluded here, from `[tool.ruff].exclude`, and from `[tool.coverage.run].omit`.

### COLUMNS — why two values

| Context | Value | Reason |
|---|---|---|
| Test suite (`conftest.py` autouse fixture) | `COLUMNS=200` | Default for all `CliRunner.invoke` calls — prevents Rich from line-wrapping output and breaking substring assertions |
| CI (`ci.yml` env block) and pre-push hook | `COLUMNS=80` | Forces narrow terminal to surface wrap-fragility before it reaches main |

These two values are complementary: 200 makes individual test assertions stable
(no wrapping), 80 in CI/pre-push validates that no test is secretly relying on
wide output. A test that needs to assert narrow-terminal behavior can pass
`env={"COLUMNS": "80"}` to `CliRunner.invoke` and the autouse patch will honor
the explicit override.

### Coverage

```toml
[tool.coverage.report]
fail_under = 85
```

Current real coverage is 89.2% in a sandbox without `[pdf]` extras (weasyprint absent drags `pdf/export.py`); higher with all extras installed as in CI; the enforced floor is 85% (v0.2.1); the 85% floor leaves headroom for
defensive branches while making regressions fail CI explicitly.

Omit list includes: `*_old.py` files, `src/flytie/__main__.py`,
`src/flytie/migrations/env.py`, and `src/flytie/migrations/versions/*.py`.
Alembic migrations run in subprocess; their effect is tested end-to-end.

### ruff isort `known-*` lists

```toml
[tool.ruff.lint.isort]
known-first-party = ["flytie"]
known-third-party = ["alembic", "sqlalchemy", "typer", "rich", "pydantic",
                     "anthropic", "weasyprint", "jinja2", "platformdirs",
                     "tomli", "tomli_w"]
```

These are explicit rather than auto-detected. Without them, ruff's
auto-detection treated `alembic` and `alembic.config` inconsistently across
sandbox vs. CI, producing import-order churn on every `ruff --fix` run.
Explicit classification ensures the `I001` rule is deterministic across all
environments.

---

## 6. Production vs. experimental flags (v0.2.1)

All shipped commands and flags are production. Nothing is behind a runtime
feature flag or gated by an env var at runtime.

**`--dry-run` exists today** on two subcommands: `flytie material merge --dry-run`
and `flytie material dedupe --dry-run`. Both are fully shipped and production.

**FUTURE (not yet in any release):** The spec describes `material dedupe --ai`
(AI-assisted deduplication scoring) and `categorize --dry-run` as v0.3.0
candidates. These do not exist in v0.2.1. Do not reference them as current.

---

## 7. Checklists

### Adding a config key

1. Add the dotted key and description to `_CONFIG_KEYS` in `src/flytie/cli.py`.
2. Add the corresponding field to `Settings` in `src/flytie/config.py`.
3. Wire it in `load_settings()`: read from the correct TOML section, apply
   env-var precedence if appropriate.
4. Add a round-trip test: `config set <key> <value>` → `config get <key>` returns it.
5. If the key is at all sensitive: add a `config show` exclusion test.
   Secrets must never be config keys — add to `_CONFIG_KEYS` only if the value
   is safe to store on disk and safe to display in `config show` output.
6. Update user-facing docs in `docs/` (e.g. add to the relevant command doc
   or the README config section).
7. Backport to `fly-tying-tracker-spec.md` if the key changes a documented
   promise.

### Adding an env var

1. Add a `_resolve_<name>()` function in `src/flytie/config.py` following the
   existing pattern: `os.environ.get("FLYTIE_<NAME>")` → expand user → return.
2. Call it from `load_settings()` and thread the result through `Settings`.
3. Document in the module docstring of `config.py` (the existing env vars are
   listed there by name).
4. Add a test that sets the env var and confirms the resolved path changes.
5. Never put secrets in env vars named like config keys. Third-party keys use
   their own namespace (e.g., `ANTHROPIC_API_KEY`) and are read at use-time in
   the module that needs them, not stored in `Settings`.

### Adding an exit code

1. Pick a code not in the table in section 3 (current set: 0, 1, 2, 3, 4, 130).
2. Use `_fail(message, code=<N>)` in `cli.py`.
3. Add a test that triggers the new path and asserts `result.exit_code == <N>`.
4. Update the exit-code table in this skill.

---

## 8. Provenance and re-verification commands

**Date:** 2026-07-02. **Version:** v0.2.1.

All facts below were verified against live source files and a live `flytie`
install in the project sandbox.

| Catalog | Re-verify with |
|---|---|
| `_CONFIG_KEYS` | `grep -n "_CONFIG_KEYS" -A5 src/flytie/cli.py` |
| Env var names | `grep -n "FLYTIE_\|ANTHROPIC_API_KEY" src/flytie/config.py` |
| Exit codes | `grep -n "code=" src/flytie/cli.py \| sort -t= -k2 -n` |
| Extras matrix | `grep -A10 "\[project.optional-dependencies\]" pyproject.toml` |
| Smoke marker count | `pytest --collect-only -m smoke -q -p no:cacheprovider --tb=no \| tail -2` |
| COLUMNS defaults | `grep -n "COLUMNS" tests/conftest.py .github/workflows/ci.yml .pre-commit-config.yaml` |
| Coverage floor | `grep "fail_under" pyproject.toml` |
| ruff known-* | `grep -A5 "\[tool.ruff.lint.isort\]" pyproject.toml` |
