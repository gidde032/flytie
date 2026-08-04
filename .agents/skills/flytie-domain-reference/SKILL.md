---
name: flytie-domain-reference
description: >
  Domain-theory knowledge pack for the flytie codebase. Use when writing or
  validating material specifications, touching parsing/shop/dedupe/diff logic,
  interpreting hook sizes, adding or auditing categories, designing AI prompts
  about materials, or reasoning about whether two material names refer to the
  same thing (e.g. "CDC feather" vs "cul de canard"). Also use when
  understanding entity relationships, version semantics, the JSON export
  schema, or the AI suggestion flow.
---

# flytie Domain Reference

As of 2026-07-02, v0.2.1.

## When NOT to use this skill

| Task | Skill to use instead |
|---|---|
| Environment setup, install, quality gates | `flytie-build-and-env` |
| Config axes, env vars, data dirs | `flytie-config-and-flags` |
| CLI commands, flags, release runbook | `flytie-run-and-operate` |
| Change classification, gates | `flytie-change-control` |
| Debugging a specific symptom | `flytie-debugging-playbook` |
| Reviewer shapes, subagent orchestration | `flytie-subagent-orchestration` |

---

## 1. Sixty-second fly-tying primer

A **fly pattern** is a recipe: hook + ordered list of materials + tying instructions, producing an artificial lure that mimics insects or baitfish. A **tier** buys materials, ties patterns at home, and carries the flies to a river or lake.

Hook sizes are **inverse**: size 18 is smaller than size 8. Small numbers are large hooks (streamers for big fish); large numbers are small hooks (midges for selective trout).

Patterns target **species** (trout, salmon, bass) and **seasons** (spring hatch, fall). Before a fishing trip a tier generates a **shopping list** of materials still needed.

That is the full domain context needed to read this codebase. The rest is code mechanics.

---

## 2. Entity model

Source: `src/flytie/models.py`, `src/flytie/core/dto.py`.

### Core tables

| Entity | Table | Key constraint |
|---|---|---|
| `Pattern` | `patterns` | `name_key` unique (canonical, lowercase) |
| `PatternVersion` | `pattern_versions` | `(pattern_id, version_number)` unique |
| `Material` | `materials` | `canonical_name` unique |
| `PatternMaterial` | `pattern_materials` | join: version to material, with `quantity`, `unit`, `position`, `notes` |
| `Species` | `species` | `name` unique |
| `Tag` | `tags` | `name` unique |
| `PatternTag` | `pattern_tags` | many-to-many `Pattern` to `Tag` |
| `PatternSpecies` | `pattern_species` | many-to-many `Pattern` to `Species` |

### Name canonicalization

`normalize_name(name)` (in `models.py`): lowercase, strip, collapse interior whitespace.

```python
normalize_name("  Grizzly Hackle  ") == "grizzly hackle"
normalize_name("CDC Feather")         == "cdc feather"
```

- `Pattern.name_key` is the normalized key (lookup anchor). `Pattern.name_display` is the original casing, stored separately and updated on rename.
- Duplicate detection on `create_pattern` compares `name_key` values -- case-insensitive by construction.
- `Material.canonical_name` is also stored pre-normalized by `get_or_create_material`.

### Soft delete vs hard delete

`Pattern.is_deleted = True` is a soft delete. The pattern remains in the DB and its version history is intact. `include_deleted=False` is the default for all list/get operations. Hard delete (`hard_delete_pattern`) physically removes the row and cascades to versions and materials (FK `ondelete=CASCADE`).

### Current version

`Pattern.current_version_id` is a FK to `pattern_versions.id`. It always points to the most recently appended version. `edit_pattern` appends a new `PatternVersion` (incrementing `version_number`) and updates this pointer. The pointer is `NULL` only transiently during hard-delete setup.

### Draft notice (--from-suggestion)

When `flytie add --from-suggestion N` creates a pattern, the CLI prints a yellow "Draft:" notice listing two things: (1) materials were added with category `other`, and (2) if the suggestion had no hook size, the hook is a placeholder `'0'`. The underlying data is a normal `Pattern`/`PatternVersion`; "draft" is a display label only, not a DB field.

---

## 3. Material mini-grammar

