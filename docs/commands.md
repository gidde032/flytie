# Command reference

Every flytie command, its options, and a worked example. Anything here is also
available live with `flytie <command> --help`.

Global option: `flytie --version` prints the installed version and exits.

---

## `flytie init`

Initialize the local SQLite database and apply the schema. Run once before any
other command.

| Option | Meaning |
|---|---|
| `--force` | Re-create the schema even if the database already exists. |

```bash
flytie init
```

`--force` rebuilds the schema; it does not delete an existing database file
silently in normal use — only pass it when you intend to reset the schema.
If an earlier `init` was interrupted, the next plain `flytie init` will
detect the half-built state and repair it without `--force` (no data loss).

---

## `flytie info`

Print resolved paths and a quick library summary: database path, config file
path, data directory, current Alembic schema revision, and pattern / tag /
species counts. Safe to run before `flytie init` and against an incompatible
database (it reports the situation rather than failing).

```bash
flytie info
```

The Anthropic API key is **never** displayed by `info`. By design it lives
only in the `ANTHROPIC_API_KEY` environment variable and is never written to
disk; see [AI suggestions](ai-suggestions.md) for the policy in full.

---

## `flytie add`

Add a new pattern to the library. `NAME` is required and is case-insensitively
unique.

| Argument / Option | Meaning |
|---|---|
| `NAME` | Pattern name (required). |
| `--hook TEXT` | Hook size or range, e.g. `14` or `12-16`. |
| `--difficulty INTEGER` | Tying difficulty, 1–5. |
| `--instructions TEXT` | Free-text tying steps. |
| `--notes TEXT` | Free-text notes. |
| `-t, --tag TEXT` | A tag; repeatable. |
| `-s, --species TEXT` | A target species; repeatable. |
| `-m, --material TEXT` | A material line; repeatable (see below). |
| `--from-file PATH` | Load fields from a JSON or TOML file. See [Pattern file format](pattern-file-format.md). |

A material is written `name,category,quantity,unit` — only the name is
required. Valid categories: `thread`, `hook`, `hackle`, `dubbing`, `flash`,
`body`, `tail`, `wing`, `head`, `bead`, `weight`, `adhesive`, `other`.

