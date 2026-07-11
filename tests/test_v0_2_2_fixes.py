"""Paired regression tests for the v0.2.2 full-project review findings.

Each test names the reviewer and severity of the finding it pins.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from flytie import db as db_module
from flytie.ai.suggest import _status_error_message
from flytie.cli import app
from flytie.config import Settings, load_settings
from flytie.core import dedupe as dedupe_repo
from flytie.core import patterns as patterns_repo
from flytie.core import portability as portability_repo
from flytie.core.dto import MaterialLineDTO, PatternInput
from flytie.core.suggestions import NoSuggestionsError, load_suggestions
from flytie.db import Database
from flytie.models import Material

# ===========================================================================
# H1 — `edit --rename-to` must update name_key, not just name_display
# (skeptical-senior-engineer reviewer, HIGH)
# ===========================================================================


def _init(runner: CliRunner) -> None:
    r = runner.invoke(app, ["init"])
    assert r.exit_code == 0, r.stdout


def _add_pattern(runner: CliRunner, name: str, hook: str = "14") -> None:
    r = runner.invoke(app, ["add", name, "--hook", hook, "--material", "thread,thread,1,spool"])
    assert r.exit_code == 0, r.stdout


def test_rename_to_updates_addressability_cli(env_dirs: tuple[Path, Path]) -> None:
    """H1 (skeptical-senior-engineer, HIGH): rename must move name_key, not just name_display."""
    runner = CliRunner()
    _init(runner)
    _add_pattern(runner, "Adams")

    r = runner.invoke(app, ["edit", "Adams", "--rename-to", "Parachute Adams"])
    assert r.exit_code == 0, r.stdout

    ok = runner.invoke(app, ["view", "Parachute Adams"])
    assert ok.exit_code == 0, ok.stdout

    gone = runner.invoke(app, ["view", "Adams"])
    assert gone.exit_code == 1, gone.stdout


def test_edit_pattern_core_updates_name_key(session) -> None:  # type: ignore[no-untyped-def]
    """H1 (skeptical-senior-engineer, HIGH): core-level edit_pattern must update name_key."""
    patterns_repo.create_pattern(session, PatternInput(name="Adams", hook_size="14"))
    patterns_repo.edit_pattern(
        session, "Adams", PatternInput(name="Parachute Adams", hook_size="14")
    )
    renamed = patterns_repo.get_pattern(session, "Parachute Adams")
    assert renamed.name_key == "parachute adams"
    assert renamed.name_display == "Parachute Adams"
    with pytest.raises(patterns_repo.PatternNotFoundError):
        patterns_repo.get_pattern(session, "Adams")


# ===========================================================================
# H1 collision — rename must not silently steal another pattern's name
# ===========================================================================


def test_rename_collision_raises_core(session) -> None:  # type: ignore[no-untyped-def]
    """H1 (skeptical-senior-engineer, HIGH): renaming onto an existing name_key is refused."""
    patterns_repo.create_pattern(session, PatternInput(name="Adams", hook_size="14"))
    patterns_repo.create_pattern(session, PatternInput(name="Elk Hair Caddis", hook_size="14"))
    with pytest.raises(patterns_repo.DuplicatePatternError):
        patterns_repo.edit_pattern(
            session, "Adams", PatternInput(name="Elk Hair Caddis", hook_size="14")
        )


def test_rename_collision_cli_nonzero_exit(env_dirs: tuple[Path, Path]) -> None:
    """H1 (skeptical-senior-engineer, HIGH): CLI-level rename collision exits non-zero with a clear message."""
    runner = CliRunner()
    _init(runner)
    _add_pattern(runner, "Adams")
    _add_pattern(runner, "Elk Hair Caddis")

    r = runner.invoke(app, ["edit", "Adams", "--rename-to", "Elk Hair Caddis"])
    assert r.exit_code != 0
    assert "already exists" in (r.stdout + r.stderr)


def test_rename_collision_with_soft_deleted_pattern_refused(session) -> None:  # type: ignore[no-untyped-def]
    """H1 (skeptical-senior-engineer, HIGH): soft-deleted patterns still hold their name_key globally."""
    patterns_repo.create_pattern(session, PatternInput(name="Adams", hook_size="14"))
    patterns_repo.create_pattern(session, PatternInput(name="Elk Hair Caddis", hook_size="14"))
    patterns_repo.soft_delete_pattern(session, "Elk Hair Caddis")

    with pytest.raises(patterns_repo.DuplicatePatternError, match="undelete"):
        patterns_repo.edit_pattern(
            session, "Adams", PatternInput(name="Elk Hair Caddis", hook_size="14")
        )


# ===========================================================================
# H1 same-key tweak — display-only renames stay addressable, no collision check
# ===========================================================================


def test_rename_same_key_display_tweak_stays_addressable(session) -> None:  # type: ignore[no-untyped-def]
    """H1 (skeptical-senior-engineer, HIGH): case-only rename updates display, keeps key, no collision check."""
    patterns_repo.create_pattern(session, PatternInput(name="adams", hook_size="14"))
    patterns_repo.edit_pattern(session, "adams", PatternInput(name="Adams", hook_size="14"))
    p = patterns_repo.get_pattern(session, "adams")
    assert p.name_display == "Adams"
    assert p.name_key == "adams"


# ===========================================================================
# H3 — load_suggestions must raise NoSuggestionsError for schema-invalid JSON
# (skeptical-senior-engineer reviewer, HIGH)
# ===========================================================================


def test_load_suggestions_schema_invalid_json_raises_no_suggestions_error(
    env_dirs: tuple[Path, Path],
) -> None:
    """H3 (skeptical-senior-engineer, HIGH): schema-invalid (but valid) JSON must raise NoSuggestionsError."""
    settings: Settings = load_settings()
    path = settings.data_dir / "last_suggestions.json"
    # Valid JSON, valid top-level shape, but the suggestion object is missing
    # the required `name` field -- Suggestion(**s) raises pydantic.ValidationError.
    path.write_text(
        json.dumps({"suggestions": [{"hook_size": "14", "key_materials": []}]}),
        encoding="utf-8",
    )
    with pytest.raises(NoSuggestionsError):
        load_suggestions(settings)


# ===========================================================================
# C1 doc canary — pin the already-applied doc fix (parent-applied, not ours)
# ===========================================================================


def test_ai_suggestions_doc_does_not_reference_removed_flags() -> None:
    """C1 doc canary: `docs/ai-suggestions.md` must not reference the removed --name/--hook-size flags."""
    doc_path = Path(__file__).resolve().parent.parent / "docs" / "ai-suggestions.md"
    text = doc_path.read_text(encoding="utf-8")
    assert "--name" not in text
    assert "--hook-size" not in text


# ===========================================================================
# C2 — the narrow-terminal stress gate must actually apply
# (testing/CI specialist reviewer, CRITICAL)
# ===========================================================================


def test_narrow_gate_applies_when_env_set(env_dirs: tuple[Path, Path]) -> None:
    """C2 (testing/CI specialist, CRITICAL): FLYTIE_TEST_COLUMNS must reach the CLI.

    Before the v0.2.2 fix, the pre-push/CI `COLUMNS=80` gates were silent
    no-ops: the autouse `_wide_cli_runner_env` fixture overrode the outer
    environment with its 200-column default for every invocation. The
    fixture now reads `FLYTIE_TEST_COLUMNS` as its default. This test only
    asserts under the gate (it skips in normal wide runs), so a pre-push
    or CI stress run self-verifies that the gate is live — if the fixture
    ever stops honoring the variable, the gate run fails here instead of
    silently testing nothing.
    """
    cols = os.environ.get("FLYTIE_TEST_COLUMNS")
    if cols is None:
        pytest.skip("narrow-terminal stress gate not active (FLYTIE_TEST_COLUMNS unset)")
    runner = CliRunner()
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0, r.stdout
    widest = max(len(line) for line in r.stdout.splitlines() if line.strip())
    assert widest <= int(cols), (
        f"CLI output is {widest} columns wide but FLYTIE_TEST_COLUMNS={cols} — "
        "the autouse fixture is no longer honoring the stress-gate variable."
    )


def test_explicit_env_still_wins_over_fixture_default(env_dirs: tuple[Path, Path]) -> None:
    """C2 (testing/CI specialist, CRITICAL): per-test explicit env beats both defaults."""
    runner = CliRunner()
    r = runner.invoke(app, ["--help"], env={"COLUMNS": "80"})
    assert r.exit_code == 0, r.stdout
    widest = max(len(line) for line in r.stdout.splitlines() if line.strip())
    assert widest <= 80


def test_help_critical_tokens_survive_narrow_terminals() -> None:
    """C2 follow-on (v0.2.2): long help tokens must not be ellipsis-truncated at 80 cols.

    Rich truncates single tokens longer than the help cell with `…` instead
    of wrapping them. The original `name,category,quantity,unit` and
    `docs/pattern-file-format.md` tokens were invisible on a standard
    80-column terminal — defeating the v0.1.1 friction fixes they carried.
    The help wording is now wrap-friendly; pin that at 80 columns directly.
    """
    runner = CliRunner()
    r = runner.invoke(app, ["add", "--help"], env={"COLUMNS": "80"})
    assert r.exit_code == 0
    assert "…" not in r.stdout, (
        "flytie add --help truncates content at 80 columns — some help "
        "string contains a token wider than the help cell."
    )


# ===========================================================================
# M6 — no ambient ANTHROPIC_API_KEY can reach a test
# (testing/CI specialist reviewer, MEDIUM)
# ===========================================================================


def test_ambient_api_key_is_stripped() -> None:
    """M6 (testing/CI specialist, MEDIUM): autouse fixture strips ANTHROPIC_API_KEY.

    Previously the guarantee was per-test discipline (each AI test
    remembering `monkeypatch.delenv`); now `_no_ambient_api_key` in
    conftest.py strips the variable structurally for every test. A real
    key exported in a contributor's shell can never change test behavior.
    """
    assert "ANTHROPIC_API_KEY" not in os.environ


# ===========================================================================
# H4 — import path bypasses the hook-size invariant
# (skeptical-senior-engineer reviewer, HIGH)
# ===========================================================================


def _minimal_export_payload(hook_size: str) -> dict:
    return {
        "flytie_export_version": 1,
        "exported_at": "2026-01-01T00:00:00",
        "patterns": [
            {
                "name": "Adams",
                "is_deleted": False,
                "tags": [],
                "species": [],
                "versions": [
                    {
                        "version_number": 1,
                        "hook_size": hook_size,
                        "difficulty": None,
                        "instructions": "",
                        "notes": "",
                        "created_at": "2026-01-01T00:00:00",
                        "is_current": True,
                        "materials": [],
                    }
                ],
            }
        ],
    }


def test_h4_blank_hook_size_rejected_at_parse() -> None:
    """H4 (skeptical-senior-engineer, HIGH): a blank hook_size in an import file is rejected at parse."""
    payload = _minimal_export_payload("  ")
    with pytest.raises(portability_repo.PortabilityError):
        portability_repo.parse_document(json.dumps(payload))


def test_h4_blank_hook_size_rejected_via_cli(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    """H4 (skeptical-senior-engineer, HIGH): import-db exits non-zero and writes nothing to the DB."""
    runner = CliRunner()
    _init(runner)
    payload = _minimal_export_payload("  ")
    import_path = tmp_path / "bad-import.json"
    import_path.write_text(json.dumps(payload), encoding="utf-8")

    r = runner.invoke(app, ["import-db", str(import_path)])
    assert r.exit_code != 0

    listed = runner.invoke(app, ["list"])
    assert listed.exit_code == 0
    assert "Adams" not in listed.stdout


# ===========================================================================
# M4 — create_schema conflates never-migrated with half-migrated
# (skeptical-senior-engineer reviewer, MEDIUM)
# ===========================================================================


def test_m4_create_schema_refuses_when_fallback_cant_repair(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M4 (skeptical-senior-engineer, MEDIUM): create_schema refuses instead of reporting false success.

    Models a half-applied migration: `upgrade_to_head` throws (caught by the
    bare `except Exception`), and the direct-build fallback can't repair the
    damage (patched to a no-op here, matching M4's description of the
    fallback being "a no-op on existing tables"). Before this fix,
    `create_schema` would return normally with the `patterns` table still
    missing.
    """
    db = Database.from_settings(settings)
    db.create_schema()
    assert db.schema_is_complete()

    with db.engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        conn.exec_driver_sql("DROP TABLE patterns")

    def _boom() -> None:
        raise RuntimeError("simulated broken migration")

    monkeypatch.setattr(db, "upgrade_to_head", _boom)
    monkeypatch.setattr(db, "_build_schema_directly", lambda: None)

    with pytest.raises(db_module.SchemaCreationError) as exc_info:
        db.create_schema()
    assert str(settings.db_path) in str(exc_info.value)
    db.engine.dispose()


