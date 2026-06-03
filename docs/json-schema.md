# Export JSON schema

`flytie export-db` writes — and `flytie import-db` reads — a documented JSON
format. This page describes that format so you can write or transform export
files by hand, or validate them in other tools.

The schema is versioned by the top-level `flytie_export_version` field. This
document describes **version 1**.

## Shape at a glance

```json
{
  "flytie_export_version": 1,
  "exported_at": "2026-05-22T18:30:00",
  "patterns": [
    {
      "name": "Zebra Midge",
      "is_deleted": false,
      "tags": ["nymph", "midge"],
      "species": ["rainbow trout"],
      "versions": [
        {
          "version_number": 1,
          "hook_size": "20",
          "difficulty": 2,
          "instructions": "Thread base, rib, bead.",
          "notes": "",
          "created_at": "2026-01-15T09:00:00",
          "is_current": false,
          "materials": [
            {"canonical_name": "black thread", "category": "thread",
             "quantity": null, "unit": null, "notes": ""}
          ]
        },
        {
          "version_number": 2,
          "hook_size": "18",
          "difficulty": 2,
          "instructions": "Thread base, rib, bead.",
          "notes": "Bumped up a hook size.",
          "created_at": "2026-03-02T11:20:00",
          "is_current": true,
          "materials": [
            {"canonical_name": "black thread", "category": "thread",
             "quantity": null, "unit": null, "notes": ""},
            {"canonical_name": "silver wire", "category": "flash",
             "quantity": 1, "unit": "strand", "notes": ""}
          ]
        }
      ]
    }
  ]
}
```

## Fields

### Document

| Field | Type | Required | Meaning |
|---|---|---|---|
| `flytie_export_version` | integer | no (default `1`) | Schema version. Import refuses a value higher than the running flytie understands. |
| `exported_at` | date-time string | no | When the file was written (informational). |
| `patterns` | array | no (default `[]`) | The exported patterns. |

### Pattern

| Field | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | **yes** | Display name. Case-insensitively unique on import. |
| `is_deleted` | boolean | no (default `false`) | Whether the pattern is soft-deleted. |
| `tags` | array of strings | no | Tag names. |
| `species` | array of strings | no | Target species names. |
| `versions` | array | no | The version history. **Must contain at least one version** for the pattern to import. |

### Version

| Field | Type | Required | Meaning |
|---|---|---|---|
| `version_number` | integer | **yes** | Sequence number within the pattern (1, 2, 3, …). |
| `hook_size` | string | **yes** | Hook size or range, e.g. `"14"` or `"12-16"`. |
| `difficulty` | integer or null | no | Tying difficulty, 1–5. |
| `instructions` | string | no (default `""`) | Tying steps. |
| `notes` | string | no (default `""`) | Free-text notes. |
| `created_at` | date-time string | **yes** | When this version was created; preserved verbatim on import. |
| `is_current` | boolean | no (default `false`) | Marks the current version. At most one version per pattern may be `true`; import rejects a file that flags two or more. If none is flagged, import falls back to the highest `version_number`. |
| `materials` | array | no | The material lines for this version. |

### Material

| Field | Type | Required | Meaning |
|---|---|---|---|
| `canonical_name` | string | **yes** | Material name. |
| `category` | string | no (default `"other"`) | One of: `thread`, `hook`, `hackle`, `dubbing`, `flash`, `body`, `tail`, `wing`, `head`, `bead`, `weight`, `adhesive`, `other`. An unknown category is rejected on import. |
| `quantity` | number or null | no | Amount, if specified. |
| `unit` | string or null | no | Unit for the quantity. |
| `notes` | string | no (default `""`) | Per-material note. |

## Validation behavior on import

`flytie import-db` validates the file before touching the database:

- Malformed JSON → rejected with a "not valid JSON" message.
- JSON that doesn't match this schema (wrong types, missing required fields) →
  rejected with a schema-mismatch message.
- A `flytie_export_version` newer than the running flytie → rejected with an
  upgrade hint.
- An unknown material category, or a pattern with no versions → rejected.
- Two or more patterns in the file with the same name (case-insensitive) →
  rejected before any database changes are attempted.
- A pattern that flags more than one version as `is_current` → rejected.
- An import file larger than 50 MiB → rejected (a hard upper bound to avoid
  exhausting memory; see `MAX_IMPORT_FILE_BYTES` in `flytie.core.portability`).

In every case the import is **transactional**: a rejected file leaves the
database completely unchanged.

## The machine-readable schema

flytie's export models are Pydantic models, so a formal JSON Schema can be
generated at any time:

```python
import json
from flytie.core.portability import ExportDocument

print(json.dumps(ExportDocument.model_json_schema(), indent=2))
```
