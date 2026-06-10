"""Tests for suggestion persistence and ``flytie add --from-suggestion``.

Covers: save/load/get round-trip, error cases (missing file, bad index),
the ``--from-suggestion`` CLI path (draft notice, overrides, conflict with
``--from-file``), and the updated suggest hint in render output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from flytie.ai.suggest import Suggestion, SuggestionRequest, SuggestionResult
from flytie.cli import app
from flytie.config import load_settings
from flytie.core.suggestions import (
    NoSuggestionsError,
    SuggestionIndexError,
    get_suggestion,
    load_suggestions,
    save_suggestions,
)

# ===========================================================================
# Fixtures
# ===========================================================================


def _make_result(count: int = 3) -> SuggestionResult:
    """Build a minimal SuggestionResult with *count* suggestions."""
    suggestions = [
        Suggestion(
            name=f"Fly {i}",
            hook_size=str(12 + i * 2),
            key_materials=[f"material-{i}a", f"material-{i}b"],
            rationale=f"Reason {i}",
            is_existing=False,
        )
        for i in range(1, count + 1)
    ]
    return SuggestionResult(
        request=SuggestionRequest(species="trout", season="fall"),
        suggestions=suggestions,
        raw_text="[]",
    )


# ===========================================================================
# Core persistence tests
# ===========================================================================


class TestSaveSuggestions:
    def test_round_trip(self, env_dirs: tuple[Path, Path]) -> None:
        settings = load_settings()
        result = _make_result(2)
        path = save_suggestions(settings, result)
        assert path.exists()

        loaded = load_suggestions(settings)
        assert len(loaded) == 2
        assert loaded[0].name == "Fly 1"
        assert loaded[1].name == "Fly 2"

    def test_overwrites_previous(self, env_dirs: tuple[Path, Path]) -> None:
        settings = load_settings()
        save_suggestions(settings, _make_result(3))
        save_suggestions(settings, _make_result(1))
        loaded = load_suggestions(settings)
        assert len(loaded) == 1

    def test_json_structure(self, env_dirs: tuple[Path, Path]) -> None:
        settings = load_settings()
        path = save_suggestions(settings, _make_result(1))
        data = json.loads(path.read_text())
        assert "timestamp" in data
        assert "request" in data
        assert "suggestions" in data
        assert data["request"]["species"] == "trout"


class TestLoadSuggestions:
    def test_missing_file_raises(self, env_dirs: tuple[Path, Path]) -> None:
        settings = load_settings()
        with pytest.raises(NoSuggestionsError, match="No saved suggestions"):
            load_suggestions(settings)

    def test_corrupt_file_raises(self, env_dirs: tuple[Path, Path]) -> None:
        settings = load_settings()
        path = settings.data_dir / "last_suggestions.json"
        path.write_text("not json at all")
        with pytest.raises(NoSuggestionsError, match="Could not read"):
            load_suggestions(settings)

    def test_missing_key_raises(self, env_dirs: tuple[Path, Path]) -> None:
        settings = load_settings()
        path = settings.data_dir / "last_suggestions.json"
        path.write_text(json.dumps({"timestamp": "x"}))
        with pytest.raises(NoSuggestionsError, match="Could not read"):
            load_suggestions(settings)


class TestGetSuggestion:
    def test_valid_index(self, env_dirs: tuple[Path, Path]) -> None:
        settings = load_settings()
        save_suggestions(settings, _make_result(3))
        s = get_suggestion(settings, 2)
        assert s.name == "Fly 2"

    def test_index_zero_raises(self, env_dirs: tuple[Path, Path]) -> None:
        settings = load_settings()
        save_suggestions(settings, _make_result(3))
        with pytest.raises(SuggestionIndexError, match="#0 does not exist"):
            get_suggestion(settings, 0)

    def test_index_too_high_raises(self, env_dirs: tuple[Path, Path]) -> None:
        settings = load_settings()
        save_suggestions(settings, _make_result(2))
        with pytest.raises(SuggestionIndexError, match="#5 does not exist"):
            get_suggestion(settings, 5)

    def test_no_file_raises_no_suggestions(self, env_dirs: tuple[Path, Path]) -> None:
        settings = load_settings()
        with pytest.raises(NoSuggestionsError):
            get_suggestion(settings, 1)


# ===========================================================================
# CLI: --from-suggestion
# ===========================================================================


class TestFromSuggestionCLI:
    @staticmethod
    def _seed_suggestions(runner: CliRunner, count: int = 3) -> None:
        """Init DB and write a suggestions file via the core API."""
        runner.invoke(app, ["init"])
        settings = load_settings()
        save_suggestions(settings, _make_result(count))

    def test_creates_pattern_from_suggestion(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        self._seed_suggestions(runner)
        r = runner.invoke(app, ["add", "--from-suggestion", "1"])
        assert r.exit_code == 0, r.stdout
        assert "Added" in r.stdout
        assert "Fly 1" in r.stdout
        assert "Draft" in r.stdout

    def test_draft_notice_mentions_category(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        self._seed_suggestions(runner)
        r = runner.invoke(app, ["add", "--from-suggestion", "1"])
        assert "other" in r.stdout
        assert "flytie edit" in r.stdout

    def test_name_override(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        self._seed_suggestions(runner)
        r = runner.invoke(app, ["add", "Custom Name", "--from-suggestion", "1"])
        assert r.exit_code == 0, r.stdout
        assert "Custom Name" in r.stdout

    def test_hook_override(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        self._seed_suggestions(runner)
        r = runner.invoke(app, ["add", "--from-suggestion", "1", "--hook", "18"])
        assert r.exit_code == 0, r.stdout
        # Verify the pattern used the override
        r2 = runner.invoke(app, ["view", "Fly 1"])
        assert "18" in r2.stdout

    def test_invalid_index_exits(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        self._seed_suggestions(runner, count=2)
        r = runner.invoke(app, ["add", "--from-suggestion", "5"])
        assert r.exit_code == 2
        assert "#5 does not exist" in r.output

    def test_no_suggestions_file_exits(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        runner.invoke(app, ["init"])
        r = runner.invoke(app, ["add", "--from-suggestion", "1"])
        assert r.exit_code == 2
        assert "No saved suggestions" in r.output

    def test_conflict_with_from_file(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        self._seed_suggestions(runner)
        r = runner.invoke(app, ["add", "--from-suggestion", "1", "--from-file", "dummy.json"])
        assert r.exit_code == 2
        assert "cannot be used together" in r.output

    def test_materials_have_category_other(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        self._seed_suggestions(runner)
        runner.invoke(app, ["add", "--from-suggestion", "1"])
        r = runner.invoke(app, ["view", "Fly 1"])
        assert r.exit_code == 0, r.stdout
        assert "other" in r.stdout.lower()

    def test_name_required_without_from_suggestion(self, env_dirs: tuple[Path, Path]) -> None:
        """Bare ``flytie add`` with no name should error."""
        runner = CliRunner()
        runner.invoke(app, ["init"])
        r = runner.invoke(app, ["add", "--hook", "14"])
        assert r.exit_code == 2

    def test_none_hook_stores_placeholder_and_warns(self, env_dirs: tuple[Path, Path]) -> None:
        """Review fix A+F: suggestion with no hook_size stores '0' and warns.

        Reviewer: skeptical-senior-engineer, CLI/UX specialist, data-integrity
        specialist (CRITICAL, converged).
        """
        runner = CliRunner()
        runner.invoke(app, ["init"])
        # Build a suggestion with no hook_size.
        no_hook = _make_result(1)
        no_hook.suggestions[0].hook_size = ""
        settings = load_settings()
        save_suggestions(settings, no_hook)

        r = runner.invoke(app, ["add", "--from-suggestion", "1"])
        assert r.exit_code == 0, r.stdout
        assert "placeholder" in r.stdout
        assert "'0'" in r.stdout
        # Verify hook_size in the DB
        r2 = runner.invoke(app, ["view", "Fly 1"])
        assert "0" in r2.stdout

    def test_none_hook_with_override_no_placeholder_warning(
        self, env_dirs: tuple[Path, Path]
    ) -> None:
        """When --hook overrides a missing suggestion hook, no placeholder warning."""
        runner = CliRunner()
        runner.invoke(app, ["init"])
        no_hook = _make_result(1)
        no_hook.suggestions[0].hook_size = ""
        settings = load_settings()
        save_suggestions(settings, no_hook)

        r = runner.invoke(app, ["add", "--from-suggestion", "1", "--hook", "14"])
        assert r.exit_code == 0, r.stdout
        assert "placeholder" not in r.stdout


# ===========================================================================
# Suggest hint text
# ===========================================================================


class TestSuggestHint:
    def test_hint_mentions_from_suggestion(self, env_dirs: tuple[Path, Path]) -> None:
        """The suggest output should mention --from-suggestion for new flies."""
        from unittest.mock import MagicMock, patch

        fake_result = _make_result(1)

        runner = CliRunner()
        runner.invoke(app, ["init"])

        with (
            patch("flytie.ai.resolve_api_key", return_value="sk-ant-fake"),
            patch("flytie.ai.anthropic_streamer", return_value=MagicMock()),
            patch("flytie.ai.generate_suggestions", return_value=fake_result),
        ):
            r = runner.invoke(app, ["suggest", "--species", "trout", "--season", "fall"])

        assert r.exit_code == 0, r.stdout
        assert "--from-suggestion" in r.stdout
