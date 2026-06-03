"""Regression tests for the Phase 5 (AI suggestions) review findings.

Each test pins one finding from the three persona-driven reviewers — the
Anthropic-API specialist, the privacy & security specialist, and the
skeptical senior engineer — so the same defect cannot resurface.

No network and no API key: the Anthropic SDK is replaced with a hand-built
fake module (`make_fake_anthropic`) that lets us exercise `anthropic_streamer`'s
error-mapping and truncation paths, which were previously untested.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from flytie.ai.suggest import (
    AIError,
    SuggestionRequest,
    SuggestionResult,
    anthropic_streamer,
    build_prompt,
    generate_suggestions,
    parse_suggestions,
)
from flytie.cli import app
from flytie.core.dto import MaterialLineDTO, PatternDTO, PatternVersionDTO

# --- helpers -----------------------------------------------------------------


def _pattern(name: str, hook: str = "14", materials: list[str] | None = None) -> PatternDTO:
    now = datetime(2026, 1, 1)
    version = PatternVersionDTO(
        version_number=1,
        hook_size=hook,
        created_at=now,
        materials=[MaterialLineDTO(canonical_name=m, category="other") for m in (materials or [])],
    )
    return PatternDTO(id=1, name=name, created_at=now, updated_at=now, current_version=version)


def _fake_streamer(chunks: list[str]):
    def _stream(system: str, user: str) -> Iterator[str]:
        yield from chunks

    return _stream


# --- a fake `anthropic` SDK module -------------------------------------------


class FakeAnthropicError(Exception):
    """Stands in for `anthropic.AnthropicError`."""


class FakeAPIError(FakeAnthropicError):
    """Stands in for `anthropic.APIError`."""


class FakeAPIStatusError(FakeAPIError):
    """Stands in for `anthropic.APIStatusError` — carries an HTTP status_code."""

    def __init__(self, message: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class FakeAPIConnectionError(FakeAPIError):
    """Stands in for `anthropic.APIConnectionError`."""


class _FakeStream:
    def __init__(self, chunks, stop_reason, raise_during):
        self._chunks = chunks
        self._stop_reason = stop_reason
        self._raise_during = raise_during

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text_stream(self):
        yield from self._chunks
        if self._raise_during is not None:
            raise self._raise_during

    def get_final_message(self):
        return SimpleNamespace(stop_reason=self._stop_reason)


def make_fake_anthropic(
    *,
    chunks: tuple[str, ...] = (),
    stop_reason: str = "end_turn",
    raise_during: BaseException | None = None,
    raise_on_stream: BaseException | None = None,
):
    """Build a stand-in for the `anthropic` module that `_require_anthropic` returns."""
    mod = SimpleNamespace()
    mod.AnthropicError = FakeAnthropicError
    mod.APIError = FakeAPIError
    mod.APIStatusError = FakeAPIStatusError
    mod.APIConnectionError = FakeAPIConnectionError

    class _Messages:
        def stream(self, **kwargs):
            if raise_on_stream is not None:
                raise raise_on_stream
            return _FakeStream(list(chunks), stop_reason, raise_during)

    class _Client:
        def __init__(self, *args, **kwargs):
            self.messages = _Messages()

    mod.Anthropic = _Client
    return mod


# --- HIGH: string-literal-aware JSON array extraction ------------------------


def test_parse_handles_brackets_inside_string_values() -> None:
    """A ']' inside a rationale must not truncate an otherwise valid array."""
    blob = '[{"name": "Caddis", "rationale": "swing it [deep] then ]lift["}]'
    suggestions = parse_suggestions(blob, set())
    assert len(suggestions) == 1
    assert suggestions[0].name == "Caddis"
    assert "]lift[" in suggestions[0].rationale


def test_parse_handles_escaped_quote_inside_string() -> None:
    blob = '[{"name": "Bob\'s \\"special\\" fly", "hook_size": "12"}]'
    suggestions = parse_suggestions(blob, set())
    assert len(suggestions) == 1
    assert suggestions[0].hook_size == "12"


def test_parse_handles_object_wrapped_array() -> None:
    """The model sometimes wraps the array: {"suggestions": [...]}. Recover it."""
    blob = '{"suggestions": [{"name": "Adams", "hook_size": "14"}]}'
    suggestions = parse_suggestions(blob, set())
    assert len(suggestions) == 1
    assert suggestions[0].name == "Adams"


def test_parse_truncated_array_returns_empty() -> None:
    """A genuinely cut-off array (no closing bracket) parses to nothing."""
    assert parse_suggestions('[{"name": "Adams"}, {"name": "Cad', set()) == []


# --- MEDIUM: count enforcement ----------------------------------------------


def test_generate_suggestions_trims_to_requested_count() -> None:
    req = SuggestionRequest(species="trout", season="fall", count=2)
    blob = json.dumps([{"name": f"Fly {i}"} for i in range(5)])
    result = generate_suggestions(req, [], _fake_streamer([blob]))
    assert len(result.suggestions) == 2
    assert [s.name for s in result.suggestions] == ["Fly 0", "Fly 1"]


# --- LOW: null-coercion and dedup -------------------------------------------


def test_parse_coerces_null_fields_to_empty_string() -> None:
    """A JSON null must not render as the literal text 'None'."""
    blob = '[{"name": "Adams", "hook_size": null, "rationale": null}]'
    suggestions = parse_suggestions(blob, set())
    assert suggestions[0].hook_size == ""
    assert suggestions[0].rationale == ""


def test_parse_dedups_by_normalized_name() -> None:
    blob = '[{"name": "Adams"}, {"name": "  adams "}, {"name": "ADAMS"}]'
    suggestions = parse_suggestions(blob, set())
    assert len(suggestions) == 1


def test_parse_is_existing_matches_case_and_whitespace_insensitively() -> None:
    """`is_existing` uses normalize_name — verify with a non-normalized name."""
    blob = '[{"name": "  PARACHUTE   Adams "}]'
    suggestions = parse_suggestions(blob, {"parachute adams"})
    assert suggestions[0].is_existing is True


# --- LOW: grounding block material cap --------------------------------------


def test_grounding_block_caps_materials_per_pattern() -> None:
    many = [f"material-{i}" for i in range(30)]
    req = SuggestionRequest(species="trout", season="fall")
    _, user = build_prompt(req, [_pattern("Big Fly", "10", many)])
    assert "material-0" in user
    assert "material-11" in user  # 12th material (index 11) still shown
    assert "material-12" not in user  # 13th is past the cap
    assert "…" in user  # truncation marker present


# --- privacy: material-level notes are never sent ---------------------------


def test_grounding_block_excludes_material_notes() -> None:
    now = datetime(2026, 1, 1)
    version = PatternVersionDTO(
        version_number=1,
        hook_size="14",
        created_at=now,
        materials=[
            MaterialLineDTO(
                canonical_name="thread",
                category="thread",
                notes="SECRET-MATERIAL-NOTE",
            )
        ],
    )
    dto = PatternDTO(id=1, name="Adams", created_at=now, updated_at=now, current_version=version)
    _, user = build_prompt(SuggestionRequest(species="trout", season="fall"), [dto])
    assert "thread" in user  # the name IS sent
    assert "SECRET-MATERIAL-NOTE" not in user  # the note is NOT


# --- streamer error mapping (previously untested) ---------------------------


def _patch_anthropic(monkeypatch: pytest.MonkeyPatch, fake) -> None:
    monkeypatch.setattr("flytie.ai.suggest._require_anthropic", lambda: fake)


def test_streamer_maps_401_to_credentials_message(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = make_fake_anthropic(raise_during=FakeAPIStatusError("nope", 401))
    _patch_anthropic(monkeypatch, fake)
    streamer = anthropic_streamer("sk-ant-key")
    with pytest.raises(AIError, match="credentials"):
        list(streamer("system", "user"))


def test_streamer_maps_429_to_rate_limit_message(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = make_fake_anthropic(raise_during=FakeAPIStatusError("slow down", 429))
    _patch_anthropic(monkeypatch, fake)
    streamer = anthropic_streamer("sk-ant-key")
    with pytest.raises(AIError, match="rate limit"):
        list(streamer("system", "user"))


def test_streamer_maps_529_to_overloaded_message(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = make_fake_anthropic(raise_during=FakeAPIStatusError("busy", 529))
    _patch_anthropic(monkeypatch, fake)
    streamer = anthropic_streamer("sk-ant-key")
    with pytest.raises(AIError, match="overloaded"):
        list(streamer("system", "user"))


def test_streamer_maps_connection_error_to_network_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = make_fake_anthropic(raise_during=FakeAPIConnectionError("dns"))
    _patch_anthropic(monkeypatch, fake)
    streamer = anthropic_streamer("sk-ant-key")
    with pytest.raises(AIError, match="network"):
        list(streamer("system", "user"))


def test_streamer_wraps_unexpected_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-Anthropic error (e.g. a transport bug) must not escape raw."""
    fake = make_fake_anthropic(raise_during=RuntimeError("something weird"))
    _patch_anthropic(monkeypatch, fake)
    streamer = anthropic_streamer("sk-ant-key")
    with pytest.raises(AIError, match="Unexpected error"):
        list(streamer("system", "user"))