def test_m4_normal_init_happy_path_still_works(env_dirs: tuple[Path, Path]) -> None:
    """M4 (skeptical-senior-engineer, MEDIUM): the ordinary init path is unaffected by the new check."""
    runner = CliRunner()
    r = runner.invoke(app, ["init"])
    assert r.exit_code == 0, r.stdout
    assert "Initialized flytie database" in r.stdout


# ===========================================================================
# M5 — merge_materials mutates soft-deleted patterns' rows but under-reports
# (skeptical-senior-engineer reviewer, MEDIUM)
# ===========================================================================


def test_m5_merge_reports_deleted_affected_patterns_separately(session) -> None:  # type: ignore[no-untyped-def]
    """M5 (skeptical-senior-engineer, MEDIUM): merge stays global; deleted-affected patterns are reported, labeled."""
    patterns_repo.create_pattern(
        session,
        PatternInput(
            name="Ghost",
            hook_size="14",
            materials=[MaterialLineDTO(canonical_name="old hackle", category="hackle")],
        ),
    )
    patterns_repo.create_pattern(
        session,
        PatternInput(
            name="Adams",
            hook_size="14",
            materials=[MaterialLineDTO(canonical_name="new hackle", category="hackle")],
        ),
    )
    patterns_repo.soft_delete_pattern(session, "Ghost")

    result = patterns_repo.merge_materials(session, "old hackle", "new hackle")
    assert result.affected_patterns == []
    assert result.deleted_affected_patterns == ["Ghost"]
    assert result.version_rows == 1

    # The deleted pattern's rows really were rewritten -- undelete and verify.
    patterns_repo.undelete_pattern(session, "Ghost")
    ghost = patterns_repo.get_pattern(session, "Ghost")
    mat_names = [pm.material.canonical_name for pm in ghost.current_version.materials]
    assert mat_names == ["new hackle"]