Source: `src/flytie/core/parsing.py` -- `parse_material_spec`.

### Format

```
name[,category[,quantity[,unit[,notes]]]]
```

Passed as one string per `--material` flag. Fields are comma-split with `maxsplit=4` (so `notes` may contain commas).

| Field | Required | Default | Validation |
|---|---|---|---|
| `name` | yes | -- | non-empty after strip |
| `category` | no | `"other"` | any string; validated to `MATERIAL_CATEGORIES` later in `get_or_create_material` |
| `quantity` | no | `None` | `float()`; rejects NaN, +/-inf, negative |
| `unit` | no | `None` | any string |
| `notes` | no | `""` | any string |

### Valid examples (verified live)

```
"grizzly hackle"                           # name only; cat=other, qty=None, unit=None
"grizzly hackle,hackle"                    # + category
"grizzly hackle,hackle,2"                  # + quantity
"grizzly hackle,hackle,2,feather"          # + unit
"CDC feather,wing,4,feather,dry-fly only"  # all five fields
```

### Rejected examples (verified live)

```
""                     # MaterialParseError: empty spec
"bad,hack,notanumber"  # MaterialParseError: non-numeric quantity
"bad,hack,-1"          # MaterialParseError: negative quantity
"bad,hack,inf"         # MaterialParseError: infinite quantity
"bad,hack,nan"         # MaterialParseError: NaN quantity
```

`MaterialParseError` is a subclass of `ValueError`; the CLI catches it and exits with code 2.

Category is **not** validated inside `parse_material_spec` -- invalid categories raise `ValueError` in `get_or_create_material` at DB write time.

---

## 4. Category taxonomy

Source: `src/flytie/models.py` -- `MATERIAL_CATEGORIES` tuple (advisory; validated at the application layer).

```python
MATERIAL_CATEGORIES = (
    "thread", "hook", "hackle", "dubbing", "flash",
    "body", "tail", "wing", "head",
    "bead", "weight", "adhesive",
    "other",
)
```

13 categories as of v0.2.1. `bead`, `weight`, and `adhesive` were added after the initial 10.

**Validation behavior**: `get_or_create_material` (in `core/patterns.py`) normalizes the supplied category (lowercase strip) and raises `ValueError` if it is not in `MATERIAL_CATEGORIES`. The error message lists all valid values. Category is enforced on add, edit, and import.

**`"other"` is the catch-all** and the default when no category is supplied. v0.3.0 plans a `material categorize` command to clean up materials stuck in `other`.

Re-extract the current list:
```bash
python -c "from flytie.models import MATERIAL_CATEGORIES; print(MATERIAL_CATEGORIES)"
```

---

## 5. Hook-size semantics

Source: `src/flytie/core/patterns.py` -- `hook_size_tokens`, `_matches_hook_size`.

Hook size is stored as a free-form string in `PatternVersion.hook_size` (max 50 chars). No numeric enforcement at the DB level; the field accepts anything.

### Range/interval matching in `flytie list --hook-size`

`hook_size_tokens(s)` extracts a set of integers from a hook-size string:

```
"14"     -> {14}
"12-16"  -> {12, 13, 14, 15, 16}   # contiguous range, both endpoints inclusive
"14, 16" -> {14, 16}               # comma-separated discrete sizes
"10/12"  -> {10, 12}               # slash-separated
"streamer" -> set()                # non-numeric yields empty set
```

Matching logic (`_matches_hook_size`):
1. Parse both the stored value and the query into token sets.
2. If both sets are non-empty: match if the intersection is non-empty (a query of `"14"` matches a pattern stored as `"12-16"`).
3. If either side yields an empty set (non-numeric): fall back to case-insensitive substring match.

### Placeholder hook warning

`flytie add --from-suggestion N` uses the suggestion's `hook_size` string as-is. If the suggestion returned no hook size (empty string), the CLI falls back to `"0"` as a placeholder and prints a yellow draft warning: `"hook size is a placeholder ('0')"`. The user is expected to run `flytie edit` to correct it.

---

## 6. Quantity and unit rules

Source: `src/flytie/core/shop.py`.

### Shop aggregation

`build_shopping_list` walks each selected pattern's **current version** only. Aggregation key is `(canonical_name, normalized_unit)`.

