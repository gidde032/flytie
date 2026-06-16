# Fly Tying Recipe Manager — Development Outline & Spec Requirements

A command-line tool for fly tiers to store, search, version, and share their tying patterns; generate trip-ready shopping lists; export pattern cards to PDF; and request AI-driven pattern suggestions tailored to species, season, and water.

---

## 1. Project Overview

### Vision
Fly tiers currently scatter their patterns across notebooks, text files, photos, and memory. This tool replaces that with a structured, local-first, AI-augmented CLI that treats each pattern as a versioned record with searchable metadata, deduplicable materials, and printable artifacts.

### Target Users
Hobbyist and competitive fly tiers, guides who maintain pattern catalogs for clients, and fly shops that want a portable inventory-aware reference. Users are assumed to be comfortable on the command line.

### Success Criteria
A user can install the tool from PyPI, add five patterns in under ten minutes, generate a deduplicated shopping list for a weekend trip, export any pattern as a printable PDF card, and receive a contextually grounded AI suggestion in under five seconds for a given water and season.

---

## 2. Technical Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.10+ | Mature ecosystem for CLI, ORM, PDF, AI; CI matrix covers 3.10 / 3.11 / 3.12 |
| CLI Framework | Typer + Rich | Type-hint-driven commands, formatted tables, color, progress bars |
| Storage | SQLite via SQLAlchemy 2.x | Local, zero-config, portable, no server |
| Migrations | Alembic | Schema evolution across versions |
| PDF Export | WeasyPrint | HTML/CSS-styled pattern cards |
| AI Agent | Anthropic Claude API (`claude-sonnet-4-6` or current) | Streaming structured suggestions |
| Templating | Jinja2 | Pattern card HTML templates |
| Testing | pytest + pytest-cov | Unit, integration, snapshot coverage |
| Linting/Formatting | ruff (handles both lint and format; Black-compatible output) | Single-tool linting + opinionated formatting |
| Type Checking | mypy | Catch type errors before runtime |
| Packaging | hatchling + pyproject.toml | Modern, PEP 621–compliant build |
| Distribution | PyPI via Trusted Publishing (GitHub Actions OIDC) | No shared secrets; release workflow triggers on tag |
| CI | GitHub Actions | Lint, type-check, test on PR and tag |

---

## 3. Functional Requirements

### FR-1 — Pattern Management
The tool must allow users to create, read, update, delete, list, and search fly tying patterns. Each pattern has a unique name (case-insensitive), a hook size (or range), a list of materials with quantities and notes, freeform tying instructions, a list of target species, a list of tags, an optional difficulty rating, and free-form notes. All patterns are scoped to a single user-local database file.

### FR-2 — Versioning
Every edit to a pattern produces a new immutable version row preserving the prior state. Users can list versions for a pattern, view a specific historical version, and diff two versions (text-level diff of materials and instructions). Restoring an older version creates a new version (no destructive rewinds). The `edit` command never changes a pattern's display name implicitly; renaming is an explicit opt-in via an `--rename-to` flag, which protects against accidental case changes and against a `--from-file` payload whose name differs from the edit target.