def test_m5_merge_cli_labels_deleted_affected_patterns(env_dirs: tuple[Path, Path]) -> None:
    """M5 (skeptical-senior-engineer, MEDIUM): `material merge` CLI output labels deleted patterns."""
    runner = CliRunner()
    _init(runner)
    r1 = runner.invoke(
        app, ["add", "Ghost", "--hook", "14", "--material", "old hackle,hackle,1,feather"]
    )
    assert r1.exit_code == 0, r1.stdout
    r2 = runner.invoke(
        app, ["add", "Adams", "--hook", "14", "--material", "new hackle,hackle,1,feather"]
    )
    assert r2.exit_code == 0, r2.stdout
    del_r = runner.invoke(app, ["delete", "Ghost", "--yes"])
    assert del_r.exit_code == 0, del_r.stdout

    r = runner.invoke(app, ["material", "merge", "old hackle", "new hackle"])
    assert r.exit_code == 0, r.stdout
    assert "(deleted)" in r.stdout
    assert "Ghost" in r.stdout


# ===========================================================================
# M8 — dedupe scoring inflates short-name false positives + threshold range
# (skeptical-senior-engineer reviewer, MEDIUM)
# ===========================================================================


def test_m8_short_name_false_positive_not_a_candidate(session) -> None:  # type: ignore[no-untyped-def]
    """M8 (skeptical-senior-engineer, MEDIUM): "silk"/"silt" is not a candidate at the default threshold."""
    session.add(Material(canonical_name="silk", category="other"))
    session.add(Material(canonical_name="silt", category="other"))
    session.flush()
    assert dedupe_repo.find_duplicate_candidates(session) == []


