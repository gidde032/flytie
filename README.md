# flytie — Fly Tying Recipe Manager

A local-first, AI-augmented command-line tool for managing fly tying patterns.
Tag and search your patterns, track every tweak with automatic versioning,
generate trip-ready deduplicated shopping lists, export printable pattern
cards, and ask Claude for recommendations grounded in your own library.

**New to flytie?** Start with the [Quickstart](docs/quickstart.md) — it walks
through a full workflow in about ten minutes.

Everything lives in a single local SQLite file — no account, no server, and no
network access unless you explicitly run `flytie suggest`.

## What it does

- **Manage patterns** — a pattern stores a name, hook size, materials list
  (with optional category, quantity, and unit per material), target species,
  tags, and notes. Add, list, view, search, edit, delete, and restore patterns
  from the terminal.
- **Plan trips** — pick a set of patterns by name, tag, or species; `flytie shop`
  aggregates all their materials into one deduplicated list. That list is your
  fly shop order before a trip.
- **Export pattern cards** — render a styled pattern card to PDF or HTML.
  The card includes the full materials list, hook details, and notes — one
  page per fly, ready to print or open in a browser.
- **Get AI suggestions** — `flytie suggest` sends your species, season, and
  water conditions to Claude and streams back fly recommendations grounded in
  your own library. Patterns you already own are flagged; new ones are labeled
  so you know what to tie or buy.
- **Version automatically** — every edit creates an immutable snapshot.
  Diff any two versions, view the full history, and restore an old one.
  Diffs sort materials alphabetically so reordering alone produces no noise.
- **Clean up materials** — `flytie material merge` rewrites all references
  from one material name to another across your entire library and version
  history. `flytie material dedupe` finds likely duplicates using fuzzy
  matching and walks you through merging them interactively.
- **Library stats** — `flytie stats` shows pattern, material, species, and
  tag counts; top-5 rankings; and timeline info at a glance.
- **Stay portable** — export your whole library to a single JSON file and
  import it on any machine.

## Install

```bash
pip install flytie               # core CLI + styled HTML pattern cards
pip install "flytie[pdf]"        # + PDF export (needs the native libs below)
pip install "flytie[ai]"         # + AI suggestions
pip install "flytie[pdf,ai]"     # everything
```

The core install includes Jinja2, so `flytie export <name> --html` produces a
styled, printable HTML pattern card on a bare `pip install flytie` — no
extras, no native libraries. Any browser can open and print the resulting
file. Choose the `[pdf]` extra only when you specifically want PDF output.

### PDF export native dependencies

The `[pdf]` extra installs WeasyPrint, which depends on the native Pango /
Cairo / GdkPixbuf libraries. These are **not** Python packages and must be
installed at the OS level:

```bash
# macOS
brew install pango

# Debian / Ubuntu
sudo apt install libpango-1.0-0 libpangoft2-1.0-0

# Fedora / RHEL
sudo dnf install pango

# Windows
# See https://doc.courtbouillon.org/weasyprint/stable/first_steps.html
```

If installing the native libraries isn't an option on your platform, stick
with the core install and use `flytie export <name> --html` for printable
output.

**macOS note:** install Pango via Homebrew (`brew install pango`) *before*
running `pip install "flytie[pdf]"`. On some macOS + Python combinations
(notably Python installed via Anaconda when Homebrew's Pango is also
present), importing WeasyPrint without a matching native Pango can
SIGSEGV the interpreter rather than raise a clean `ImportError`. Running
`brew install pango` first avoids the binary incompatibility.

## 60-second example

```bash
# 1. Create your local database (run once)
flytie init

# 2. Add a pattern — the Parachute Adams is a classic dry fly for trout.
#    Hook size 14 is a mid-size hook. Tag it "dry" so you can find it later.
#    Each material follows the format: name, category, quantity, unit
#    (only the name is required; the rest are optional but help with shopping lists)
flytie add "Parachute Adams" \
  --hook 14 \
  --species "brown trout" \
  --tag dry \
  --material "grizzly hackle,hackle,1,feather" \
  --material "adams gray dubbing,dubbing" \
  --material "white calf body hair,wing"

# 3. List your library and view the full pattern
flytie list
flytie view "Parachute Adams"

# 4. Generate a shopping list for all your dry flies before a trip
flytie shop --tag dry

# 5. Export a printable pattern card
flytie export "Parachute Adams" --out ~/cards/     # PDF (needs [pdf] extra)
flytie export "Parachute Adams" --html             # styled HTML, no extras needed
```

## Documentation

Full guides live in [`docs/`](docs/index.md):

- [Quickstart](docs/quickstart.md) — install and your first pattern
- [Command reference](docs/commands.md) — every command and option
- [Shopping list cookbook](docs/shopping-list.md)
- [AI suggestions](docs/ai-suggestions.md)
- [Migrating from a notebook](docs/migrating-from-notebook.md)
- [Export JSON schema](docs/json-schema.md)

Every command also has built-in help: `flytie <command> --help`.

## Project status

Current release: `0.2.1`. See [`CHANGELOG.md`](CHANGELOG.md) for the full
release history.

## Development

```bash
pip install -e ".[dev,pdf,ai]"
pre-commit install --hook-type pre-commit --hook-type pre-push
pytest
ruff check src tests
mypy src
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for what runs at each hook stage,
how to enable pre-commit.ci, and the formatter / coverage / smoke-test
contracts.

## License

MIT — see [`LICENSE`](LICENSE).
