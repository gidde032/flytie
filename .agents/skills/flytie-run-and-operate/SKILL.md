---
name: flytie-run-and-operate
description: >
  Use when running any flytie command, learning the full command surface,
  finding where data and exports land, working through a scratch-env session,
  importing or exporting the pattern library, cutting a release, or publishing
  flytie to PyPI. Covers: init, info, add, list, view, search, edit, delete,
  undelete, versions, diff, restore, stats, shop, export, export-db, import-db,
  suggest, tag (list/add/remove), material (merge/dedupe), config
  (get/set/path/show), and the full release runbook.
---

# flytie-run-and-operate

Operating the CLI — command surface, data locations, destructive-operation
guards, AI commands, and the release runbook.

**When NOT to use this skill:**
- Setting up the dev environment from scratch → `flytie-build-and-env`
- Env vars, exit codes, config file format → `flytie-config-and-flags`
- Quality gates, PR rules, what blocks a release → `flytie-change-control`
- Triaging a failure or reading a stack trace → `flytie-debugging-playbook`
- Domain model (Pattern, Version, Species, Tag) → `flytie-domain-reference`

---

## 1. Command catalog

As of 2026-07-02 (v0.2.1). Derived from `flytie --help` (run live) and
`src/flytie/cli.py` (complete read). Re-verify with `flytie --help` and
`flytie <cmd> --help`.

### Top-level commands

| Command | What it does | Key flags | Notable behavior |
|---------|-------------|-----------|-----------------|
| `init` | Create the SQLite DB via Alembic migrations | `--force` | Safe to re-run; auto-repairs a half-built schema without `--force` or data loss |
| `info` | Show resolved paths and library summary | — | Works before init and against an incompatible (newer-schema) DB by design; never reveals the API key |
| `stats` | Read-only library summary | — | Exits cleanly with a message if the library is empty |
| `add` | Add a new pattern | `--hook` (required), `--difficulty 1-5`, `--instructions`, `--notes`, `-t TAG` (repeatable), `-s SPECIES` (repeatable), `-m MATERIAL` (repeatable), `--from-file PATH`, `--from-suggestion N` | `name` and `--hook` are required unless using `--from-file` or `--from-suggestion` |
| `list` | List patterns | `--tag`, `--species`, `--hook-size`, `--include-deleted` | Filters are ANDed |
| `view` | Full detail for one pattern | `--version N` | Shows current version by default; `--version` pins to a historical version |
| `search` | Free-text search | positional query | Searches name, instructions, notes, and material names |
| `edit` | Edit a pattern, creating a new immutable version | `--hook`, `--difficulty`, `--instructions`, `--notes`, `-t` (replaces list), `-s` (replaces list), `-m` (replaces list), `--clear-tags`, `--clear-species`, `--clear-materials`, `--rename-to`, `--from-file` | List flags replace, not append; `--clear-*` and its matching list flag are mutually exclusive |
| `delete` | Soft-delete a pattern | `--yes` / `-y`, `--hard` | Interactive confirm unless `--yes`; non-TTY stdin refuses without `--yes`; `--hard` is permanent |
| `undelete` | Restore a soft-deleted pattern | — | No-ops with a message if the pattern is not deleted |
| `versions` | List every version of a pattern, oldest first | — | |
| `diff` | Unified diff between two versions | `<name> <v1> <v2>` positional | Both version numbers are required positional args |
| `restore` | Restore an old version as a new (latest) version | `<name> <version>` positional | Appends a new version; never rewrites history |
| `shop` | Deduplicated shopping list | `-p PATTERN` (repeatable), `-t TAG` (repeatable), `-s SPECIES` (repeatable), `-x MATERIAL` (exclude, repeatable), `-f FORMAT` | Format: `table` (default), `markdown`, `text`, `json`; at least one selector required |
| `suggest` | Ask Codex for fly suggestions grounded in your library | `-s SPECIES` (required), `--season` (required), `--water`, `--conditions`, `--n 1-10` (default 3) | Requires `ANTHROPIC_API_KEY` env var and `[ai]` extra |
| `export` | Export a pattern as a PDF card (or HTML) | positional name or `--tag`/`--species` for batch, `--out`, `--template`, `--css`, `--photo`, `--html` | `--html` prints to stdout, no WeasyPrint needed; `--out` with no extension treated as directory |
| `export-db` | Export the library to a portable JSON file | `--out` (required), `--tag`, `--species`, `--include-deleted` | Includes full version history per pattern |
| `import-db` | Import from a flytie JSON export file | positional path, `--on-conflict skip\|overwrite\|rename` | Fully transactional: nothing changes on failure |