def test_m8_short_jaccard_qualifying_pair_still_candidate() -> None:
    """M8 (skeptical-senior-engineer, MEDIUM): a short pair with real token overlap can still qualify."""
    assert dedupe_repo.combined_similarity("a b", "b a") >= 0.6


def test_m8_long_near_duplicate_pair_still_candidate() -> None:
    """M8 (skeptical-senior-engineer, MEDIUM): a long near-duplicate pair is unaffected by the short-name guard."""
    score = dedupe_repo.combined_similarity("peacock herl", "peacock hurl")
    assert score >= 0.6


def test_m8_threshold_out_of_range_rejected(env_dirs: tuple[Path, Path]) -> None:
    """M8 (skeptical-senior-engineer, MEDIUM): --threshold outside [0, 1] is a Typer range error."""
    runner = CliRunner()
    _init(runner)
    too_high = runner.invoke(app, ["material", "dedupe", "--threshold", "1.5"])
    assert too_high.exit_code != 0
    too_low = runner.invoke(app, ["material", "dedupe", "--threshold", "-0.1"])
    assert too_low.exit_code != 0


def test_m8_jaccard_empty_empty_is_zero() -> None:
    """M8 (skeptical-senior-engineer, MEDIUM): jaccard_similarity("", "") no longer returns 1.0."""
    assert dedupe_repo.jaccard_similarity("", "") == 0.0


