# Pattern file format

`flytie add` and `flytie edit` both accept a `--from-file` flag pointing at a
JSON or TOML file describing a single pattern. The file format is documented
here so you can write or generate patterns by hand, with a script, or copied
from another tyer's library.

This is **not** the same format as `flytie export-db` / `flytie import-db`.
The pattern-file format is a single pattern at the top level; the export
format wraps many patterns in a versioned document. See
[`docs/json-schema.md`](json-schema.md) for the export format.

## JSON example

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

## TOML example

The same pattern as TOML:

```toml
name = "Zebra Midge"
hook_size = "18"
difficulty = 2
instructions = "Thread base, rib with wire, seat the bead."
notes = "Tie a dozen — they get lost fast."
tags = ["nymph", "midge"]
species = ["rainbow trout"]

[[materials]]
canonical_name = "black thread"
category = "thread"

[[materials]]
canonical_name = "silver wire"
category = "flash"
quantity = 1
unit = "strand"

[[materials]]
canonical_name = "silver bead"
category = "bead"
quantity = 1
unit = "bead"
```

Both forms produce identical patterns. Pick whichever is more convenient
in your editor — TOML reads more cleanly for long material lists; JSON is
the easier target for scripts.

## Fields

### Pattern-level

| Field | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | **yes** | Display name. Case-insensitively unique across the library. |
| `hook_size` | string | **yes** | Hook size or range, e.g. `"14"` or `"12-16"`. |
| `difficulty` | integer | no | Tying difficulty, 1–5. |
| `instructions` | string | no (default `""`) | Free-form tying steps. |
| `notes` | string | no (default `""`) | Free-form notes. |
| `tags` | array of strings | no | Tag names. |
| `species` | array of strings | no | Target species names. |
| `materials` | array of material objects | no | Per-material lines (see below). |

### Material objects

| Field | Type | Required | Meaning |
|---|---|---|---|
| `canonical_name` | string | **yes** | Material name. |
| `category` | string | no (default `"other"`) | One of: `thread`, `hook`, `hackle`, `dubbing`, `flash`, `body`, `tail`, `wing`, `head`, `bead`, `weight`, `adhesive`, `other`. An unknown category is rejected. |
| `quantity` | number | no | Amount, if you want to record one. Omit (or set null) to leave unquantified — that material then renders as `?` in `flytie shop`. |
| `unit` | string | no | Unit, e.g. `feather`, `strand`, `inch`. Omit if `quantity` is also omitted. |
| `notes` | string | no (default `""`) | Per-material note. |

## CLI flags override file values

Any flag you pass alongside `--from-file` overrides the corresponding value
in the file. This is the common pattern for bulk-importing a fly and then
fixing one field without editing the file:

```bash
flytie add "Zebra Midge" --from-file zebra-midge.json --hook 20
```

The file is loaded, `hook_size` is replaced with `20`, the rest is unchanged.

The same precedence applies to `flytie edit --from-file` — file values
become the new version's baseline; passing flags layers overrides on top.

## Bulk-loading a folder

A small shell loop is enough to import a directory of files:

```bash
for f in patterns/*.json; do
  name=$(python -c "import json,sys; print(json.load(open('$f'))['name'])")
  flytie add "$name" --from-file "$f"
done
```

A reverse direction also exists for moving a whole library between machines:
see [`flytie export-db`](commands.md#flytie-export-db).

## See also

- [`flytie add` command reference](commands.md#flytie-add) — every flag and option
- [Migrating from a notebook](migrating-from-notebook.md) — workflow for transcribing an existing collection
- [Export JSON schema](json-schema.md) — the *different* (multi-pattern) format used by `flytie export-db` / `flytie import-db`