### Subcommand groups

**`tag`**

| Subcommand | What it does |
|-----------|-------------|
| `tag list` | List all tags with usage counts (active patterns only) |
| `tag add <pattern> <tag>...` | Add one or more tags to a pattern |
| `tag remove <pattern> <tag>...` | Remove one or more tags from a pattern |

**`material`**

| Subcommand | What it does | Key flags |
|-----------|-------------|-----------|
| `material merge <from> <to>` | Merge one material name into another, rewriting all references | `--dry-run` |
| `material dedupe` | Scan for likely duplicate material names and interactively merge | `--threshold 0-1` (default 0.6), `--dry-run` |

**`config`**

| Subcommand | What it does |
|-----------|-------------|
| `config path` | Print the config file location |
| `config show` | Show all configured settings (API key never stored or shown) |
| `config get <key>` | Read a single setting |
| `config set <key> <value>` | Write a single setting |

Configurable keys: `database.path`, `pdf.template`, `pdf.output_dir`.
`ANTHROPIC_API_KEY` is deliberately NOT a config key — it is read only from
the environment variable.

### Material mini-grammar

`--material` accepts comma-separated fields: `name[,category[,quantity[,unit[,notes]]]]`.
Only `name` is required. Valid categories:
`thread hook hackle dubbing flash body tail wing head bead weight adhesive other`.
Example: `"grizzly hackle,hackle,2"`. See `flytie-domain-reference` for
full grammar and validation rules.

---

## 2. Worked 10-minute session (scratch environment)

Use these env vars to avoid touching your real library:

```bash
export FLYTIE_CONFIG_DIR=/tmp/ft_demo_config
export FLYTIE_DATA_DIR=/tmp/ft_demo_data
export PATH="$HOME/.local/bin:$PATH"   # adjust if in a venv
```

### Initialize

```bash
rm -rf /tmp/ft_demo_config /tmp/ft_demo_data   # clean slate
flytie init
# Initialized flytie database at /tmp/ft_demo_data/flytie.sqlite3

flytie info
# Database path       /tmp/ft_demo_data/flytie.sqlite3
# Config file         /tmp/ft_demo_config/config.toml
# Data directory      /tmp/ft_demo_data
# Schema revision     5af955bd607b
# Patterns            0
# Tags                0
# Species             0
```

### Add a pattern

```bash
flytie add "Parachute Adams" \
  --hook 14 \
  --difficulty 3 \
  --notes "Classic dry fly, versatile mayfly imitation" \
  -m "dry fly hook,hook,1" \
  -m "olive dubbing,dubbing,0.1,oz" \
  -m "grizzly hackle,hackle,2,feather" \
  -m "white calf hair,tail,1,pinch" \
  -t "dry" -t "mayfly" \
  -s "rainbow trout" -s "brown trout"
# Added Parachute Adams (v1)
```

### List and view

```bash
flytie list
# Table: Name / Hook / Tags / Species

flytie list --tag dry
# Filters to patterns tagged "dry"

flytie view "Parachute Adams"
# Full detail panel — materials, notes, version number, timestamps
```

### Search

```bash
flytie search "adams"
# Returns Parachute Adams (searches name, instructions, notes, material names)
```

### Edit (creates a new immutable version)

```bash
flytie edit "Parachute Adams" --hook 12-16 --notes "Works well in riffles"
# Edited Parachute Adams → v2

flytie versions "Parachute Adams"
# v1 (original)  v2 (current)

flytie diff "Parachute Adams" 1 2
# Unified diff showing hook size and notes changes
```