### FR-3 — Tagging & Search
Tags are arbitrary strings attached to patterns. Users can list patterns filtered by any combination of tag, target species, hook size range, and full-text match against pattern name, instructions, notes, and material names. (Instructions are searched in addition to the original spec's "name, materials, and notes" because tying-step text is the most distinctive descriptor of a pattern in many libraries, and excluding it produced too many false negatives in practice.) Search results render as a Rich table with column highlighting.

A `flytie tag list` subcommand prints every tag currently in use, with the number of patterns each is attached to, so the user can discover what selectors are available before running `flytie list --tag <name>`. A separate `flytie info` command prints resolved paths (database, config, data directory), the schema revision, and pattern/tag/species counts — the canonical "where am I?" diagnostic.

### FR-4 — Shopping List Generation
Given one or more pattern names, tags, or species, the tool aggregates required materials, deduplicates by canonical material name, and sums quantities where units match. Output is a Rich table grouped by material category (thread, hook, hackle, dubbing, flash, etc.) with a `Qty` column carrying the summed total per material. A material that was recorded without a numeric quantity renders as `?` so the user sees it on the trip list without a misleading zero. Exportable to plain text, Markdown, and JSON.

### FR-5 — PDF Pattern Cards
The `export` command renders a single pattern (or a batch selected by `--tag` / `--species`) to a styled PDF using an HTML/CSS template. The card includes pattern name, hook size, full materials list, tying steps, target species, tags, and the version number. Users can choose a built-in template or supply a custom CSS file. Output filename and destination directory are configurable. A `--html` flag renders the styled HTML card to stdout instead of a PDF; this path needs only Jinja2, not WeasyPrint or its native libraries, so it serves as a fallback for users who cannot install the `pdf` extra's native dependencies (Pango/Cairo).

### FR-6 — AI Suggestions
The `suggest` command accepts required `--species` and `--season` parameters, plus optional `--water` (e.g., "Henry's Fork"), `--conditions` (e.g., "low and clear"), and `--n` for number of suggestions. It composes a structured prompt with relevant patterns from the local DB as context, calls the Claude API, and streams a recommendation with reasoning back to the terminal. Output includes pattern name (existing or proposed), hook size, key materials, and a one-sentence rationale.

### FR-7 — Import / Export (Portability)
Users can export the full database or a filtered subset to a JSON file with a documented schema, and import a JSON file (with conflict resolution: skip, overwrite, or rename). This enables sharing pattern collections across machines and contributing to community pattern sets.

### FR-8 — Configuration
A `config` command manages user-scoped settings: database path, default PDF template, and default output directory. The `config` command exposes `get`, `set`, `path`, and `show` subcommands. Settings persist in `~/.config/flytie/config.toml` and are written atomically (tmp file + rename) so a crash never corrupts the file.

The Anthropic API key is **not** a config-file-managed setting: it is read only from the `ANTHROPIC_API_KEY` environment variable and is never written to disk, so it cannot leak through the config file. This is a deliberate data-minimization choice.

Three environment variables override resolved paths, primarily for testing and for users who keep their data outside the platform default location: `FLYTIE_DB_PATH` (database file), `FLYTIE_CONFIG_DIR` (config directory), and `FLYTIE_DATA_DIR` (data directory). Precedence is environment variable > config file > built-in default.

---

## 4. Non-Functional Requirements

**Performance.** CLI startup under 600 ms (best-of-5 `flytie --version` invocations — measures the tool's import surface after the OS filesystem cache is warm, which is a one-time cost the CLI does not control). Search across 5,000 patterns under 100 ms. PDF render under 1.5 s per card. AI suggestion first token under 2 s on a healthy connection. The 600 ms budget is enforced by a regression test added in v0.1.2; an earlier 300 ms target proved tight against real CI hardware and made the gate flaky without measurably improving the user experience. The gate's purpose is to catch regressions in the import graph (e.g. someone re-introducing an eager `import weasyprint` or `import anthropic` at module top level) rather than to chase the last 100 ms.

**Reliability.** Database writes are transactional. A failed import leaves the DB unchanged. A crash mid-AI-stream does not corrupt local state.

**Portability.** Runs on macOS, Linux, and Windows (WSL acceptable for WeasyPrint dependencies; document native Windows caveats). `pip install flytie` is sufficient for the core CLI on supported platforms. The optional `pdf` extra additionally requires native libraries (Pango / Cairo) installed at the OS level — `brew install pango` on macOS, `apt install libpango-1.0-0` on Debian/Ubuntu, `dnf install pango` on Fedora/RHEL; the README documents this, and `flytie export --html` is a no-native-deps fallback.

**Usability.** Every command has `--help` with examples. Error messages name the failing input and suggest a fix. Rich tables degrade gracefully on non-TTY output.

**Privacy & Security.** No telemetry. The API key is read only from the `ANTHROPIC_API_KEY` environment variable, never written to the config file or any other on-disk location, and never logged. Only pattern names and material lists relevant to the query are sent to the Claude API; never the full database.

**Maintainability.** Test coverage above 85% on core modules (models, search, shopping list, import/export). Public functions and CLI commands have docstrings. Schema changes ship with Alembic migrations.

---

## 5. Data Model

The schema is normalized to keep materials canonical and versioning clean. It evolves via Alembic migrations; the tables below reflect the current state.

`patterns` — id, name, current_version_id, is_deleted, created_at, updated_at. The name is stored as two columns: `name_key` (lowercased, whitespace-collapsed canonical form, carrying the UNIQUE constraint) and `name_display` (the form shown to the user). This is how case-insensitive uniqueness is implemented portably on SQLite. `is_deleted` supports soft deletes.

`pattern_versions` — id, pattern_id, version_number, hook_size, difficulty, instructions, notes, created_at. Soft-immutable: new edits insert a new row.

`materials` — id, canonical_name (unique), category, default_unit. The category is constrained at the application level to one of: thread, hook, hackle, dubbing, flash, body, tail, wing, head, bead, weight, adhesive, other. An unknown category is rejected with an actionable error.

`pattern_materials` — id, pattern_version_id, material_id, quantity, unit, position (ordering), notes.

`species` — id, name (unique).

`pattern_species` — pattern_id, species_id (many-to-many; species attaches to the pattern, not the version, since target species rarely changes per tweak).

`tags` — id, name (unique).

`pattern_tags` — pattern_id, tag_id.

Configuration is **not** stored in the database. User-scoped settings live in a TOML file at `~/.config/flytie/config.toml` (see FR-8); this is simpler than a DB table, keeps config human-editable, and avoids a migration for what is a handful of key/value pairs. There is therefore no `config` table in the schema.

---

## 6. Development History

The v0.1.0 build was organized into six phases (foundation → core CLI → versioning & shopping list → PDF export → AI suggestions → polish & publish). Each phase ended with a usable increment, a tagged commit, and passing CI. Detailed write-ups of each phase live in `phase-summaries/phase-{1..6}.md`.

Two design decisions made during implementation are worth recording here because they shaped the CLI contract:

- **Flag-driven over interactive.** The original plan proposed interactive prompts for adding materials and an `$EDITOR` integration for `edit`. Both were superseded by repeatable `--material` flags and a `--from-file` path (JSON or TOML). Every command stays scriptable, every edit is recordable from shell history, and `--from-file` covers the bulk-input case the interactive prompt was meant for.
- **TOML over YAML for `--from-file`.** YAML support was dropped in favor of TOML (already a project dependency via the config file) so the JSON/TOML pair shares one parser with no extra runtime cost.

Post-v0.1.0 development follows the same phase-shaped workflow for features and a hardening-pass shape for quality releases. See `ROADMAP.md` for planned work.

---

## 7. Testing Strategy

Unit tests cover models, validators, the shopping list aggregation algorithm, and the AI prompt-construction logic. Integration tests exercise full command paths against a temporary SQLite DB using a pytest fixture that yields an isolated `Database` per test. Snapshot tests cover Rich-rendered tables (using `syrupy`) and PDF text extraction (using `pdfminer.six`). The AI path is tested with a recorded transport that replays a canned streaming response; no real API calls run in CI. A `pytest -m smoke` marker exists for a five-test happy-path suite intended for quick local feedback.

Several testing contracts are enforced structurally rather than by convention: an 85% coverage floor via `[tool.coverage.report] fail_under`, a cold-start benchmark that fails if `flytie --version` exceeds 600 ms (catches import-graph regressions), an autouse `_wide_cli_runner_env` fixture that sets `COLUMNS=200` to eliminate Rich wrap noise during test authoring, a subprocess probe that verifies the installed entry point resolves correctly, and a pre-push hook that re-runs tests at `COLUMNS=80` as a narrow-terminal safety net. The smoke marker count (exactly five tests) is itself regression-tested. See `CONTRIBUTING.md` for the full hook layout and CI gate details.

---

## 8. Risks & Mitigations

**WeasyPrint native dependencies.** Pango and Cairo can be painful on Windows. Current state: CI tests on Linux + macOS, the README documents WSL for Windows, and `flytie export --html` provides a no-native-deps fallback that produces a styled standalone HTML card printable from a browser.

**Material deduplication.** "Size 14 dry fly hook" and "14 dry hook" are the same thing to a tier but different strings to a database. Current state: canonical material table with exact-match dedup on write (v0.1.0), `flytie material merge` for manual dedup (v0.2.0), `flytie material dedupe` for edit-distance-based candidate discovery (v0.2.1). Semantic matching via Claude API is a candidate for a future release (see `ROADMAP.md`).

**AI hallucination.** Suggestions may name materials or flies that don't exist. Current state: the prompt grounds suggestions in the user's existing pattern library, the response schema requires a rationale, and novel suggestions are flagged `[NEW]` so the user verifies before adding.

**Schema evolution.** Database changes after release can break user data. Current state: every schema change ships with an Alembic migration, the app refuses to start against a DB newer than its known head, and `flytie export-db` is recommended in release notes before upgrades.

---

## 9. Open Questions

All original open questions have been resolved or moved to the feature pipeline. See `ROADMAP.md` for candidate features and their current status.

---

## 10. Definition of Done

A release is shippable when: all quality gates pass (ruff format, ruff check, mypy, pytest with 85% coverage floor, cold-start benchmark), the tag version matches `__version__` in `src/flytie/__init__.py`, `CHANGELOG.md` has an entry for the release, documentation is updated, and CI is green on `main` and on the tag. The user-facing acceptance bar remains: a new user can `pip install flytie`, run `flytie init`, add patterns, generate a shopping list, export a PDF card, and request an AI suggestion within the first ten minutes.
