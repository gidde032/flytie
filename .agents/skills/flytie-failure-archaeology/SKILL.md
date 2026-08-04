---
name: flytie-failure-archaeology
description: >-
  The settled-history chronicle for flytie — every major investigation, dead
  end, rejected fix, false alarm, and accepted spec deviation, recorded as
  symptom → root cause → evidence → status. Use when about to re-investigate a
  bug, before proposing a fix a reviewer suggests (it may already have been
  rejected), when a reviewer re-raises an old finding, when tempted to "clean
  up" something odd-looking (e.g. the *_old.py files, the (imported) rename
  suffix, the 600 ms cold-start budget), or when wondering why a design is the
  way it is. Read this before spending tokens re-fighting a battle that is
  already settled and pinned by a regression test.
---

# flytie failure archaeology

This is the **chronicle**: what broke, what was tried, what was rejected, and
what is now settled. It exists so nobody re-fights a battle that already has a
verdict and a regression test.

**This skill vs. its neighbor.** `flytie-debugging-playbook` triages failures
that will *recur* (symptom → triage → fix, forward-looking). **This** skill
records what is *settled* (symptom → root cause → evidence → status,
backward-looking). If you have a live symptom and want a fix procedure, go to
the playbook. If you want to know whether a thing was already investigated,
whether a fix was already rejected, or why a weird-looking design is
intentional, you are in the right place.

Facts are date-stamped where volatile. As of **2026-07-02, flytie is at
v0.2.1** (tagged; on PyPI). v0.3.0 is scoped but not started.

---

## 1. How to use this file — check here BEFORE you...

| You are about to... | Check first for... | Why |
|---|---|---|
| Re-investigate a bug | a chronicle entry with status **FIXED+pinned** | It may already be fixed with a regression test naming it. |
| Propose a fix a reviewer suggested | a **REJECTED proposal** entry | The maintainer may have already declined it as a taste call. |
| "Clean up" something odd-looking | the *_old.py note, the `(imported)` suffix, the 600 ms budget | Several odd-looking things are deliberate or un-removable. |
| Re-raise a deviation from the spec | the **Accepted spec deviations** table (§4) | Deviations are backported into the spec on purpose. |
| Action a reviewer's factual claim about the outside world | the **False-alarm registry** (§3) | Reviewers have been confidently wrong about model IDs and file presence. |

The single rule this file enforces: **a reviewer's findings are an input to
judgement, not a verdict — and that applies to its factual claims as much as
its style opinions.** Every entry below with status REJECTED or FALSE ALARM is
a case where executing the finding blindly would have made the project worse.

---

## 2. The chronicle

Organized by phase/release. Each entry: **Symptom → Root cause → Evidence →
Status**. Status values:

- **FIXED+pinned** — fixed, with a named regression test that fails if it
  regresses.
- **ACCEPTED deviation** — a knowing departure from the spec; the spec was
  backported to match.
- **REJECTED proposal** — a fix was proposed (by a reviewer or in discussion)
  and deliberately declined. Do not re-propose without new information.
- **FALSE ALARM** — a finding that was wrong; named here so a future audit
  doesn't re-raise it.

### Phase 1 — Foundation (`init`, schema, Alembic)

**`flytie init` used `create_all`, never stamped Alembic.**
Root cause: schema was built with `Base.metadata.create_all` and the Alembic
version table was left empty. Any later migration would try to re-run the
initial migration and fail. Evidence: **both reviewers converged** on it
independently ("Both reviewers converged on the same high-severity issues") —
the project's first and strongest convergence signal. Status: **FIXED+pinned**.
`create_schema` in `src/flytie/db.py` runs Alembic and stamps head. (See also
the Phase 6 stamped-but-empty follow-up, which is a *different* failure mode of
the same subsystem.)

**Alembic migrations missing from the wheel.**
Root cause: the bundled migrations directory wasn't force-included in the build.
A `pip install`ed copy had no migrations to run. Status: **FIXED+pinned**.
Migrations live inside the package at `src/flytie/migrations/`; initial
revision `5af955bd607b`.