### Shop

```bash
flytie shop --pattern "Parachute Adams" --format markdown
# ## Shopping List (deduplicated)
# - dry fly hook
# - grizzly hackle
# ...
```

### Export --html (no WeasyPrint required)

```bash
flytie export "Parachute Adams" --html > /tmp/adams.html
# Styled HTML written to stdout; redirect to a file or pipe to a browser
```

### Export-db and import-db round trip

```bash
flytie export-db --out /tmp/my-patterns.json
# Exported 1 pattern(s) to /tmp/my-patterns.json

# Simulate importing into a fresh library
export FLYTIE_DATA_DIR=/tmp/ft_demo_data_import
flytie init
flytie import-db /tmp/my-patterns.json
# Import complete.
#   created: 1

flytie list
# Parachute Adams is present

# Restore original data dir
export FLYTIE_DATA_DIR=/tmp/ft_demo_data
```

---

## 3. Where data lands

### Database

- Default: `{platformdirs.user_data_dir("flytie")}/flytie.sqlite3`
  - macOS: `~/Library/Application Support/flytie/flytie.sqlite3`
  - Linux: `~/.local/share/flytie/flytie.sqlite3`
- Override priority: `FLYTIE_DB_PATH` env var > `database.path` config key > default
- `flytie info` always shows the resolved path — run it to confirm ground truth.
- WAL mode is always on (`PRAGMA journal_mode=WAL`). Expect
  `flytie.sqlite3-wal` and `flytie.sqlite3-shm` sidecar files next to the DB
  during active writes; they merge back on clean connection close. Include them
  in backups.

### Config file

- Default: `{platformdirs.user_config_dir("flytie")}/config.toml`
  - macOS: `~/Library/Preferences/flytie/config.toml`
  - Linux: `~/.config/flytie/config.toml`
- Override: `FLYTIE_CONFIG_DIR` env var sets the directory.
- `flytie config path` prints the resolved path.
- Written atomically (tmp + `os.replace`); a crash never corrupts it.

### AI suggestion persistence

After each `flytie suggest` run, results are saved to:
`{data_dir}/last_suggestions.json`

Only the most recent run is kept — a new `suggest` call overwrites the file.
This is what `flytie add --from-suggestion <n>` reads (1-based index matching
the display order from `flytie suggest`). If no `suggest` has been run yet,
`--from-suggestion` fails with an error message telling you to run it first.
Source: `src/flytie/core/suggestions.py`, constant `SUGGESTIONS_FILENAME`.

### PDF and HTML export output

- `--out path/to/card.pdf` → exact path (`.pdf` extension present)
- `--out path/to/dir` or `--out path/to/dir/` (no `.pdf` extension, or
  existing directory) → treated as a directory; auto-named card written inside
- `--out` omitted → current working directory, auto-named
- `--html` → stdout only; no file written
- Batch export (`--tag` or `--species`) always writes to a directory, never to
  a single file; `--html` cannot be combined with batch export

---

## 4. Destructive-operation guards

| Operation | Guard | Non-TTY / scripting behavior |
|-----------|-------|------------------------------|
| `delete <name>` | Interactive confirm unless `--yes` / `-y` | Refuses with exit 2 without `--yes` when stdin is not a TTY |
| `delete --hard` | Same confirm, labeled "permanently delete" | Same requirement |
| `undelete <name>` | None — safe operation | n/a |
| `init --force` | No confirm; drops and recreates schema | Data loss is permanent |
| `import-db --on-conflict skip` | Default; skips colliding names | No prompt |
| `import-db --on-conflict overwrite` | Replaces pattern and all its versions | No prompt; fully transactional |
| `import-db --on-conflict rename` | Appends numeric suffix to colliding names | No prompt; reports each rename |
| `restore <name> <v>` | Appends old version as new current; no history is rewritten | No guard needed |

All `import-db` modes are a single transaction: if anything fails, the DB is
left completely unchanged.