**Unit normalization** (`_normalize_unit`): lowercase, strip, collapse whitespace. `None` and `""` both become `None`. `"Feather"`, `"feather "`, `"FEATHER"` all normalize to `"feather"`.

| Scenario | Result |
|---|---|
| Same material, same normalized unit | quantities summed |
| Same material, different units | separate line items (both appear on the shop list) |
| Quantity is `None` | `has_unitless=True` flag set on the accumulator entry |

### `?` display marker

In the rendered shop table (`render.py`):
- `quantity=None`: shows `?`
- `quantity=N` but `has_unitless=True` (same material used without a quantity in another pattern): shows `N+?`

### Merge quantity discard (dedupe path)

`merge_materials` collapses one material name into another. If both the source and target exist on the same pattern version with **mismatched units**, the source quantity is silently discarded and a warning is added to `MergeResult.warnings`. Quantities are only summed when both rows carry the same unit and both have non-`None` quantities.

---

## 7. Dedupe scoring

Source: `src/flytie/core/dedupe.py`.

### Algorithms

**`levenshtein_ratio(a, b)`**: normalized edit distance, `1 - distance / max(len(a), len(b))`. Range [0, 1]; 1.0 = identical. O(n*m) DP, O(min(n,m)) space.

**`jaccard_similarity(a, b)`**: token-level Jaccard on whitespace-split sets. `|A intersection B| / |A union B|`. Range [0, 1]; assumes names are pre-normalized (lowercase, collapsed whitespace).

**`combined_similarity(a, b)`**: `max(levenshtein_ratio, jaccard_similarity)`.

### Threshold and default

`find_duplicate_candidates` accepts `threshold: float = 0.6`. Pairs scoring at or above threshold are returned, sorted by score descending. Each `DupeCandidate` includes the pattern-use counts for both names so the user can see which name is more established.

### The semantic-gap problem

Character-level scoring cannot detect semantic equivalents. Verified live:

```
combined_similarity("cdc feather", "cul de canard") = 0.3077  # below default threshold 0.6
```

Neither levenshtein nor jaccard finds overlap between these names. v0.3.0 plans a `--ai` flag on `flytie dedupe` to use the Codex API for semantic matching. Until then, such pairs are invisible to dedupe.

---

## 8. Version and diff semantics

Source: `src/flytie/core/versions.py`.

Each `flytie edit` appends a new `PatternVersion` (immutable append-only log). `PatternVersion.version_number` increments from 1.

### `diff_versions(session, name, v1, v2)`

Returns a unified diff (`difflib.unified_diff`) between the two versions serialized as text lines. The serialization format (`_version_as_lines`):

```
hook_size: <value>
difficulty: <value or n/a>
materials:
  - <canonical_name> [qty] [unit] [category] [(notes)]
  ...     <- sorted by canonical_name (alphabetical)
instructions:
  <text lines>
notes:
  <text lines>
```

Materials are sorted by `canonical_name` before diffing (v0.2.0 redesign). Positional reordering of materials does not appear as a diff -- only actual material additions, removals, or attribute changes do.

### `restore_version(session, name, version_number)`

Copies the content of the target version into a new `PatternVersion` via `edit_pattern`. Tags and species are **not** changed (`tags=None`, `species=None` in the payload). Version history is never truncated; restore adds a new entry.

---

## 9. AI suggestion schema

Sources: `src/flytie/ai/suggest.py`, `src/flytie/core/suggestions.py`.

### Request/response models

**`SuggestionRequest`** (input to `generate_suggestions`):
- `species: str`
- `season: str`
- `water: str | None`
- `conditions: str | None`
- `count: int = 3`

**`Suggestion`** (one item from the AI):
- `name: str`
- `hook_size: str = ""`  (may be empty if the model omits it)
- `key_materials: list[str]`
- `rationale: str = ""`
- `is_existing: bool = False`  (True if name matches a library pattern)

