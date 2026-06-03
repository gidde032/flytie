# flytie — Fly Tying Recipe Manager

A local-first, AI-augmented command-line tool for managing fly tying patterns.
Tag and search your patterns, track every tweak with automatic versioning,
generate trip-ready deduplicated shopping lists, export printable pattern
cards, and ask Claude for recommendations grounded in your own library.

Everything lives in a single local SQLite file — no account, no server, and no
network access unless you explicitly run `flytie suggest`.

## What it does

- **Manage patterns** — add, list, view, search, tag, edit, and delete tying
  patterns with structured hook sizes, materials, target species, and notes.
- **Version automatically** — every edit creates an immutable version; list
  the history, diff any two versions, and restore an old one.
- **Plan trips** — aggregate materials across any set of patterns into one
  deduplicated shopping list, excluding what you already own.
- **Export cards** — render a styled pattern card to PDF (or HTML).
- **Get suggestions** — `flytie suggest` asks the Anthropic Claude API for
  flies suited to a species, season, and water, grounded in your library.
- **Stay portable** — export and import your whole library as documented JSON.

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

## 60-second example

```bash
flytie init
flytie add "Parachute Adams" --hook 14 --tag dry \
  --material "grizzly hackle,hackle,1,feather"
flytie shop --tag dry                              # deduped shopping list
flytie export "Parachute Adams" --out ~/cards/     # printable PDF card
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

Current release: `0.1.1`. See [`CHANGELOG.md`](CHANGELOG.md) for the full
release history.

## Development

```bash
pip install -e ".[dev,pdf,ai]"
pytest
ruff check src tests
mypy src
```

## License

MIT — see [`LICENSE`](LICENSE).
