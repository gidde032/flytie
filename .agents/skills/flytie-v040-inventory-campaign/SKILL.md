---
name: flytie-v040-inventory-campaign
description: >-
  Executable, decision-gated campaign for shipping flytie v0.4.0 — the fly-box /
  inventory module and shop --format csv — including the project's FIRST real
  Alembic schema migration since the initial schema. Use when: starting v0.4.0
  work; implementing "flytie inventory"; adding the inventory_items table;
  writing or reviewing the second migration; wiring shop to subtract owned
  materials; asked "how do existing users get the new schema"; planning the
  upgrade path from a v0.1.x–v0.3.x database. Contains pre-verified facts about
  the migration machinery, five maintainer decision gates, an upgrade-path test
  battery, and fenced-off wrong paths. Do NOT use for generic migration advice
  on other projects or for v0.3.0 AI-layer work.
---

# flytie v0.4.0 campaign — inventory module + first schema migration

Authored 2026-07-04 by the outgoing principal session, from live code recon
against `main` at v0.2.1. **Status: planned, not started.** If v0.3.0 has
shipped by the time you read this, §0's recon commands re-establish every fact
this file relies on — run them before trusting anything here.

**Scope (from the roadmap):** (a) `flytie inventory add/remove/list/update` —
track owned materials in a new `inventory_items` table; (b) `flytie shop`
subtracts owned quantities by default, `--all` shows the unfiltered list;
(c) `shop --format csv` (trivial, no schema impact). (a)+(b) require the
project's **first schema migration since the initial revision** — the riskiest
surface in the project's future, which is why this campaign exists.

**The headline fact (verified 2026-07-04, and the reason Gate A exists):**
today there is NO path by which an existing user's database ever gets a second
migration. `flytie init` early-exits with "already exists" when the schema is
complete (`cli.py`, `init`: `if db.schema_is_complete(): ... raise typer.Exit(0)`),
and `_open_db` only calls `validate_compatibility()`, which passes for any
*known* revision — it never upgrades. Ship the migration without deciding
Gate A and every existing user's `flytie inventory` dies with
`no such table: inventory_items`. This is not hypothetical; it is how the
code reads right now.

---

## Sequencing recommendation

Run `shop --format csv` (§7) FIRST as a stand-alone warm-up micro-phase with
its own mini-review. Do NOT bundle it with the inventory phases: bundling
requires non-overlapping surfaces (project rule), and both touch the shop
render path. Then run §0→§6 as the inventory phase-set. Each numbered section
below is sized to be one session-slice; report at each boundary and let the
maintainer pick the next slice.

---

## §0 — Preconditions and recon (gate: facts re-established, baseline green)

1. Fresh session. Read `handoff.md` + `AGENTS.md` if present. Confirm whether
   v0.3.0 shipped (`git tag`; `grep version src/flytie/__init__.py`).
2. Baseline gates green before touching anything:
   `ruff format --check src tests && ruff check src tests && mypy src`,
   full `pytest --cov=src/flytie` (85% floor), `pytest -m smoke` (exactly 5),
   cold-start best-of-5 < 600 ms. Record the numbers — they are your
   before/after evidence.
3. Re-verify the campaign's load-bearing facts (expected results as of
   2026-07-04 in parentheses):

```bash
# (a) init early-exits on a complete DB — no upgrade path for existing users
grep -n "schema_is_complete" src/flytie/cli.py            # (early-exit inside init)
# (b) merge_materials DELETES the source Material row
grep -n "session.delete(from_mat)" src/flytie/core/patterns.py   # (present)
# (c) exactly one migration; head is the initial revision
ls src/flytie/migrations/versions/                        # (one *_initial_schema.py, rev 5af955bd607b)
# (d) repair path builds ORM metadata then stamps head
grep -n "_build_schema_directly" src/flytie/db.py         # (create_all + stamp_alembic_head)
# (e) batch mode already on for SQLite ALTER safety
grep -n "render_as_batch" src/flytie/migrations/env.py    # (True, both modes)
# (f) unit normalization currently lives in shop
grep -n "_normalize_unit" src/flytie/core/shop.py         # (strip/lower/collapse)
# (g) export parser tolerance of unknown keys (Pydantic default: ignore)
grep -n "model_config\|ConfigDict\|extra" src/flytie/core/portability.py  # (no strict config found)
# (h) does ExportDocument carry a format-version field? (informs Gate E)
grep -n "class ExportDocument" -A 12 src/flytie/core/portability.py
```