def test_streamer_detects_max_tokens_truncation(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = make_fake_anthropic(chunks=('[{"name":', '"Adams"}]'), stop_reason="max_tokens")
    _patch_anthropic(monkeypatch, fake)
    streamer = anthropic_streamer("sk-ant-key")
    with pytest.raises(AIError, match="cut off"):
        list(streamer("system", "user"))


def test_streamer_error_message_never_contains_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No failure path may leak the API key into an error string."""
    secret = "sk-ant-SUPERSECRETKEY-9999"
    for exc in (
        FakeAPIStatusError("detail", 401),
        FakeAPIConnectionError("dns"),
        FakeAnthropicError("generic"),
        RuntimeError("weird"),
    ):
        fake = make_fake_anthropic(raise_during=exc)
        _patch_anthropic(monkeypatch, fake)
        streamer = anthropic_streamer(secret)
        with pytest.raises(AIError) as excinfo:
            list(streamer("system", "user"))
        assert secret not in str(excinfo.value)


def test_streamer_happy_path_yields_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = make_fake_anthropic(chunks=("hello ", "world"), stop_reason="end_turn")
    _patch_anthropic(monkeypatch, fake)
    streamer = anthropic_streamer("sk-ant-key")
    assert "".join(streamer("system", "user")) == "hello world"


# --- CLI: streaming wiring and Ctrl-C handling ------------------------------


def _init(runner: CliRunner) -> None:
    assert runner.invoke(app, ["init"]).exit_code == 0


def test_cli_suggest_wires_on_chunk_callback(
    env_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI must pass a real `on_chunk` callback so streaming is live."""
    captured: dict[str, object] = {}

    def _fake_generate(request, grounding, streamer, on_chunk=None):
        captured["on_chunk"] = on_chunk
        if on_chunk is not None:
            on_chunk("a chunk")
        return SuggestionResult(request=request, suggestions=[], raw_text="[]")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr("flytie.ai.anthropic_streamer", lambda *a, **k: _fake_streamer([]))
    monkeypatch.setattr("flytie.ai.generate_suggestions", _fake_generate)
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(app, ["suggest", "--species", "trout", "--season", "fall"])
    assert r.exit_code == 0, r.stdout + r.stderr
    assert callable(captured["on_chunk"])


def test_cli_suggest_handles_keyboard_interrupt(
    env_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_generate(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr("flytie.ai.anthropic_streamer", lambda *a, **k: _fake_streamer([]))
    monkeypatch.setattr("flytie.ai.generate_suggestions", _fake_generate)
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(app, ["suggest", "--species", "trout", "--season", "fall"])
    assert r.exit_code == 130
    assert "Traceback" not in (r.stdout + r.stderr)


def test_cli_suggest_prints_data_disclosure_notice(
    env_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The user must be told what leaves their machine before the API call."""
    sample = '[{"name": "Parachute Adams", "hook_size": "14"}]'
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr("flytie.ai.anthropic_streamer", lambda *a, **k: _fake_streamer([sample]))
    runner = CliRunner()
    _init(runner)
    runner.invoke(
        app,
        [
            "add",
            "Parachute Adams",
            "--hook",
            "14",
            "-s",
            "rainbow trout",
            "-m",
            "grizzly hackle,hackle,1,feather",
        ],
    )
    r = runner.invoke(app, ["suggest", "--species", "rainbow trout", "--season", "fall"])
    assert r.exit_code == 0, r.stdout + r.stderr
    assert "Anthropic API" in r.stdout
    assert "never sent" in r.stdout