**Timezone-aware datetime compared unequal after round-trip.**
Symptom: `TypeError: can't compare offset-naive and offset-aware datetimes`.
Root cause: SQLite `DateTime(timezone=True)` does not persist tz info; a
tz-aware Python datetime written then read back no longer matched. Status:
**FIXED+pinned** (self-caught in the test loop). Fix: store naive UTC
consistently.

**Stale `current_version` relationship after edit.**
Root cause: `edit_pattern` set the new version's foreign-key id but didn't append
to the in-memory relationship collection, leaving it stale. Status:
**FIXED+pinned**. Fix: append the new version to the relationship.

**`search_patterns` didn't escape SQL `LIKE` wildcards.**
Root cause: user input containing `%` or `_` was interpreted as wildcards.
Status: **FIXED+pinned**.

**Malformed-TOML config crashed the CLI; config writes were non-atomic.**
Status: **FIXED+pinned**. Config writes go through tmp-file-then-rename in
`src/flytie/config.py`. `Pattern.is_deleted` also gained a `server_default` in
this pass.

### Phase 2 — Core CLI commands

**`-h` shadowed `--help`.**
Root cause: `-h` was bound as the short alias for `--hook`, so it never reached
Typer's conventional `--help`. Caught by the UX reviewer. Status:
**FIXED+pinned**.

**`add`/`edit --from-file` silently ignored other CLI flags — in two places.**
Root cause: a flawed pattern was **copied into both commands** — the file
payload won and any CLI flags passed alongside it were dropped silently. The
correctness reviewer caught `edit`; both reviewers caught that `add` had the
same flaw. Status: **FIXED+pinned**. Fix: CLI flags now layer as explicit
overrides on top of the file payload, consistently in both commands.

**Silent display-name renames.**
Root cause: editing a pattern could change its display name as an accidental
side effect. Status: **FIXED+pinned**. Fix: a dedicated `--rename-to` flag makes
renames explicit; a bare edit no longer renames. (Backported into the spec.)

Also fixed this phase: conflicting `--tag x --clear-tags`; uncaught Pydantic
`ValidationError`; missing `~` expansion / size cap / decode-error wrapping in
`load_pattern_file`; non-TTY `delete` without `--yes`.

### Phase 3 — Versioning, shopping list, and the FUSE incident

**Missing `shop --format json`.**
Root cause: the spec declared a JSON exporter for shopping lists; it was never
implemented. Status: **FIXED+pinned**. (A spec promise unimplemented — the class
of bug a spec-drift audit catches that per-phase code review misses.)

**Unit-normalization bug in shopping-list dedup.**
Symptom: `"Feather"` and `"feather"` counted as different materials. Root cause:
dedup didn't normalize units/names on both sides. Status: **FIXED+pinned**.

**NaN/inf/negative quantities poisoned aggregation.**
Root cause: `parse_material_spec` accepted `NaN`, `inf`, and negative quantities
that then corrupted shopping-list sums. Status: **FIXED+pinned**. Fix:
`parse_material_spec` rejects them.

Also fixed: unescaped Markdown specials in rendered output; a bare `assert` in
`restore_version` (now raises `RuntimeError`); trailing-whitespace `difficulty:`
when None.

**THE FUSE INCIDENT — read this before touching `*_old.py`.**
Symptom: reads/edits of recently-edited files returned
`OSError: [Errno 35] Resource deadlock avoided` (POSIX `EDEADLK`). Root cause:
the workspace filesystem is a FUSE mount bridging an agent sandbox to disk;
bursts of rapid edits to the same file trip a cache-coherency race, and the
resulting `EDEADLK` is **per-inode and persistent** — only a fresh inode at the
same path clears it. It cost **~20,000 tokens** of in-place recovery before a
workaround was found.

- **The cheap recovery (learned later, in Phase 6):** asking the user to re-open
  the project folder brings the mount back with fresh inodes and clears the
  deadlock project-wide, at the cost of one user action plus `pip install -e .` to
  re-point the editable install — far cheaper than the in-place recovery. The full
  step-by-step recovery ladder lives in `flytie-debugging-playbook` (A1, the owner);
  this entry is the historical incident record.
