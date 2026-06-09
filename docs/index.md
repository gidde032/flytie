# flytie documentation

**flytie** is a local-first, AI-augmented command-line tool for managing fly
tying patterns. It keeps your patterns in a structured local database so you
can tag, search, version, and undelete them; view library stats; merge
duplicate materials; generate trip-ready shopping lists; export printable
pattern cards; and ask Claude for recommendations grounded in your own library.

Everything lives on your machine in a single SQLite file — there is no account,
no server, and no network access unless you explicitly run `flytie suggest`.

## Guides

- **[Quickstart](quickstart.md)** — install flytie and add your first pattern
  in about ten minutes.
- **[Command reference](commands.md)** — every command and option, with a
  worked example for each.
- **[Shopping list cookbook](shopping-list.md)** — practical recipes for
  turning your patterns into a deduplicated materials list before a trip.
- **[AI suggestions](ai-suggestions.md)** — set up `flytie suggest`, understand
  exactly what data is sent to the Anthropic API, and write good prompts.
- **[Migrating from a notebook](migrating-from-notebook.md)** — move patterns
  from paper, text files, or memory into flytie.
- **[Pattern file format](pattern-file-format.md)** — the JSON/TOML format
  accepted by `flytie add --from-file` and `flytie edit --from-file`.
- **[Export JSON schema](json-schema.md)** — the documented format used by
  `flytie export-db` / `flytie import-db` (different from the per-pattern
  format above).

## Getting help

Every command has built-in help:

```bash
flytie --help
flytie add --help
flytie shop --help
```

## Where flytie keeps your data

flytie stores its database under your platform's standard data directory (for
example `~/.local/share/flytie/` on Linux or `~/Library/Application Support/flytie/`
on macOS). Run `flytie info` to see the resolved database path, config file
path, data directory, and pattern count in one shot. (`flytie config path`
exists too, but it specifically prints the location of the TOML config file
— use `flytie info` when you want the broader picture.)

Three environment variables override the defaults, in order of specificity:

- `FLYTIE_DB_PATH` — full path to the SQLite database file. Most surgical: the
  config directory and data directory still use their platform defaults.
- `FLYTIE_DATA_DIR` — directory where the SQLite database (and any future
  data files) live. The DB filename inside it stays `flytie.sqlite3`.
- `FLYTIE_CONFIG_DIR` — directory where `config.toml` lives. Used by the test
  suite to redirect config writes to a temp directory.

The Anthropic API key, by design, is **not** controlled by any of these — it
is read only from `ANTHROPIC_API_KEY` and is never written to disk.
