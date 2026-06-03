# Migrating from a notebook

Most tyers already have a pattern collection — scrawled in a notebook, kept in
scattered text files, or simply held in memory. This guide moves it into
flytie so it becomes searchable, versioned, and trip-ready.

## You don't have to do it all at once

flytie is useful from the first pattern. Transcribe the flies you tie most
often first; add the rest as you reach for them. Every pattern you add is
immediately searchable and starts accumulating version history.

## Approach 1 — type them in

For a handful of patterns, `flytie add` straight from the command line is
fastest. Materials are written `name,category,quantity,unit`:

```bash
flytie add "Zebra Midge" --hook 18 -t nymph -t midge -s "rainbow trout" \
  -m "black thread,thread" \
  -m "silver wire,flash,1,strand" \
  -m "silver bead,bead,1,bead" \
  --instructions "Thread base, rib with wire, seat the bead."
```

## Approach 2 — transcribe into files, then load them

For a larger backlog, write one JSON (or TOML) file per pattern and load it
with `--from-file`. This is easier to proofread than a long command line, and
the files double as a plain-text backup. The full schema lives at
[Pattern file format](pattern-file-format.md); the example below is enough
to get started.

A pattern file looks like this (`zebra-midge.json`):

```json
{
  "name": "Zebra Midge",
  "hook_size": "18",
  "difficulty": 2,
  "instructions": "Thread base, rib with wire, seat the bead.",
  "notes": "Tie a dozen — they get lost fast.",
  "tags": ["nymph", "midge"],
  "species": ["rainbow trout"],
  "materials": [
    {"canonical_name": "black thread", "category": "thread"},
    {"canonical_name": "silver wire", "category": "flash", "quantity": 1, "unit": "strand"},
    {"canonical_name": "silver bead", "category": "bead", "quantity": 1, "unit": "bead"}
  ]
}
```

Only `name` and `hook_size` are required; everything else is optional. Load it:

```bash
flytie add "Zebra Midge" --from-file zebra-midge.json
```

Any CLI flag you also pass overrides the file — handy for fixing one field
without editing the file.

### Loading a whole folder

Put one file per pattern in a directory and loop:

```bash
for f in patterns/*.json; do
  name=$(python -c "import json,sys; print(json.load(open('$f'))['name'])")
  flytie add "$name" --from-file "$f"
done
```

## Approach 3 — import a shared collection

If another tyer sends you a flytie export (or you're moving between your own
machines), don't transcribe anything — import it directly:

```bash
flytie import-db shared-patterns.json
```

The import is transactional and lets you choose what happens to name
collisions (`--on-conflict skip|overwrite|rename`). See the
[command reference](commands.md#flytie-import-db) and the
[JSON schema](json-schema.md).

## Tips for a clean library

- **Keep material names consistent.** `hare's ear dubbing` and
  `hares ear dubbing` are different strings, flytie won't merge in a
  shopping list.
- **Tag as you go.** Tags (`dry`, `nymph`, `streamer`, `winter`, specific
  rivers, etc.) make `flytie shop --tag` and `flytie list --tag` more effective
  later.
- **Improve flies as you go.** Every `flytie edit` keeps the old version, so
  you can refine a transcription over time without losing
  the original.
- **Back up once you're done.** `flytie export-db --out my-patterns.json`
  gives you a portable snapshot of the whole library.
