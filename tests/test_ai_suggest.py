"""Unit tests for the AI suggestion module (`flytie.ai.suggest`).

No network and no API key: the Anthropic call is replaced with a fake
`Streamer` that replays canned chunks. Prompt construction and response
parsing are pure functions, tested directly.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest

from flytie.ai.suggest import (
    MAX_GROUNDING_PATTERNS,
    AIError,
    SuggestionRequest,
    build_prompt,
    generate_suggestions,
    parse_suggestions,
    resolve_api_key,
)
from flytie.core.dto import MaterialLineDTO, PatternDTO, PatternVersionDTO

# --- helpers -----------------------------------------------------------------


def _pattern(name: str, hook: str = "14", materials: list[str] | None = None) -> PatternDTO:
    now = datetime(2026, 1, 1)
    version = PatternVersionDTO(
        version_number=1,
        hook_size=hook,
        created_at=now,
        materials=[
            MaterialLineDTO(canonical_name=m, category="other") for m in (materials or [])
        ],
    )
    return PatternDTO(
        id=1, name=name, created_at=now, updated_at=now, current_version=version
    )


def _fake_streamer(chunks: list[str]):
    """Return a Streamer that yields the given chunks verbatim."""

    def _stream(system: str, user: str) -> Iterator[str]:
        yield from chunks

    return _stream


_SAMPLE_JSON = (
    '[{"name": "Parachute Adams", "hook_size": "14", '
    '"key_materials": ["grizzly hackle", "grey dubbing"], '
    '"rationale": "A reliable mayfly imitation for fall."}, '
    '{"name": "Zebra Midge", "hook_size": "20", '
    '"key_materials": ["black thread", "silver wire"], '
    '"rationale": "Works subsurface when fish are keyed on midges."}]'
)


# --- build_prompt ------------------------------------------------------------


def test_build_prompt_includes_all_request_fields() -> None:
    req = SuggestionRequest(
        species="rainbow trout", season="late October",
        water="Henry's Fork", conditions="low and clear", count=4,
    )
    system, user = build_prompt(req, [])
    assert "JSON array" in system
    assert "rainbow trout" in user
    assert "late October" in user
    assert "Henry's Fork" in user
    assert "low and clear" in user
    assert "4" in user


def test_build_prompt_omits_optional_fields_when_absent() -> None:
    req = SuggestionRequest(species="brown trout", season="spring", count=3)
    _, user = build_prompt(req, [])
    assert "Water:" not in user
    assert "Water conditions:" not in user


def test_grounding_block_includes_patterns() -> None:
    req = SuggestionRequest(species="trout", season="fall")
    _, user = build_prompt(req, [_pattern("Adams", "14", ["grizzly hackle"])])
    assert "Adams" in user
    assert "hook 14" in user
    assert "grizzly hackle" in user


def test_grounding_block_caps_pattern_count() -> None:
    req = SuggestionRequest(species="trout", season="fall")
    many = [_pattern(f"Pattern {i}") for i in range(MAX_GROUNDING_PATTERNS + 20)]
    _, user = build_prompt(req, many)
    # Only the first MAX_GROUNDING_PATTERNS appear.
    assert f"Pattern {MAX_GROUNDING_PATTERNS - 1}" in user
    assert f"Pattern {MAX_GROUNDING_PATTERNS + 5}" not in user


def test_grounding_block_excludes_instructions_and_notes() -> None:
    """Privacy: instructions/notes must never reach the prompt."""
    now = datetime(2026, 1, 1)
    version = PatternVersionDTO(
        version_number=1, hook_size="14", created_at=now,
        instructions="SECRET-INSTRUCTIONS-TEXT",
        notes="SECRET-NOTES-TEXT",
        materials=[MaterialLineDTO(canonical_name="thread", category="thread")],
    )
    dto = PatternDTO(id=1, name="Adams", created_at=now, updated_at=now, current_version=version)
    req = SuggestionRequest(species="trout", season="fall")
    _, user = build_prompt(req, [dto])
    assert "SECRET-INSTRUCTIONS-TEXT" not in user
    assert "SECRET-NOTES-TEXT" not in user


# --- parse_suggestions -------------------------------------------------------


def test_parse_valid_json_array() -> None:
    suggestions = parse_suggestions(_SAMPLE_JSON, set())
    assert len(suggestions) == 2
    assert suggestions[0].name == "Parachute Adams"
    assert suggestions[0].hook_size == "14"
    assert "grizzly hackle" in suggestions[0].key_materials
    assert suggestions[0].rationale.startswith("A reliable")


def test_parse_marks_existing_library_patterns() -> None:
    suggestions = parse_suggestions(_SAMPLE_JSON, {"parachute adams"})
    by_name = {s.name: s for s in suggestions}
    assert by_name["Parachute Adams"].is_existing is True
    assert by_name["Zebra Midge"].is_existing is False


def test_parse_strips_code_fences() -> None:
    fenced = f"```json\n{_SAMPLE_JSON}\n```"
    assert len(parse_suggestions(fenced, set())) == 2


def test_parse_finds_array_embedded_in_prose() -> None:
    noisy = f"Here are my picks:\n{_SAMPLE_JSON}\nHope that helps!"
    assert len(parse_suggestions(noisy, set())) == 2


def test_parse_malformed_returns_empty() -> None:
    assert parse_suggestions("not json at all", set()) == []
    assert parse_suggestions("[ {broken", set()) == []
    assert parse_suggestions('{"name": "not an array"}', set()) == []


def test_parse_skips_items_without_a_name() -> None:
    blob = '[{"hook_size": "14"}, {"name": "Adams", "hook_size": "12"}]'
    suggestions = parse_suggestions(blob, set())
    assert len(suggestions) == 1
    assert suggestions[0].name == "Adams"


# --- resolve_api_key ---------------------------------------------------------


def test_resolve_api_key_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test123")
    assert resolve_api_key() == "sk-ant-test123"


def test_resolve_api_key_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(AIError, match="No Anthropic API key"):
        resolve_api_key()


def test_resolve_api_key_blank_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    with pytest.raises(AIError):
        resolve_api_key()


# --- generate_suggestions (end-to-end with a fake streamer) ------------------


def test_generate_suggestions_end_to_end() -> None:
    req = SuggestionRequest(species="rainbow trout", season="fall", count=2)
    grounding = [_pattern("Parachute Adams", "14", ["grizzly hackle"])]
    streamer = _fake_streamer([_SAMPLE_JSON[:30], _SAMPLE_JSON[30:]])
    result = generate_suggestions(req, grounding, streamer)
    assert len(result.suggestions) == 2
    assert result.raw_text == _SAMPLE_JSON
    # The library pattern is flagged.
    adams = next(s for s in result.suggestions if s.name == "Parachute Adams")
    assert adams.is_existing is True


def test_generate_suggestions_invokes_on_chunk() -> None:
    req = SuggestionRequest(species="trout", season="fall")
    chunks_seen: list[str] = []
    streamer = _fake_streamer(["chunk-a", "chunk-b", "chunk-c"])
    generate_suggestions(req, [], streamer, on_chunk=chunks_seen.append)
    assert chunks_seen == ["chunk-a", "chunk-b", "chunk-c"]


def test_generate_suggestions_keeps_raw_text_on_parse_failure() -> None:
    req = SuggestionRequest(species="trout", season="fall")
    streamer = _fake_streamer(["the model rambled and produced no JSON"])
    result = generate_suggestions(req, [], streamer)
    assert result.suggestions == []
    assert "rambled" in result.raw_text


def test_generate_suggestions_propagates_streamer_errors() -> None:
    req = SuggestionRequest(species="trout", season="fall")

    def _failing_streamer(system: str, user: str):
        raise AIError("simulated network failure")
        yield  # pragma: no cover

    with pytest.raises(AIError, match="simulated network failure"):
        generate_suggestions(req, [], _failing_streamer)
