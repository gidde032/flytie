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
| Distribution | PyPI via `twine` / `hatch publish` | Standard Python ecosystem |
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

**Performance.** CLI startup under 300 ms cold. Search across 5,000 patterns under 100 ms. PDF render under 1.5 s per card. AI suggestion first token under 2 s on a healthy connection.

**Reliability.** Database writes are transactional. A failed import leaves the DB unchanged. A crash mid-AI-stream does not corrupt local state.

**Portability.** Runs on macOS, Linux, and Windows (WSL acceptable for WeasyPrint dependencies; document native Windows caveats). `pip install flytie` is sufficient for the core CLI on supported platforms. The optional `pdf` extra additionally requires native libraries (Pango / Cairo) installed at the OS level — `brew install pango` on macOS, `apt install libpango-1.0-0` on Debian/Ubuntu, `dnf install pango` on Fedora/RHEL; the README documents this, and `flytie export --html` is a no-native-deps fallback.

**Usability.** Every command has `--help` with examples. Error messages name the failing input and suggest a fix. Rich tables degrade gracefully on non-TTY output.

**Privacy & Security.** No telemetry. The API key is read only from the `ANTHROPIC_API_KEY` environment variable, never written to the config file or any other on-disk location, and never logged. Only pattern names and material lists relevant to the query are sent to the Claude API; never the full database.

**Maintainability.** Test coverage above 85% on core modules (models, search, shopping list, import/export). Public functions and CLI commands have docstrings. Schema changes ship with Alembic migrations.

---

## 5. Data Model (Initial Schema)

The schema is normalized to keep materials canonical and versioning clean.

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

## 6. Multi-Phase Development Plan

The work is organized into six phases. Each phase ends with a usable increment, a tagged commit, and passing CI.

### Phase 1 — Foundation (Week 1)

Set up the repository skeleton, tooling, and persistence layer. Initialize the Git repo with `pyproject.toml`, `src/flytie/` layout, ruff/black/mypy config, and a baseline GitHub Actions workflow running lint and tests on Python 3.10 / 3.11 / 3.12. Define the SQLAlchemy 2.x declarative models for `Pattern`, `PatternVersion`, `Material`, `PatternMaterial`, `Species`, `Tag`, and their relationships. Wire up Alembic with an initial migration. Build a `Database` helper that resolves the DB path from config, opens a session, and runs pending migrations on startup. Add a minimal `flytie init` command that creates the DB and confirms with Rich output. Write unit tests for model CRUD and relationship cascades.

**Phase 1 deliverables.** Installable package, `flytie init` works, schema migrations run cleanly, CI green on all PRs.

### Phase 2 — Core CLI Commands (Weeks 2–3)

Implement the pattern lifecycle commands using Typer. `flytie add` accepts pattern name, hook size, repeatable `--material` flags for materials (or a `--from-file` flag pointing to a JSON or TOML fragment — see [`docs/pattern-file-format.md`](docs/pattern-file-format.md)), tags, species, and notes. `flytie list` renders a Rich table of patterns with filters (`--tag`, `--species`, `--hook-size`). `flytie view <name>` displays a full pattern card in the terminal. `flytie search <query>` runs a full-text-style match (see FR-3 for the fields searched). `flytie edit <name>` accepts field flags and writes a new `PatternVersion`; renaming requires an explicit `--rename-to` flag (no `$EDITOR` integration in v0.1 — the flag surface is the contract, which keeps every edit scriptable and reviewable). `flytie delete <name>` requires confirmation; soft-delete by default with a `--hard` opt-in. Implement `flytie tag add/remove/list <name> <tag>`. Each command includes `--help` with examples. Add integration tests that exercise the SQLite layer end-to-end using a temp DB fixture.

The original spec proposed "an interactive prompt for materials" and "an interactive editor" for `edit`. Both were superseded by the flag-driven design above during implementation: every command stays scriptable, every edit is recordable from history, and the `--from-file` path covers the bulk-input case the interactive prompt was meant for. YAML support was dropped in favor of TOML (already a project dependency via the config file) so the JSON/TOML pair shares one parser with no extra runtime cost.

**Phase 2 deliverables.** A user can manage patterns entirely from the CLI with formatted output and persistent history.

### Phase 3 — Versioning & Shopping List (Week 4)

Promote versioning from a schema concept to a first-class feature. `flytie versions <name>` lists every version with timestamps. `flytie view <name> --version N` renders a historical version. `flytie diff <name> <v1> <v2>` shows a unified diff of materials and instructions. `flytie restore <name> <version>` creates a new version copied from the old one. Then build the shopping list: `flytie shop` accepts any combination of `--pattern`, `--tag`, `--species` flags (repeatable), aggregates the materials across all selected patterns, deduplicates by canonical material name, sums quantities where units match, and outputs a Rich table grouped by material category. Add `--format markdown|text|json` for non-TTY workflows and `--exclude` to drop materials the user already owns. Snapshot tests cover the rendered output.

**Phase 3 deliverables.** Versioning is queryable and reversible without data loss; trip-ready shopping lists generate in one command.

### Phase 4 — PDF Export (Week 5)