Soft-delete (`delete` without `--hard`) sets `is_deleted=True`. The pattern
is hidden from `list`, `view`, and `shop` but remains in the DB. Recover with
`undelete`. Hard-delete removes all rows permanently; there is no recovery.

---

## 5. AI command operation (`suggest`)

### Requirements

- Set `ANTHROPIC_API_KEY` in the environment. It is never written to disk.
  `export ANTHROPIC_API_KEY=sk-ant-...`
- Install the `[ai]` extra: `pip install 'flytie[ai]'`

### Error when key is not set

Verified from `src/flytie/ai/suggest.py::resolve_api_key`:

```
No Anthropic API key found. Set the ANTHROPIC_API_KEY environment variable:
  export ANTHROPIC_API_KEY=sk-ant-...
flytie never stores the key on disk.
```

Exit code 2. No key material ever appears in error messages, logs, or
`flytie info` output.

### Error when `[ai]` extra is not installed

Exit code 3 with message: `"AI suggestions need the optional 'ai' extra.
Install with: pip install 'flytie[ai]'"`

### Normal operation

Before the API call, the CLI prints what is being sent:

```
Sending 4 pattern name(s) and their material lists to the Anthropic API.
Instructions and notes are never sent.
```

A spinner (`Consulting Codex…`) shows a live character count as the response
streams. After completion, results appear in a Rich panel and are saved to
`{data_dir}/last_suggestions.json`.

### Turning a suggestion into a pattern

```bash
# After a successful suggest run:
flytie add --from-suggestion 1
# Draft: materials were added with category 'other'.
# Use `flytie edit` to refine.
```

### Privacy boundary

Only `pattern.name`, `version.hook_size`, and `material.canonical_name` fields
are sent as grounding context. The boundary is enforced in
`src/flytie/ai/suggest.py::build_prompt`. New fields added to `PatternVersion`
must NOT be added to the prompt without an explicit privacy review.

---

## 6. Release runbook

**Do not skip step 0.**

### (0) All quality gates must be green

See `flytie-change-control` for the full specification. Quick reference:

```bash
ruff format --check src tests
ruff check src tests
mypy src
pytest --cov=src/flytie --cov-report=term-missing   # 85% floor via fail_under
pytest -m smoke                                     # exactly 5 tests, ~3 s
```

### (1) Bump the version — single source of truth

Edit `src/flytie/__init__.py`:

```python
__version__ = "0.2.2"   # new version
```

The tag pushed in step 5 must match this string exactly; `release.yml` asserts
it before building.

### (2) Update CHANGELOG.md

Add a new `[X.Y.Z] — YYYY-MM-DD` section (Keep-a-Changelog format) and
update the compare links at the bottom:

```markdown
[0.2.2]: https://github.com/finngidden/flytie/compare/v0.2.1...v0.2.2
[Unreleased]: https://github.com/finngidden/flytie/compare/v0.2.2...HEAD
```

### (3) Update README.md

Update the current-release version badge or mention.

### (4) Commit via the normal PR flow

Merge only after CI is green on the PR.

### (5) Tag and push

```bash
git tag v0.2.2
git push origin v0.2.2
```

Never force-push a tag. Never re-tag a version already published to PyPI —
bump the patch instead.

### (6) What release.yml does automatically

Triggered by a `v*` tag push. Three jobs in sequence (source:
`.github/workflows/release.yml`):

**test** (matrix: Python 3.10, 3.11, 3.12 on ubuntu-latest): installs
`[dev,pdf,ai]` plus native WeasyPrint libs (Pango, Cairo), runs
`ruff format --check`, `ruff check`, `mypy`, and
`pytest --cov=src/flytie --cov-report=term-missing` (85% gate enforced).

**build** (Python 3.12): runs a fail-fast version assertion before building:

```bash
TAG="${GITHUB_REF_NAME}"
VERSION="v$(grep -oP '__version__\s*=\s*"\K[^"]+' src/flytie/__init__.py)"
if [ "$TAG" != "$VERSION" ]; then
  echo "Pushed tag '$TAG' does not match package version '$VERSION'."
  exit 1
fi
```