If any expected result no longer holds, STOP and reconcile this file against
reality before proceeding (update the campaign, don't force it).

---

## GATE A — upgrade delivery strategy — **DECIDED 2026-07-04: A1 (auto-upgrade + backup)**

Ratified by the maintainer in the authoring session. Implement A1 exactly as
specified below (guarded/idempotent, timestamped backup, .db-only copy). The
option table is kept as the decision record; do NOT re-open unless A1 fails
in practice — then return to the maintainer with evidence.

How does a v0.1.x–v0.3.x database acquire the new table? Options, ranked:

| Option | Mechanism | Pros | Cons |
|---|---|---|---|
| **A1 (recommended)** | `_open_db` auto-upgrades when DB revision is known-but-behind-head; makes a timestamped backup copy of the `.db` file first (checkpoint WAL, then copy) and prints one line: "Upgraded database schema to <rev>; backup at <path>" | Zero user action; local-first single-user tool; principle of least surprise; backup makes it reversible | Schema mutates on what the user thought was a read command; backup adds disk writes on first run |
| A2 | Teach `init` to upgrade: replace the early-exit with "schema complete but behind head → run `upgrade_to_head()`"; every OTHER command refuses when behind head with "run `flytie init` to upgrade" | Explicit, auditable moment; `init` docstring already says "safe to re-run" | Every existing user hits one refusal before things work; "init" now means "upgrade" too |
| A3 | New `flytie migrate` command; other commands refuse when behind head and name it | Clearest semantics; no surprise mutation | New permanent command surface for an event that happens once per release; most friction |

Whichever is chosen: the refusal/upgrade message must be tested (paired test),
`flytie info` must keep working against a behind-head DB (it already bypasses
compatibility checks by design — preserve that), and the CHANGELOG gets a
first-ever **Upgrade notes** section. Do not proceed past this gate without
the maintainer's explicit pick. A1 blast-radius notes (reviewer finding):
`_open_db` serves ~25 commands, so the FIRST run of *any* command (including
read-only `list`/`stats`) triggers the upgrade — the upgrade must be
idempotent and guarded (re-check the revision inside the same connection
before acting), and the backup filename must be timestamped
(`<db>.pre-<newrev>-<YYYYMMDDHHMMSS>.bak`), never a fixed name a second
racing process would overwrite. Backup mechanics: run
`PRAGMA wal_checkpoint(TRUNCATE)` first, then copy ONLY the `.db` file —
post-truncate the `-wal`/`-shm` sidecars are empty and safely omitted (say
this in the code comment so nobody "fixes" it).

---

## §1 — Schema + the migration itself (gate: two-revision world, all invariants hold)

**Table design** (`inventory_items`):

```
id            Integer PK
material_id   FK -> materials.id, ondelete=RESTRICT, nullable=False, index
quantity      Float, nullable=True          # None = "have some, amount unknown" (mirrors pattern_materials '?')
unit          String(50), nullable=True     # store NORMALIZED (strip/lower/collapse) — see §3
notes         Text, default "", nullable=False
created_at / updated_at   like Pattern's, WITH server_default (lesson: the Phase 1
                          is_deleted missing-server-default review finding)
UniqueConstraint(material_id, unit)   # ← Gate B
```

**GATE B — uniqueness key — DECIDED 2026-07-04: `UNIQUE(material_id, unit)`.** Ratified by the maintainer; rationale as recommended:
`UNIQUE(material_id, unit)` — one row per (material, unit), which is exactly
the shop accumulator's `(canonical_name, normalized_unit)` key, so §5's
subtraction is a clean key-join. Alternative: `UNIQUE(material_id)` (one row
per material, single unit) — simpler but forces unit-conversion questions the
project has always refused to answer. **SQLite trap either way:** NULL units
are all distinct under UNIQUE — the constraint will NOT stop duplicate
(material, NULL) rows. The repo layer must therefore do get-or-create keyed on
`(material_id, normalized_unit-or-None)`; add a paired test for the
double-NULL case specifically.

**Migration mechanics:**
- Hand-write the revision (copy the style of the initial migration; template
  is `src/flytie/migrations/script.py.mako`). `down_revision = "5af955bd607b"`.
  Pure `op.create_table(...)` + index — no ALTER involved; batch mode
  (already on in env.py) matters only for future ALTER-shaped migrations.
- Write a real `downgrade()` (`op.drop_table`), but document it as
  best-effort/unsupported — the project has never certified downgrades.
- Add the ORM model to `models.py` **in the same commit**. Invariant: ORM
  metadata must equal head at all times, because `_build_schema_directly()`
  (the stamped-but-empty repair path) does `create_all` + stamp-head — if the
  model lags the migration, repaired DBs silently diverge from migrated ones.
- `known_revisions()` walks the scripts directory, so the new revision is
  recognized automatically; `validate_compatibility()` needs no change.
- Coverage: `[tool.coverage.run] omit` already wildcards
  `src/flytie/migrations/versions/*.py` — no gate change needed (and none is
  permitted without sign-off).

**Expected observations at this gate:** `flytie init` on a fresh env creates
the table; `flytie info` shows the NEW revision; a ScriptDirectory walk
returns exactly 2 revisions. If `init` creates the table but `info` still
shows `5af955bd607b` → you created the file somewhere Alembic doesn't scan;
check `MIGRATIONS_DIR` resolution before anything else.

**Wheel check:** build once (`python -m build`) and assert BOTH migration
files appear in the wheel (`unzip -l dist/*.whl | grep versions`). The initial
migration ships today without an `__init__.py` in `versions/` (hatchling
packages the directory contents); the new file rides the same mechanism —
verify, don't assume.

---

## §2 — Upgrade-path test battery (gate: battery green; this is a NEW test class)

The suite has never tested a real upgrade because there was never a second
revision. **Sequencing: §1's migration must exist BEFORE the money test means
anything** — until the new revision lands, `5af955bd607b` IS head and
"build-at-old, upgrade-to-head" is a green no-op that proves nothing. Build
the helper alongside §1, and make it refuse degeneracy:

```python
def build_db_at(settings, revision: str) -> Database:
    """Create a DB migrated only up to `revision` (not head)."""
    # same Config dance as Database.upgrade_to_head, but:
    command.upgrade(cfg, revision)   # e.g. "5af955bd607b"
    # Guard against the degenerate case: the helper must FAIL if `revision`
    # is already head, so the money test can never silently become a no-op.
    assert revision not in ScriptDirectory.from_config(cfg).get_heads()
```

Battery (each test's docstring names this campaign):
1. Fresh init → head: `inventory_items` exists, `alembic_version` = new head.
2. **The money test:** build at `5af955bd607b`, populate representative data
   through the ORM (patterns incl. one soft-deleted, multi-version history,
   materials with case-variant units), then `upgrade_to_head()` → row counts
   identical, version history intact, inventory table present and empty.
3. Stamped-but-empty repair in a two-revision world: stamp head on an empty
   DB → `create_schema()` → ALL tables incl. inventory exist (regression of
   the Phase 6 CRITICAL against the new head).
4. Behind-head behavior per Gate A's decision (auto-upgrade happens / refusal
   message appears) — paired test for whichever was chosen, plus: `flytie
   info` still works against a behind-head DB.
5. Future-revision refusal still works: stamp a fake unknown revision → exit
   code 4 (extends the existing v0.1.1 `validate_compatibility` tests).
6. Gate B double-NULL-unit dedupe (see §1).

Where they live: a new `tests/test_migrations.py` (this is core feature
coverage, not review-fix regression — the `test_v0_X_Y_fixes.py` convention
does not apply here).

---

## §3 — Core module (gate: repo functions + unit extraction, tests green)

- **First, extract unit normalization**: move `_normalize_unit` from
  `core/shop.py` to a tiny `core/units.py` (public `normalize_unit`), import
  it back into shop. Do this BEFORE writing inventory code — inventory
  importing from shop (or vice versa) is the circular-import wrong path.
  Keep a re-export or alias in shop for one release if anything external
  touches it (grep first).
- `core/inventory.py`: `add_or_update`, `remove`, `list_items`, get-or-create
  keyed on `(material_id, normalized_unit)`; material lookup reuses the public
  `get_or_create_material` (public since v0.2.0). DTOs in `core/dto.py`;
  renderers consume DTOs only (architecture boundary — reviewers stopped
  flagging session leaks the day this became law; don't give them a reason
  to start again).
- **Merge/dedupe re-pointing (cross-feature, MANDATORY):** `merge_materials`
  ends with `session.delete(from_mat)` — with inventory's RESTRICT FK, any
  merge of a material that has inventory rows raises IntegrityError. Extend
  `merge_materials`: re-point inventory rows to the target material; where
  target already has a row with the same normalized unit, sum quantities;
  where units differ, keep the target's row and emit the same
  "discarded quantity" warning shape the function already uses for pattern
  materials. `material dedupe` inherits this via merge. Paired tests: merge
  with inventory on source; merge with inventory on both sides, same unit;
  differing units (warning text asserted with whitespace-normalization).
  **Trap from history:** adding warnings to this path broke an exact-count
  assertion once before (v0.2.1). The asserts that WILL break are in
  `tests/test_v0_2_phase1.py` (~lines 502 and 542, `== 1` / `== 2`) — update
  them in the same commit; re-grep `len(result.warnings)` for any added since.

---

## §4 — CLI command group (gate: commands live, help text passes the "cold user" bar)

`flytie inventory add|remove|list|update` mirroring the `material`/`tag`
group structure in `cli.py`. Conventions that are law here: every option gets
a real `help=` string (the v0.1.1 friction-log finding — a bare `--unit TEXT`
is a regression); destructive `remove` honors `--yes` and refuses non-TTY
without it (exit 2, matching `delete`); errors route through `_fail`;
NO new top-level imports in `cli.py` (cold-start gate; anything heavy stays
lazy). Explicit small decision (surface it, don't guess): should `flytie
stats` and `flytie info` report an inventory count? Recommend yes for both
(one row each); either way, record the choice so an auditor doesn't flag the
omission as drift. Docs: `docs/commands.md` section + a short
`docs/inventory.md` topical guide, each with a docs-content smoke test
pinning the promises.

---

## §5 — Shop subtraction (GATE D: semantics table sign-off BEFORE implementing)

Subtraction joins on the same key the accumulator already uses:
`(canonical_name, normalized_unit)`. The `?` (quantity=None) semantics create
judgment calls — **DECIDED 2026-07-04: the maintainer ratified THIS table
as written** (including hiding fully-owned rows unless `--all`). Implement
against it directly; amendments require going back to the maintainer:

| needed | owned | proposed result |
|---|---|---|
| N | M, same unit | buy max(N−M, 0); row hidden when 0 unless `--all` |
| N | M, different unit | buy N; annotate "owned M <other-unit> not comparable" |
| N | None-quantity row | buy N; annotate "some on hand" |
| ? (None) | anything | buy stays `?` and the row is NEVER hidden (unknown need can't be satisfied); the owned column still shows the owned value so the user sees what they have |
| N | no inventory row | buy N (today's behavior) |

`--all` disables subtraction entirely (shows the pre-v0.4.0 list). Output: add
an "owned" column only when inventory is non-empty (keep the empty-inventory
rendering byte-identical to today — cheapest way to keep dozens of existing
shop assertions green; verify with the full suite before deciding otherwise).
Formats: text/markdown/json/csv all reflect subtraction; json/csv gain
`owned`/`to_buy` fields; docs + docs-content smoke tests updated. COLUMNS=80
stress-run before push (wrap fragility has bitten shop-adjacent tests twice).

---

## §6 — Portability (GATE E) + reviews + release

**GATE E — exports — DECIDED 2026-07-04: merge-by-(material, normalized-unit); incoming wins on quantity conflict with a warning.** Ratified by the maintainer. Extend `ExportDocument` with an
optional `inventory` array (absent key = old export = imports cleanly).
Verified 2026-07-04: the parser has no strict/extra config, so **an OLD
flytie importing a NEW export silently ignores the inventory key** — no
error, no data. Options: (E1, recommended) accept + document loudly in
CHANGELOG upgrade notes and `docs/json-schema.md`; (E2) add a format-version
field now — note it cannot fix THIS asymmetry (old versions can't be changed
retroactively), it only helps future ones; consider it for the catalogue.
`import-db` on the new version must handle both shapes. **`--on-conflict`
does NOT map onto inventory** (reviewer finding): the existing skip/overwrite/
rename modes are per-PATTERN (matched on `name_key`, portability.py ~399;
`overwrite` hard-deletes the pattern) — inventory rows are global per
(material, unit), so they need their own documented merge policy, decided at
this gate: (recommended) merge-by-(material, normalized-unit) — incoming row
wins on quantity conflict, with a warning; alternative: `--replace-inventory`
flag for wholesale replacement. Do not pretend the pattern modes cover this.
Round-trip test: export→wipe→import preserves inventory.

**Review pass (per change-control, non-negotiable):** three contextless
Sonnet reviewers — skeptic (standing) + **data-integrity/migration specialist**
(brief them onto §1–§3: FK behavior under merge, the repair path, upgrade
battery adequacy) + UX/CLI specialist (§4–§5: help text, subtraction
semantics legibility, `--all` discoverability). Briefs from
`subagent-brief-templates.md` if present; otherwise the embedded templates in
`flytie-subagent-orchestration`. Out-of-scope list for reviewers: downgrade
certification (documented unsupported), unit conversion (permanently out),
photo attachments (v0.5+).

**Hardening + release:** triple-lens audit (spec-drift — remember to backport
the inventory table into spec §5 and mark §9's inventory question resolved;
contributor-friction; CI-as-contract). CHANGELOG `[0.4.0]` with the first
**Upgrade notes** subsection (what happens to an existing DB on first run,
where the backup lands if Gate A chose A1, the old-flytie-import caveat from
Gate E). Then the standard release runbook (`flytie-run-and-operate`) — all
gates green first; the migration makes this the release where the
tag-vs-version assertion and the full-matrix test run earn their keep.

**Success is measured, not judged:** §2 battery green; full suite green at
COLUMNS=80; coverage ≥ 85 with NO omit-list change; cold-start best-of-5
< 600 ms (alembic must stay lazy-imported — the migration work makes it
tempting to import it at module level in db.py; don't); the §0 baseline
numbers compared and reported; a manually-exercised upgrade of a scratch
v0.2.1-era DB (built via `build_db_at`) with data intact.

---

## §7 — shop --format csv (independent warm-up micro-phase)

One new renderer + one branch in the `shop` command. Facts from a validated
dry-run implementation (2026-07-04, Sonnet, full 3-reviewer pass — the code
itself was ephemeral; the findings transfer): columns
`category,material,quantity,unit,used_in`; RFC 4180 via the stdlib `csv`
module writing to `io.StringIO`; print with `markup=False, highlight=False`
(Rich mangles `[bracketed]` names otherwise) and exactly one trailing
newline; **fix the pre-existing bug while here** — "Nothing to buy" prints to
STDOUT today and corrupts piped `csv`/`json` output; route it to the error
console for all formats, with paired regression tests. `used_in` joins
pattern names with `"; "` — document the collision limitation, don't invent
an escaping scheme (taste call already made once). Update `docs/commands.md`
+ `docs/shopping-list.md` + smoke tests. Mini-review: skeptic + UX/CLI is
sufficient for this size; still every-finding-paired-test.

---

## Fenced wrong paths (each has a reason; don't relitigate silently)

- **Editing the released initial migration** — published revisions are
  immutable; users' DBs reference them by ID. New revision only.
- **`create_all` without stamping, or stamping without verifying tables** —
  re-reads the Phase 6 CRITICAL into existence.
- **Columns on `materials` instead of a new table** — couples inventory
  lifecycle to the canonical registry, breaks merge semantics, and makes the
  (material, unit) key impossible.
- **`alembic revision --autogenerate` against your personal DB** — generates
  drift noise from whatever state that DB is in; hand-write from the template.
- **Assuming `init` upgrades existing DBs** — verified false (§0a). Gate A
  exists because of this; skipping it ships a broken release.
- **Skipping the merge→inventory re-point** — first `material merge` on an
  inventoried material IntegrityErrors in front of the user.
- **Any gate-weakening to get the battery green** — coverage floor, omit
  list, smoke count, cold-start budget: maintainer sign-off or it doesn't
  happen.

## When NOT to use this skill

Generic flytie debugging → `flytie-debugging-playbook`. How reviews run →
`flytie-subagent-orchestration`. Release mechanics → `flytie-run-and-operate`.
Schema/invariant background → `flytie-architecture-contract` (read its
migration invariants before §1). v0.3.0 AI-layer work → the roadmap and
`flytie-change-control`, not this file.

## Provenance and maintenance

Authored 2026-07-04 from direct code recon at v0.2.1 `main` (db.py, cli.py
init/_open_db, models.py, migrations/env.py, core/patterns.py merge_materials,
core/shop.py, core/portability.py) plus the roadmap's v0.4.0 entry and a
validated csv dry-run. All load-bearing facts carry re-verification commands
in §0 — run them at campaign start, especially if v0.3.0 landed in between.
Gates A/B/D/E were ratified by the maintainer on 2026-07-04 in the authoring
session (A1 auto-upgrade+backup; composite uniqueness key; the §5 semantics
table as written; import merge-by-key). Only the info/stats-count question
(§4) and reviewer-slate details remain as in-flight judgment calls. If
execution reveals evidence against a ratified decision, stop and return to
the maintainer — don't silently re-decide.