For the structured `--from-file` form (when one-liners are inconvenient or
you're bulk-importing), see [Pattern file format](pattern-file-format.md).

```bash
flytie add "Parachute Adams" --hook 14 --difficulty 3 \
  -t dry -t mayfly -s "rainbow trout" \
  -m "grizzly hackle,hackle,1,feather" \
  -m "adams gray dubbing,dubbing"
```

With `--from-file`, any CLI flags you also pass layer on top of the file's
values.

---

## `flytie list`

List patterns as a table, ordered by name.

| Option | Meaning |
|---|---|
| `-t, --tag TEXT` | Only patterns with this tag. |
| `-s, --species TEXT` | Only patterns for this species. |
| `--hook-size TEXT` | Filter by hook size or range; `14` matches a pattern tied `12-16`. |
| `--include-deleted` | Also show soft-deleted patterns. |

```bash
flytie list --tag dry --hook-size 12-16
```

---

## `flytie view`

Show full details for a pattern: header, materials, instructions, and notes.

| Argument / Option | Meaning |
|---|---|
| `NAME` | Pattern name (required). |
| `--version INTEGER` | Show a specific historical version instead of the current one. |

```bash
flytie view "Parachute Adams"
flytie view "Parachute Adams" --version 1
```

---

## `flytie search`

Full-text search across pattern names, instructions, notes, and material names.

```bash
flytie search hackle
```

---

## `flytie edit`

Edit a pattern. **Every edit creates a new immutable version** — the previous
version is preserved.

| Argument / Option | Meaning |
|---|---|
| `NAME` | Pattern to edit (required). |
| `--hook`, `--difficulty`, `--instructions`, `--notes` | Field overrides. |
| `-t, --tag TEXT` | Set tags (repeatable). |
| `--clear-tags` | Remove all tags. |
| `-s, --species TEXT` | Set species (repeatable). |
| `--clear-species` | Remove all species. |
| `-m, --material TEXT` | Set materials (repeatable). |
| `--clear-materials` | Remove all materials. |
| `--rename-to TEXT` | Change the pattern's display name explicitly. |
| `--from-file PATH` | Load fields from a JSON/TOML file. |

If you don't pass materials, the previous version's materials carry over.
Renaming is only done via `--rename-to`, so an editing typo can't silently
rename a pattern. Passing both `--tag` and `--clear-tags` is an error.

```bash
flytie edit "Parachute Adams" --hook 16
flytie edit "Parachute Adams" --rename-to "Parachute Adams (olive)"
```

---

## `flytie delete`

Delete a pattern. Soft-delete by default (recoverable; hidden from `list`).

| Argument / Option | Meaning |
|---|---|
| `NAME` | Pattern to delete (required). |
| `--hard` | Permanently remove the pattern and its history. |
| `-y, --yes` | Skip the confirmation prompt. |

In a non-interactive shell, `--yes` is required.

```bash
flytie delete "Old Pattern"
flytie delete "Old Pattern" --hard --yes
```

---

## `flytie versions`

List every version of a pattern, oldest first, with timestamps.

```bash
flytie versions "Parachute Adams"
```

---

## `flytie diff`

Show a unified diff of materials and instructions between two versions.

| Argument | Meaning |
|---|---|
| `NAME` | Pattern name. |
| `V1` | Base version number. |
| `V2` | Compared version number. |

```bash
flytie diff "Parachute Adams" 1 2
```

---

## `flytie restore`

Restore an old version by appending a copy of it as a new version. This is
non-destructive — nothing is rewound.

```bash
flytie restore "Parachute Adams" 1
```

---

## `flytie shop`

Generate a deduplicated shopping list across any set of patterns. See the
[shopping list cookbook](shopping-list.md) for recipes.

| Option | Meaning |
|---|---|
| `-p, --pattern TEXT` | Include this pattern; repeatable. |
| `-t, --tag TEXT` | Include every pattern with this tag; repeatable. |
| `-s, --species TEXT` | Include every pattern for this species; repeatable. |
| `-x, --exclude TEXT` | Drop this material from the list (already owned); repeatable. |
| `-f, --format TEXT` | Output format: `table` (default), `markdown`, `text`, or `json`. |

```bash
flytie shop --tag dry --exclude "black thread" --format markdown
```

---

## `flytie export`

Export a pattern as a printable PDF card, or batch-export many. See the
[README](../README.md#pdf-export-native-dependencies) for the WeasyPrint
native dependencies, or use `--html` to skip them.

| Argument / Option | Meaning |
|---|---|
| `NAME` | Pattern name. Omit it and use `--tag`/`--species` for a batch export. |
| `-t, --tag TEXT` | Batch-export every pattern with this tag. |
| `-s, --species TEXT` | Batch-export every pattern for this species. |
| `--out PATH` | Output PDF file (path ending `.pdf`) or directory (path with no extension; created if missing). Default: current dir. |
| `--template PATH` | Custom Jinja2 HTML template. |
| `--css PATH` | Custom CSS stylesheet. |
| `--photo PATH` | Image to embed (single-pattern export only). |
| `--html` | Render styled HTML to stdout instead of a PDF — no WeasyPrint needed. |

```bash
flytie export "Parachute Adams" --out cards/                     # directory, auto-named
flytie export "Parachute Adams" --out cards/parachute-adams.pdf  # specific file
flytie export "Adams" --html > adams.html
flytie export --tag dry --out cards/                             # batch
```

---

## `flytie suggest`

Ask the Anthropic Claude API for fly suggestions grounded in your library. See
[AI suggestions](ai-suggestions.md) for setup and a privacy explanation.

| Option | Meaning |
|---|---|
| `-s, --species TEXT` | Target fish species (required). |
| `--season TEXT` | Season or time of year, e.g. `late October` (required). |
| `--water TEXT` | Water name, e.g. `Henry's Fork`. |
| `--conditions TEXT` | Water conditions, e.g. `low and clear`. |
| `--n INTEGER` | Number of flies to suggest, 1–10 (default 3). |

Requires the `ANTHROPIC_API_KEY` environment variable.

```bash
flytie suggest -s "rainbow trout" --season "late October" \
  --water "Henry's Fork" --conditions "low and clear" --n 5
```

---

## `flytie export-db`

Export patterns to a portable JSON file, including full version history. See
the [JSON schema](json-schema.md).

| Option | Meaning |
|---|---|
| `-o, --out PATH` | Path to write the JSON file (required). |
| `--tag TEXT` | Only export patterns with this tag. |
| `--species TEXT` | Only export patterns for this species. |
| `--include-deleted` | Also export soft-deleted patterns. |

```bash
flytie export-db --out my-patterns.json
flytie export-db -o dries.json --tag dry
```

---

## `flytie import-db`

Import patterns from a flytie JSON export file. The import is **transactional**
— if anything fails, the database is left completely unchanged.

| Argument / Option | Meaning |
|---|---|
| `PATH` | The JSON export file to import (required). |
| `--on-conflict TEXT` | When a name already exists: `skip` (default), `overwrite`, or `rename`. |

```bash
flytie import-db shared-patterns.json
flytie import-db backup.json --on-conflict overwrite
```

---

## `flytie tag`

Tag management. Three subcommands: `list`, `add`, `remove`.

```bash
flytie tag list                                # every tag in use, with counts
flytie tag add "Parachute Adams" dry mayfly
flytie tag remove "Parachute Adams" mayfly
```

`flytie tag list` shows only tags currently attached to at least one
non-deleted pattern, so the output matches what `flytie list --tag <name>`
would return.

---

## `flytie config`

Manage user-scoped settings, stored in a TOML file.

| Subcommand | Meaning |
|---|---|
| `flytie config path` | Print the location of the config file. |
| `flytie config show` | Show all configured settings. |
| `flytie config get KEY` | Read one setting. |
| `flytie config set KEY VALUE` | Write one setting. |

Known keys: `database.path`, `pdf.template`, `pdf.output_dir`. The Anthropic
API key is **never** a config setting — it is read only from the
`ANTHROPIC_API_KEY` environment variable and is never written to disk.

```bash
flytie config set pdf.output_dir ~/fly-cards
flytie config show
```