- **The `*_old.py` fossils.** The in-place recovery (`mv` the poisoned file
  aside, `Write` a fresh copy at the original path) left inert poisoned inodes
  behind. Eight `*_old.py` paths are tracked in git (`git ls-files | grep _old`),
  so fresh clones get all eight, inert and excluded from pytest (`addopts`), ruff
  (`[tool.ruff].exclude`), and coverage. As of 2026-07-02 all eight are physically
  present in the working copy (verify: `find src tests -name "*_old.py"` — six
  under `src/flytie/`, two under `tests/`); their inodes are FUSE-poisoned in
  Cowork sandbox sessions, where unlink fails. **Do not delete or "fix" any of them from a sandboxed session without
  maintainer sign-off** — FUSE refuses unlinks on poisoned inodes and you will
  burn tokens failing; the tracked ones can be removed with a normal `git rm` from
  an unpoisoned checkout. Status: **ACCEPTED** (leftover artifact). Their inertness
  is what matters day to day — don't spend a session fighting the mount to remove
  them in place.

### Phase 4 — PDF export, reviews blocked by quota, user-as-fourth-reviewer

**Reviewer pass blocked twice by API quota.**
Symptom: reviewer subagents returned "You're out of extra usage" before
finishing. Status: process incident, not a code bug; the Phase 4 pass was
completed later. No fix in code.