**`SuggestionResult`**:
- `request: SuggestionRequest`
- `suggestions: list[Suggestion]`
- `raw_text: str`  (model's raw output; shown verbatim if parsing fails)

### Persistence

`save_suggestions` writes `{data_dir}/last_suggestions.json` atomically (tmp + rename). Only the most recent `flytie suggest` run is kept. File format:

```json
{
  "timestamp": "<ISO 8601>",
  "request": { "species": "...", "season": "...", "count": 3 },
  "suggestions": [ { "name": "...", "hook_size": "...", ... }, ... ]
}
```

`get_suggestion(settings, index)` takes a **1-based** index.

### Privacy boundary

`build_prompt` in `src/flytie/ai/suggest.py` is the sole place where data is assembled for the API.

**Sent to the API**: pattern names, hook sizes, material names (capped at 40 patterns x 12 materials each).

**Never sent**: instructions, notes, tags, species, full database contents, or the API key.

The API key is read only from `ANTHROPIC_API_KEY` and never logged or persisted. Model: `Codex-sonnet-4-6` (constant `DEFAULT_MODEL` in `suggest.py`). **Volatile fact** — verify the current constant in `src/flytie/ai/suggest.py` and against current Anthropic model docs before relying on it. Note: a Phase 5 reviewer once falsely flagged this ID as nonexistent (a knowledge-cutoff artifact, not a real bug — see `flytie-failure-archaeology`).

---

## 10. JSON export document

Source: `src/flytie/core/portability.py`.

### `ExportDocument` shape

```json
{
  "flytie_export_version": 1,
  "exported_at": "<ISO 8601 datetime>",
  "patterns": [
    {
      "name": "<display name>",
      "is_deleted": false,
      "tags": ["<tag>"],
      "species": ["<species>"],
      "versions": [
        {
          "version_number": 1,
          "hook_size": "14",
          "difficulty": null,
          "instructions": "",
          "notes": "",
          "created_at": "<ISO 8601>",
          "is_current": true,
          "materials": [
            {
              "canonical_name": "grizzly hackle",
              "category": "hackle",
              "quantity": 2.0,
              "unit": "feather",
              "notes": ""
            }
          ]
        }
      ]
    }
  ]
}
```

### Key rules

- **`is_current`**: exactly zero or one version per pattern may be `true`. Zero is allowed -- import falls back to the highest `version_number`. Two or more raises `PortabilityError`.
- **Duplicate names**: `parse_document` rejects a file that contains two patterns with the same normalized name.
- **File size cap**: 50 MiB (`MAX_IMPORT_FILE_BYTES`). Files larger than this are refused before parsing.
- **Format version**: `flytie_export_version` must be <= the build's `EXPORT_FORMAT_VERSION` (currently 1). A file from a newer flytie is refused.
- **Conflict modes on import**: `skip` (default), `overwrite`, `rename`. Import is fully transactional -- a failure leaves the database untouched.

---

## Provenance and maintenance

Date: 2026-07-02. Version: flytie v0.2.1.

| Claim | Source | Re-verification command |
|---|---|---|
| 13 categories, exact list | `src/flytie/models.py:MATERIAL_CATEGORIES` | `python -c "from flytie.models import MATERIAL_CATEGORIES; print(MATERIAL_CATEGORIES)"` |
| Parser field order and error cases | `src/flytie/core/parsing.py:parse_material_spec` | `python -c "from flytie.core.parsing import parse_material_spec; print(parse_material_spec('x,hackle,1,feather'))"` |
| Dedupe formula and CDC/cul de canard score | `src/flytie/core/dedupe.py:combined_similarity` | `python -c "from flytie.core.dedupe import combined_similarity; print(combined_similarity('cdc feather','cul de canard'))"` |
| Hook-size tokenizer | `src/flytie/core/patterns.py:hook_size_tokens` | `python -c "from flytie.core.patterns import hook_size_tokens; print(hook_size_tokens('12-16'))"` |
| Shop aggregation key and unit normalization | `src/flytie/core/shop.py:build_shopping_list` | Read `accum` key and `_normalize_unit` in `shop.py` |
| Export schema fields | `src/flytie/core/portability.py:ExportDocument` | `grep -n 'class Export' src/flytie/core/portability.py` |
| Privacy boundary | `src/flytie/ai/suggest.py:_grounding_block` | `grep -n 'instructions\|notes' src/flytie/ai/suggest.py` |

When updating: re-read the source files listed above, run the re-verification commands, and update the date and version in the frontmatter and the first line of this file.