If the assertion passes, `python -m build` produces sdist and wheel.

**publish**: downloads the build artifact and publishes to PyPI using Trusted
Publishing (OIDC, `pypi` environment, `id-token: write` permission). No API
token is stored in the repo.

### (7) Post-release verification

```bash
# Check the PyPI listing
open https://pypi.org/project/flytie/

# Smoke-test in a clean venv
python -m venv /tmp/flytie_verify
/tmp/flytie_verify/bin/pip install flytie==0.2.2
/tmp/flytie_verify/bin/flytie --version
# Expected: flytie 0.2.2
```

### Failure branches

| Failure point | Recovery |
|--------------|---------|
| Tag-assertion mismatch (build job fails) | **Gate first: confirm the publish job never ran** — check the workflow run on GitHub Actions AND that PyPI has no record of the version (`pip index versions flytie`, or the PyPI project page). Only if both confirm *never published* may you delete and re-push the same tag: `git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z`; fix `__version__`; commit; re-tag. **When in doubt, bump the patch to `X.Y.(Z+1)` instead** — do not re-push the same tag. |
| Test or build failure (publish never ran) | Same gate: positively confirm the publish job never ran and PyPI has no record of the version (workflow run + `pip index versions flytie`). If and only if confirmed unpublished, delete tag, fix, re-tag. Otherwise bump the patch instead of re-pushing the tag. |
| Publish failed after PyPI accepted the upload | NEVER delete or re-use the tag. Bump the patch to `X.Y.(Z+1)`, fix the issue, release that |

When in doubt: if PyPI has any record of a version number, treat it as
published. Bumping the patch is always safe.

---

## 7. Operating notes

**Cold-start budget.** `flytie --version` must complete in under 600 ms
(best of 5). Heavy deps (`weasyprint`, `anthropic`, `alembic`) stay lazy; a new
top-level import of any of them breaks this gate. Diagnose with
`python -X importtime -m flytie --version 2>importtimes.log` — the full
importtime-parsing walkthrough lives in `flytie-diagnostics-and-tooling` §5.

**`flytie info` against an incompatible DB.** If a newer flytie ran a migration
this build does not recognize, all commands except `info` exit with code 4.
`info` still works and reports the compatibility warning so you can read the DB
path and plan recovery. Recovery: install the newer flytie, run
`export-db --out backup.json`, then on the older build `init --force` followed
by `import-db backup.json`.

**Exit code 4.** Means `IncompatibleDatabaseError` — the DB schema is ahead of
this binary's bundled migrations. See `flytie-config-and-flags` for the
complete exit-code table (1 = data error, 2 = input/validation error,
3 = missing dependency, 4 = incompatible environment, 130 = user cancellation).

---

## Provenance and maintenance

Written 2026-07-02 against v0.2.1.

**Sources verified:**

| Source | What was checked |
|--------|-----------------|
| `flytie --help` (run live) | Full command list; confirmed 21 top-level entries (includes command groups `tag`, `material`, `config`) |
| `src/flytie/cli.py` (complete read) | All command signatures, flags, guards, confirm logic |
| `src/flytie/config.py` | Path resolution, env var names, precedence chain |
| `src/flytie/db.py` | WAL pragma, `validate_compatibility`, `IncompatibleDatabaseError` |
| `src/flytie/core/suggestions.py` | `SUGGESTIONS_FILENAME`, data-dir path, save/load behavior |
| `src/flytie/ai/suggest.py` | `resolve_api_key`, `build_prompt`, error messages, streaming |
| `src/flytie/pdf/export.py` | `--out` extension logic, `--html` path, `PDFDependencyError` |
| `src/flytie/models.py` | `MATERIAL_CATEGORIES` (13 values) |
| `.github/workflows/release.yml` (complete read) | Job names, matrix, tag-assertion script, publish mechanism |

**Re-verify commands:**

```bash
flytie --help                       # re-derive full command list
flytie <cmd> --help                 # re-verify flags per command
cat src/flytie/__init__.py          # confirm current version string
cat .github/workflows/release.yml  # confirm release pipeline details
```