**WeasyPrint importable but `libpango` missing → uncaught `OSError`.**
Symptom: on the user's macOS machine, `import weasyprint` succeeded but calling
into it raised `OSError` for the missing native library; the test gating only
caught `ImportError`. Root cause: native-lib absence throws `OSError`, not
`ImportError`. **Caught by the user running real commands on his own machine** —
"The user's hands-on local test on macOS effectively substituted for one of the
planned reviewers — specifically catching exactly what the packaging specialist
persona was supposed to flag." Status: **FIXED+pinned** with a three-layer fix:
(1) split `_require_jinja2` / `_require_weasyprint` so the HTML fallback needs
only Jinja2; (2) module-level `pytest.skip` on systems without Pango;
(3) README install instructions per OS. (This is the origin of the "user testing
is the fourth reviewer" principle — see also Phase 6.)

### Spec-drift audit (between Phase 4 and Phase 5)

A contextless audit compared implementation to spec section-by-section and
produced **15 deviations: 6 Accept, 4 Document, 5 Fix.** All five Fix items
closed with 20 paired tests in `tests/test_audit_fixes.py`: `flytie config`
command group; `list --hook-size` interval filter; `Material.category`
validation; batch `export --tag/--species`; and a spec backport pass. Status:
**FIXED+pinned** (the 5 fixes) and **ACCEPTED deviation** (the 6+4; see §4).

### Phase 5 — AI suggestions

**Streaming swallowed by a static spinner.**
Symptom: the "streaming" suggest output was actually a frozen spinner. Root
cause: the orchestrator exposed an `on_chunk` callback but the CLI never wired
it up. The **skeptical-senior reviewer** called this the one thing he couldn't
sign off on. Status: **FIXED+pinned**. `test_cli_suggest_wires_on_chunk_callback`
in `tests/test_review_fixes_phase5.py` asserts the CLI passes a real callback.

**`_extract_json_array` truncated on `]` inside string values.**
Root cause: the array extractor treated any `]` as the array terminator,
including one inside a rationale string. Status: **FIXED+pinned**. Fix: a
string-aware scanner (`in_string` tracking with escape handling) in
`src/flytie/ai/suggest.py`; pinned by `test_parse_handles_brackets_inside_string_values`
and `test_parse_handles_escaped_quote_inside_string`.

**Silent truncation at `max_tokens`.**
Root cause: `max_tokens` was 1500; long responses were cut off with no signal.
Status: **FIXED+pinned**. Raised to 4096 with explicit `stop_reason == "max_tokens"`
detection; pinned by `test_streamer_detects_max_tokens_truncation`.

**FALSE ALARM: reviewer claimed `Codex-sonnet-4-6` was a non-existent model ID.**
The LLM-integration reviewer confidently flagged the model constant as invalid
and recommended changing it. It was a **knowledge-cutoff artifact** — the
reviewer's training data predated the Sonnet 4.6 release, so it "knew" the ID
couldn't exist. Status: **REJECTED**. This is the canonical lesson: *anything a
reviewer asserts about the outside world — current API versions, library
behavior, what's deprecated — must be checked against current reality before
being actioned.* See §3.

Also fixed this phase (11 fixes total): richer exception translation
(401/429/529/connection errors → friendly messages), clean `KeyboardInterrupt`
exit, `--n` enforced post-parse, a data-disclosure notice, null-field coercion,
dedup by normalized name, and per-pattern material caps in the grounding block.
Privacy was verified by review: grounding contains only names/hooks/material
names; the API key is never persisted or logged.

### Phase 6 — Polish, portability, publish

**CRITICAL: `flytie init` could leave a stamped-but-empty database.**
Symptom: after an interrupted `init`, `alembic_version` said "head" but no
tables existed; the next `init` saw the stamp, ran nothing, returned cleanly,
and every later command died on `no such table: patterns`. Root cause: Alembic
stamps each migration *before* its DDL runs, and SQLite auto-commits each DDL
statement — so an interruption between stamp and DDL leaves a lying version
table. The **skeptic flagged it in theory; the maintainer then independently
reproduced it on his laptop** following his own quickstart (user-as-reviewer
converging with a sandboxed reviewer's theoretical finding). Status:
**FIXED+pinned**. `create_schema` now runs `inspect(engine).has_table("patterns")`
after the Alembic upgrade returns and rebuilds the schema directly if tables are
missing; `init` calls `schema_is_complete()` first so a corrupt DB self-repairs
**without `--force`**. Pinned by `test_create_schema_repairs_stamped_but_empty_database`
and `test_init_repairs_corrupt_db_without_force` in
`tests/test_review_fixes_phase6.py`.

**FALSE-ALARM CLASS: packaging reviewer reported LICENSE / alembic.ini / docs missing.**
The packaging specialist reported those files absent. It was **correct about the
world it was given** — a stale partial `/tmp/flytie-dev` copy that had only
changed `.py` files synced into it — and **wrong about the real repo**, where
the files exist. Root cause: a briefing error (the reviewer's sandbox wasn't
faithful), not a reviewer mistake. Status: **REJECTED** (three findings). The
durable consequence: **a pre-flight sandbox-integrity check is now required
before spawning a reviewer** — verify the world the reviewer inspects has every
file the brief mentions. This is the mirror of the Phase 5 model-ID false alarm:
there a reviewer was wrong about the *outside world*; here a reviewer was right
about a *world that wasn't real*. See §3.

**`--out` directory detection was broken.**
Symptom: `flytie export "..." --out ~/cards/` produced a file literally named
`cards` (no extension) that the OS opened as a raw blob. Root cause: the code
checked `str(out).endswith("/")` to detect directory intent, but Typer parses
`--out` as a `pathlib.Path` and `pathlib` strips trailing slashes — the branch
was dead code. Surfaced from a **real-user report** mid-fix. Status:
**FIXED+pinned**. Fix: treat any `--out` with no file extension (or an existing
directory) as a directory. Pinned by
`test_export_creates_directory_from_path_without_extension` and
`test_export_with_explicit_pdf_extension_writes_that_file`.

Also fixed (11 valid findings): duplicate pattern names within one import file
(silent data loss under `--on-conflict overwrite`) → `parse_document` rejects
duplicates up front; multiple-`is_current` ambiguity → rejected (zero remains
the documented fallback); no import file-size bound → `MAX_IMPORT_FILE_BYTES =
50 MiB`; plus docs fixes. All in `tests/test_review_fixes_phase6.py`.

### v0.1.1 — dual-lens hardening (spec-drift + friction log)

**Convergence: `flytie config path` returns the config file, not the DB path.**
The **one finding both lenses hit.** The spec-drift agent flagged it as
ambiguous in the docs (three docs gave three impressions of what it returned);
the friction agent independently logged it as the single thing "Tom" most wanted
to give up over. Status: **FIXED+pinned** via `flytie info` (a new diagnostic
that prints resolved DB path, config path, data dir, schema revision, and
counts, and never displays the API key) plus doc disambiguation.

**Spec §8 promised refusal to start against a DB newer than known head — never implemented.**
Root cause: a guarantee promised since v0.0 for users who downgrade after
migrating. A user hitting it would have a silently-misbehaving install, not a
loggable friction moment — only the spec audit could catch it. Status:
**FIXED+pinned**. `Database.validate_compatibility()` raises
`IncompatibleDatabaseError` → **exit code 4** ("incompatible environment") with a
named recovery path. `flytie info` deliberately bypasses the check so it stays
usable as a diagnostic. Pinned by
`test_validate_compatibility_rejects_unknown_revision` and
`test_info_still_works_against_incompatible_db` in `tests/test_v0_1_1_fixes.py`.

**`jinja2` was in the `[pdf]` extra, but spec FR-5 promised `--html` on a bare install.**
Root cause: the wheel technically violated the FR-5 promise that `--html` needs
no extras and no native libraries. Status: **FIXED+pinned** (a Changed, not a
bug). `jinja2` moved to core dependencies; the `[pdf]` extra retains WeasyPrint
+ native libs only.

**REJECTED: renumber the `(imported)` conflict-rename suffix (finding "D11").**
When `flytie import-db --on-conflict rename` hits a name collision, it imports
under `"<name> (imported)"`, then `"<name> (imported 2)"`, etc. (see
`_unique_name` in `src/flytie/core/portability.py`). A reviewer proposed
renumbering that scheme. The maintainer **kept it as-is** — a **taste call, not
a technical optimization.** Status: **REJECTED — do not re-propose.** This is
the canonical example of why judgement-call findings go to the user: an
autonomous agent would have implemented the renumbering and pinned the wrong
choice with a regression test. Also caught in this pass: the friction agent's
ten UX findings (missing `flytie tag list`, `?` symbol undefined near its first
use, thin `--help` text), all fixed.

### v0.1.2 — CI/quality hardening

**Coverage measured 67% naively; real coverage was 91%+.**
Root cause: a naive `fail_under=85` counted inert files (the `*_old.py` fossils,
generated code) against the total. Status: **FIXED+pinned**. Fix: an `omit`
list in `[tool.coverage.run]` mirroring pytest's `--ignore` and ruff's
`exclude` — one project answer to "what counts as live code." Coverage rose to
91%+ without changing what tests run or what ships.

**`ruff --fix` thrashed import order across environments.**
Symptom: CI failed on I001 import-sorting errors local `ruff check` couldn't
reproduce; local `ruff check --fix` *reverted* a CI-correct ordering on every
run. Root cause: ruff's isort heuristic guessed first-party vs. third-party
differently in different environments (sandbox vs. CI disagreed on `alembic`
and on `flytie.*`). Status: **FIXED+pinned**. Fix: explicit
`[tool.ruff.lint.isort]` `known-first-party = ["flytie"]` + `known-third-party`.
Meta-lesson: **two `ruff --fix` autonomy bugs (v0.1.1 + v0.1.2) both root-caused
to "ruff was guessing without explicit config." The class is `underspecified
config → environment-dependent behavior`; the cure is explicit declaration even
when the heuristic works locally.**

**WeasyPrint SIGSEGV during test collection on macOS.**
Symptom: a hard segfault (not a catchable exception) during pytest collection on
Anaconda Python + Homebrew Pango (binary-incompatible glib/cairo). Root cause:
SIGSEGV kills the process before any `try/except` can fire. Status:
**FIXED+pinned**. Fix: a **subprocess probe** —
`subprocess.run([sys.executable, "-c", "import weasyprint"])` before the
in-process import; a crash in the throwaway process is a non-zero exit the parent
detects and skips cleanly. **New PDF tests must use this pattern**, not
`try/except (ImportError, OSError)`. Reference: `tests/test_pdf_export.py`,
`tests/test_cli_export.py`.

**Catalogued lessons compound backward — the autouse CliRunner fixture.**
The v0.1.1 CliRunner terminal-width lesson (Rich wraps output at ~80 cols and
breaks substring assertions) was structurally eliminated in v0.1.2 by an autouse
`_wide_cli_runner_env` fixture in `tests/conftest.py` defaulting `COLUMNS=200`.
Notably it **retroactively fixed two pre-existing tests** that had been silently
wrap-fragile for many phases — the first time a practices-doc entry doubled back
to fix code that predated the lesson. Status: **FIXED+pinned** (structural).
Belt-and-suspenders: the pre-push hook runs `COLUMNS=80 pytest` as a stress
check.

**ACCEPTED deviation: cold-start budget raised 300 ms → 600 ms.**
Root cause: the original 300 ms spec NFR was tight on real CI hardware and
flaked. Status: **ACCEPTED deviation** — deliberately raised to 600 ms (best-of-5
`flytie --version`) with the rationale documented inline in spec §4: the gate's
purpose is regression detection on the import graph, not chasing the last 100 ms.
Pinned by the cold-start test in `tests/test_v0_1_2_fixes.py`. **Do not "restore"
300 ms** — the change is intentional.

**`black` dropped.** Status: **ACCEPTED** (Changed). `ruff format` is
Black-compatible; running both was noise. `ruff` is the sole formatter.

**Two v0.1.2 audit false alarms — correctly discarded.** See §3.

### v0.2.0 — bundled feature phase (undelete, stats, merge, diff)

**CRITICAL: `stats` reported "No patterns yet" when only deleted patterns existed.**
Symptom: a library with only soft-deleted patterns showed "No patterns yet" and
all-zero reference-table counts. Root cause: `library_stats` returned early with
zero counts when `active_patterns == 0`, and the CLI printed the wrong message.
Status: **FIXED+pinned**. Fix: the early-return path now computes reference-table
totals before returning; the CLI branches on `deleted_patterns` and prints "No
active patterns (N deleted)". Pinned by `test_stats_deleted_only_library_core`,
`test_stats_deleted_only_library_cli`, `test_stats_truly_empty_library_cli` in
`TestReviewFixesPhase1` (`tests/test_v0_2_phase1.py`).

**Bundled-phase pattern adopted.** Four non-overlapping features
(undelete/stats/merge/diff) were reviewed in **one** three-reviewer pass. Status:
process decision, worth knowing — the bundling saved ~3 review cycles *and*
surfaced cross-feature interactions (stats-after-delete, merge-across-versions)
that single-feature reviews would have missed. Also fixed: self-merge exit code
2-not-1; dry-run version-row count hidden behind a guard; `_lookup_material`
using `func.lower()` instead of `normalize_name`.

**Two v0.2.0 false alarms — correctly discarded.** See §3.

### v0.2.1 — dedupe, --from-suggestion, triple-lens hardening

Six per-feature review fixes, all **FIXED+pinned**: hook-placeholder warning when
a `--from-suggestion` has no hook size; stale-candidate skip in the interactive
dedupe loop (a pair whose materials were already merged is skipped, not shown as
"Merge failed"); unit-mismatch quantity-discard warning in `merge_materials`;
`save_suggestions` OSError warning instead of silent swallow; `s`/`q` shortcut
docs; `hook_size=None` test coverage. The per-feature reviewers raised **no
false alarms** this round.

**Triple-lens hardening audit caught `release.yml` missing the Python matrix.**
Root cause: `release.yml`'s test job ran a single Python version while `ci.yml`
ran a 3.10/3.11/3.12 matrix. Status: **FIXED+pinned**. `release.yml` now runs
`python-version: ["3.10", "3.11", "3.12"]` on the test job (build job stays
3.12). Verify: `grep python-version .github/workflows/release.yml`.

**`COLUMNS=80` wrap fragility in `test_dedupe.py` caught at the gate.**
Symptom: `test_unit_mismatch_warns...` asserted `"units differ"`, which passed at
`COLUMNS=200` (the autouse default) but wrapped mid-phrase at `COLUMNS=80` (the
pre-push width). Root cause: the same Rich-wrap class the v0.1.2 infrastructure
was built to catch — and it did. Status: **FIXED+pinned**. Fix: assert on the
un-wrapped substring; `COLUMNS=80` added to both CI workflows' test steps.

**"Adding warnings breaks exact-count assertions" lesson.**
The new unit-mismatch warning broke `test_merge_duplicate_different_units_keeps_target`,
which asserted `len(result.warnings) == 1` (now 2). Status: **FIXED+pinned**.
Lesson (mirror of the regression-test-per-fix rule): **when adding a new warning
or message to an existing code path, grep for tests asserting exact counts on
that output and update them in the same commit.**

---

## 3. False-alarm registry

Re-raising these wastes a triage cycle. Before re-raising, run the check in the
last column.

| Claim | Why it was wrong | Check before re-raising |
|---|---|---|
| Model ID `Codex-sonnet-4-6` doesn't exist (Phase 5) | Reviewer's **knowledge cutoff predated the release**. A confident claim about the outside world. | Verify the current model ID against Anthropic docs / the API, not against a reviewer's training data. |
| `LICENSE` / `alembic.ini` / `docs/` are missing (Phase 6) | Reviewer inspected a **stale partial `/tmp` sandbox** with only `.py` files synced. Correct about that world; wrong about the repo. | `git ls-files \| grep -E 'LICENSE\|alembic.ini\|docs/'` in the real working tree. Run a pre-flight sandbox-integrity check before any review. |
| "Three-tier vs two-stage" gating language is inconsistent (v0.1.2 audit) | Ambiguity in the audit's **own brief**, not in the project. | Read `CONTRIBUTING.md`'s hook-layout section; the three-tier model is coherent. |
| CI coverage gate isn't enforced / needs an explicit `--cov-fail-under` flag (v0.1.2 audit) | Finding **didn't account for `[tool.coverage.report] fail_under = 85` being read automatically by pytest-cov** on any `pytest --cov` run. | Confirm `fail_under = 85` in `pyproject.toml`; `pytest --cov` enforces it without a CLI flag. |
| Data #C2: `p_name` null-guard is missing (v0.2.0) | **Reviewer self-downgraded** — the `pattern.name_display if pattern else "?"` guard is present and correct. | Read the merge output path in `core/patterns.py`. |
| Data #H2: dry-run guard missing on the quantity-mutation line (v0.2.0) | **Reviewer self-downgraded** — the dry-run guard *is* present on that line. | Read `merge_materials`' dry-run branch. |

Note: the v0.2.0 phase summary also lists two more *non-bug* observations left
as-is by design (UX #4: a single-subcommand Typer group renders `--help`
correctly on the pinned Typer version; UX #8: a harmless defensive guard in
`render_stats`). These were not "false alarms" so much as "not worth changing" —
don't re-open them either.

---

## 4. Accepted spec deviations

These are **knowing** departures from the original spec, all **backported into
the spec** so the living spec matches the code. Do not "fix" them back toward the
original spec text — the spec text now agrees with the code.

| Deviation | Original spec said | Reality | Backported |
|---|---|---|---|
| Python target | 3.11+ | **3.10+** (dev sandbox had 3.10; CI matrix runs 3.10/3.11/3.12) | Yes |
| Material categories | fixed list | `MATERIAL_CATEGORIES` is a **superset** — `bead`, `weight`, `adhesive` added (`src/flytie/models.py`) | Yes |
| Config storage | a `config` row **table** in the DB | a **TOML config file** (`Settings` dataclass + `ConfigFile`); no DB config table | Yes |
| add/edit input | interactive prompts / `$EDITOR` | **flag-driven** `add`/`edit` (with `--from-file` for bulk) | Yes (v0.1.1) |
| Pattern file formats | YAML/JSON | **TOML + JSON** (YAML dropped) | Yes (v0.1.1) |
| Cold-start budget | 300 ms | **600 ms** best-of-5 (rationale in spec §4) | Yes (v0.1.2) |

---

## 5. How to add an entry

When an investigation closes:

1. **Append to §2** under the current release, in the fixed shape:
   **Symptom → Root cause → Evidence (the file/test/commit that pins it) →
   Status** (one of FIXED+pinned / ACCEPTED deviation / REJECTED proposal /
   FALSE ALARM).
2. **If FIXED+pinned:** name the regression test. The project contract is *no
   shipped bug ever re-surfaces silently* — per-phase fixes go in
   `tests/test_review_fixes_phase{N}.py`, hardening-pass fixes in
   `tests/test_v0_X_Y_fixes.py`, each test's docstring naming the reviewer and
   severity.
3. **If FALSE ALARM or REJECTED:** add a row to §3 (false alarm) or a REJECTED
   entry to §2 — **name why it was wrong and what to check** — so a future audit
   doesn't re-raise it. This is non-negotiable project canon: false alarms are
   named explicitly.
4. **If it is a recurring-class failure** (something a future engineer will hit
   again — a symptom with a repeatable triage), **also add it to
   `flytie-debugging-playbook`.** This chronicle records the settled instance;
   the playbook records the recurring procedure. A FUSE deadlock, a Rich-wrap
   assertion break, or a WeasyPrint SIGSEGV belongs in both.
5. **If it is an accepted spec deviation:** add a row to §4 **and** backport the
   spec (`fly-tying-tracker-spec.md`). A living spec is a feature; a fossilized
   spec is a smell.

Never delete an entry even when a practice is later superseded — the evolution
is the value.

---

## When NOT to use this skill

- **You have a live symptom and want a fix procedure** (a deadlock now, a broken
  assertion now) → `flytie-debugging-playbook` (recurring failure modes,
  symptom → triage → fix).
- **You want the change process for a fix** (change classes, gates, what needs a
  regression test) → `flytie-change-control`.
- **You want the design rationale / invariants / weak points** of a subsystem →
  `flytie-architecture-contract`.
- **You want to run a reviewer pass or triage findings** → `flytie-subagent-orchestration`.
- **You want test conventions / evidence standards** → `flytie-validation-and-qa`.

This skill is only for: *has this already been investigated, rejected, or
settled?*

---

## Provenance and maintenance

- **Date:** 2026-07-02. **Project version:** v0.2.1 (tagged, on PyPI).
- **Sources (all verified against the working copy on this date):** git history
  and tags (`git log --oneline`, `git tag`); `CHANGELOG.md`; the per-phase
  regression test files (`tests/test_review_fixes_phase{2..6}.py`,
  `test_v0_1_1_fixes.py`, `test_v0_2_phase1.py`, `test_dedupe.py`,
  `test_suggestions.py`); source (`src/flytie/db.py`, `ai/suggest.py`,
  `core/portability.py`, `models.py`, `cli.py`); `pyproject.toml`;
  `.github/workflows/release.yml`. Narrative detail was extracted and embedded
  from gitignored internal docs (`handoff.md`, `ai-development-practices/`,
  `collaboration-retrospective/`, `phase-summaries/`) — **do not cite those as
  load-bearing sources; a fresh clone won't have them.** Deeper reading, if
  present in your working copy: `phase-summaries/phase-*.md`,
  `collaboration-retrospective/phases.md`.
- **Spot-checked entries (6+):** Phase 6 stamped-but-empty →
  `grep -n stamped tests/test_review_fixes_phase6.py` (functions at lines 57, 91);
  `--out` bug → `test_export_creates_directory_from_path_without_extension`
  (line 323, same file); Phase 5 streaming + string-aware parse →
  `test_cli_suggest_wires_on_chunk_callback` (line 323 of
  `test_review_fixes_phase5.py`) and `in_string` scanner in `ai/suggest.py`
  (lines 197–210); v0.1.1 exit-code-4 →
  `test_validate_compatibility_rejects_unknown_revision` +
  `IncompatibleDatabaseError` in `db.py:24` / `cli.py:104`; v0.2.0 stats →
  `test_stats_deleted_only_library_cli` asserting "No active patterns"
  (`test_v0_2_phase1.py:875`); v0.2.1 Python matrix →
  `grep python-version .github/workflows/release.yml` (line 16). CHANGELOG
  cross-checked for the `[0.2.1]`, `[0.2.0]`, `[0.1.2]`, `[0.1.1]` sections.
- **One-line re-verification:**
  ```bash
  git tag && \
  grep -rn "def test_" tests/test_review_fixes_phase6.py tests/test_v0_2_phase1.py | grep -i "stamped\|no active\|out_" && \
  grep -n "python-version\|fail_under" .github/workflows/release.yml pyproject.toml && \
  ls src/flytie/*_old.py tests/*_old.py 2>/dev/null
  ```
