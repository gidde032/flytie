# Quickstart

This guide takes you from an empty machine to a versioned pattern library, a
shopping list, a PDF card, and an AI suggestion — in about ten minutes.

## 1. Install

```bash
pip install flytie               # core CLI + styled HTML cards
pip install "flytie[pdf]"        # + PDF export
pip install "flytie[ai]"         # + AI suggestions
pip install "flytie[pdf,ai]"     # everything
```

The core install is pure Python and is enough on its own to manage patterns,
build shopping lists, and produce styled, printable HTML pattern cards via
`flytie export <name> --html`. The `[pdf]` extra adds WeasyPrint and its
native Pango/Cairo dependencies (see the
[README](../README.md#pdf-export-native-dependencies) for the OS install);
choose it only when you specifically want PDF output instead of HTML.

## 2. Create your database

```bash
flytie init
```

This creates a local SQLite database and applies the schema. Run it once. To
see where flytie keeps your data, run:

```bash
flytie info
```

That shows the resolved database path, the config file path, the data
directory, and (after `init`) the current schema revision and pattern count.
`flytie info` is the safe "where am I?" command — it works before `init` and
even against a database the binary can't fully understand (in which case it
prints a compatibility warning and exits cleanly). `flytie config path` is a
different command that prints the location of the TOML config file
specifically; `flytie info` is what you want for an end-to-end check.

## 3. Add your first pattern

A pattern has a name, a hook size, and a list of materials. Each material is
written as `name,category,quantity,unit` — only the name is required:

```bash
flytie add "Parachute Adams" \
  --hook 14 \
  --species "rainbow trout" \
  --tag dry --tag mayfly \
  --material "grizzly hackle,hackle,1,feather" \
  --material "adams gray dubbing,dubbing" \
  --material "white calf body hair,wing"
```

Valid material categories are: `thread`, `hook`, `hackle`, `dubbing`, `flash`,
`body`, `tail`, `wing`, `head`, `bead`, `weight`, `adhesive`, `other`.

Prefer to keep patterns in files instead of long command lines? See
[Migrating from a notebook](migrating-from-notebook.md), which shows the
JSON/TOML pattern-file format and a loop for bulk-loading a directory of them.

## 4. Look at your library

```bash
flytie list                      # all patterns, as a table
flytie list --tag dry            # filtered by tag
flytie view "Parachute Adams"    # the full pattern card in the terminal
flytie search hackle             # full-text search across names and materials
```

## 5. Edit — and get versioning for free

Every edit creates a new immutable version; the old one is never lost:

```bash
flytie edit "Parachute Adams" --hook 16
flytie versions "Parachute Adams"          # see the history
flytie diff "Parachute Adams" 1 2          # what changed between v1 and v2
flytie restore "Parachute Adams" 1         # bring v1 back as a new version
```

## 6. Build a shopping list

Aggregate materials across any set of patterns and deduplicate them:

```bash
flytie shop --tag dry                      # everything tagged "dry"
flytie shop --pattern "Parachute Adams" --pattern "Zebra Midge"
```

A `?` in the Qty column means that material was recorded without a numeric
quantity — typical for things like thread that you buy by the spool rather
than counting individually. The line still appears in the shopping list; it
just doesn't sum across patterns.

See the [shopping list cookbook](shopping-list.md) for more.

## 7. Export a pattern card

```bash
flytie export "Parachute Adams" --out ~/cards/parachute-adams.pdf   # specific file
flytie export "Parachute Adams" --out ~/cards/                      # directory; auto-named
flytie export "Parachute Adams" --html                              # styled HTML to stdout
```

`--out` ending in `.pdf` writes that exact file; ending in `/` (or any path
with no extension) is treated as a directory and is created if missing.
The `--html` form works on a bare `pip install flytie` — no `[pdf]` extra,
no native libraries.

## 8. Ask Claude for a suggestion

Set your API key (read only from the environment, never stored):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
flytie suggest --species "rainbow trout" --season "late October" \
  --water "Henry's Fork" --conditions "low and clear"
```

See [AI suggestions](ai-suggestions.md) for what is and isn't sent to the API.

## 9. Back up or share your library

```bash
flytie export-db --out my-patterns.json    # whole library to JSON
flytie import-db my-patterns.json          # load it on another machine
```

## Next steps

- The full [command reference](commands.md) documents every option.
- [Migrating from a notebook](migrating-from-notebook.md) helps you bulk-load
  patterns you already have on paper or in text files.