# ===========================================================================
# FIX 5 — 5xx-vs-4xx error message split
# (skeptical-senior-engineer reviewer, LOW)
# ===========================================================================


class _FakeStatusError:
    """Minimal stand-in for `anthropic.APIStatusError` -- only `status_code` matters."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_fix5_unlisted_4xx_gives_client_side_message() -> None:
    """FIX 5 (skeptical-senior-engineer, LOW): an unlisted 4xx gets a client-side (request/key) message."""
    msg = _status_error_message(_FakeStatusError(418))
    assert "ANTHROPIC_API_KEY" in msg


def test_fix5_unlisted_5xx_gives_server_side_message() -> None:
    """FIX 5 (skeptical-senior-engineer, LOW): an unlisted 5xx gets a server-side (retry-later) message."""
    msg = _status_error_message(_FakeStatusError(503))
    assert "try again" in msg.lower()
    assert "ANTHROPIC_API_KEY" not in msg


def test_fix5_4xx_and_5xx_messages_are_distinct() -> None:
    """FIX 5 (skeptical-senior-engineer, LOW): unlisted 4xx and 5xx codes produce different messages."""
    assert _status_error_message(_FakeStatusError(418)) != _status_error_message(
        _FakeStatusError(503)
    )


# ===========================================================================
# FIX 6 — reject renames that normalize to an empty key
# (v0.2.2 slice-A follow-up)
# ===========================================================================


# NOTE: `flytie.models.normalize_name` only lowercases, strips, and collapses
# whitespace -- it does not strip punctuation, so a literal all-punctuation
# string like "!!!" does NOT normalize to "" in this codebase today (verified:
# `flytie add "!!!"` is accepted). There is therefore no real input where
# `payload.name.strip()` is non-empty but `normalize_name(...)` is empty; the
# two tests below exercise the new guard directly via a patched
# `normalize_name` so the guard's logic and message are pinned regardless.
# Surfaced as a discrepancy from the original finding's premise -- worth a
# follow-up decision on whether `normalize_name` should also strip
# punctuation-only names, which would be a separate, wider-reaching change.


def test_fix6_cli_rename_to_empty_normalized_name_fails(
    env_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """FIX 6 (v0.2.2 slice-A follow-up): `edit --rename-to` fails when the new name normalizes to empty."""
    runner = CliRunner()
    _init(runner)
    _add_pattern(runner, "Adams")

    real_normalize_name = patterns_repo.normalize_name

    def _fake_normalize_name(name: str) -> str:
        return "" if name == "!!!" else real_normalize_name(name)

    monkeypatch.setattr(patterns_repo, "normalize_name", _fake_normalize_name)

    r = runner.invoke(app, ["edit", "Adams", "--rename-to", "!!!"])
    assert r.exit_code != 0
    assert "cannot be empty" in (r.stdout + r.stderr).lower()


def test_fix6_core_edit_pattern_empty_normalized_name_raises(
    session,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FIX 6 (v0.2.2 slice-A follow-up): core-level edit_pattern rejects a rename that normalizes to empty."""
    patterns_repo.create_pattern(session, PatternInput(name="Adams", hook_size="14"))

    real_normalize_name = patterns_repo.normalize_name

    def _fake_normalize_name(name: str) -> str:
        return "" if name == "!!!" else real_normalize_name(name)

    monkeypatch.setattr(patterns_repo, "normalize_name", _fake_normalize_name)

    with pytest.raises(ValueError, match="cannot be empty"):
        patterns_repo.edit_pattern(session, "Adams", PatternInput(name="!!!", hook_size="14"))


def test_fix6_noop_edit_with_own_name_still_succeeds(session) -> None:  # type: ignore[no-untyped-def]
    """FIX 6 (v0.2.2 slice-A follow-up): a no-op edit passing the pattern's own name keeps working."""
    patterns_repo.create_pattern(session, PatternInput(name="Adams", hook_size="14"))
    edited = patterns_repo.edit_pattern(
        session, "Adams", PatternInput(name="Adams", hook_size="16")
    )
    assert edited.name_display == "Adams"
    assert edited.current_version.hook_size == "16"