Render pattern cards to PDF using WeasyPrint with a Jinja2 HTML template and a default CSS stylesheet stored alongside the package. `flytie export <name>` writes a single PDF to the current directory; `flytie export --tag dryfly --out cards/` exports a batch. The default template includes a header (pattern name + hook size), a two-column body (materials on the left, instructions on the right), a footer with version and target species, and space for a future photo field. Allow `--template custom.html` and `--css custom.css` overrides. Add a `--photo path.jpg` option that, if WeasyPrint can locate the file, embeds it into the card. Snapshot-test rendered PDFs with `pdfminer.six` text extraction to assert key fields appear.

**Phase 4 deliverables.** Printable, styled pattern cards as PDFs; documented template override path; deterministic snapshot tests.

### Phase 5 — AI Suggestions (Week 6)

Integrate the Anthropic Claude API. The `suggest` command takes `--species`, `--season`, `--water`, and `--conditions`, queries the local DB for patterns that match the species or relevant tags, builds a prompt that includes those patterns as context, and calls Claude with streaming enabled. The response is parsed for structured fields (recommended pattern name, hook size, key materials, rationale) and rendered as a Rich panel with streaming output. Patterns suggested by Claude that already exist in the DB are highlighted; novel suggestions get a `[NEW]` badge and a hint to add them with `flytie add`. (A `flytie add --from-suggestion` shortcut that pre-fills a new pattern directly from a suggestion is **deferred to a later version (v0.2)** per the open-questions deferral; Phase 5 ships only the plain-`flytie add` hint.) The API key is read only from the `ANTHROPIC_API_KEY` environment variable, never from the config file (see FR-8). All API errors fall back to a clear, actionable terminal message. Mock the API in tests using `responses` or a fixture transport so CI does not consume real credits.

**Phase 5 deliverables.** Live AI suggestions grounded in the user's pattern library, with streaming output, structured rendering, and no network calls in tests.

### Phase 6 — Polish, Portability & Publish (Week 7)

Implement `flytie export-db --out patterns.json` and `flytie import-db patterns.json` with `--on-conflict skip|overwrite|rename`. Validate imports against a documented JSON Schema. Write user-facing documentation in `docs/` with a quickstart, command reference, shopping list cookbook, AI prompt tips, and a "from notebook to flytie" migration guide. Add a `flytie --version` flag and a changelog driven by `towncrier` or hand-curated. Configure trusted publishing to PyPI via GitHub Actions on tagged releases. Cut `0.1.0`. Open the repo for feedback, file follow-up issues for v0.2 (photo support, mobile companion, fly box inventory tracking), and write a launch post.

**Phase 6 deliverables.** Patterns are portable across machines, the tool is installable from PyPI, documentation is published, and a 0.1.0 tag exists.

---

## 7. Testing Strategy

Unit tests cover models, validators, the shopping list aggregation algorithm, and the AI prompt-construction logic. Integration tests exercise full command paths against a temporary SQLite DB using a pytest fixture that yields an isolated `Database` per test. Snapshot tests cover Rich-rendered tables (using `syrupy`) and PDF text extraction (using `pdfminer.six`). The AI path is tested with a recorded transport that replays a canned streaming response; no real API calls run in CI. A `pytest -m smoke` marker exists for a five-test happy-path suite intended for quick local feedback.

---

## 8. Risks & Mitigations

WeasyPrint has native dependencies (Pango, Cairo) that can be painful on Windows. Mitigation: document the WSL recommendation, test on Linux + macOS in CI, and provide a `--format html` fallback that produces a styled standalone HTML card so users without WeasyPrint can still print from a browser.

Material deduplication is hard because "size 14 dry fly hook" and "14 dry hook" are the same thing to a tier but different strings to a database. Mitigation: introduce a canonical material table populated on first write, with a `--alias` command for users to merge variants. Defer fuzzy auto-merging to v0.2.

AI suggestions risk hallucinating materials or fly names. Mitigation: the prompt explicitly grounds suggestions in the user's existing pattern library, the response schema requires a rationale, and novel suggestions are flagged `[NEW]` so the user can verify before adding.

Schema evolution after release can break user databases. Mitigation: every schema change ships with an Alembic migration, the app refuses to start against a DB newer than its known head, and `flytie export-db` is recommended in release notes before upgrades.

---

## 9. Open Questions

Should patterns support image attachments in v0.1, or defer to v0.2? Current plan defers to keep the schema simple and avoid blob storage decisions.

Should the AI suggestion command be able to write a draft pattern directly into the DB, or only print a recommendation? Current plan: print only in v0.1, with `flytie add --from-suggestion <id>` queued for v0.2.

Should there be a fly box / inventory module that subtracts owned materials from generated shopping lists by default? Promising for v0.2; out of scope for v0.1 to avoid scope creep.

---

## 10. Definition of Done (v0.1.0)

The package is installable from PyPI on macOS and Linux with a single `pip install flytie`. A new user can run `flytie init`, add three patterns, generate a shopping list, export a PDF card, and request an AI suggestion within the first ten minutes. Test coverage is at or above 85% on `src/flytie/core/`. Documentation is published. CI is green on `main` and on the `v0.1.0` tag.
