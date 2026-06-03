"""AI pattern suggestions via the Anthropic Claude API.

Design notes
------------
The network call is isolated behind a `Streamer` seam — a callable that takes
the system and user prompt strings and yields text chunks. The real
implementation (`anthropic_streamer`) wraps the Anthropic SDK; tests inject a
fake streamer that replays canned chunks, so no network or API key is needed
in CI.

Prompt construction (`build_prompt`) and response parsing (`parse_suggestions`)
are pure functions, independently testable.

Privacy: only pattern names, hook sizes, and material names from the local DB
are sent as grounding context — never instructions, notes, or the full
database. The API key is read only from `ANTHROPIC_API_KEY` and never logged
or persisted.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterator

from pydantic import BaseModel, Field

from flytie.core.dto import PatternDTO
from flytie.models import normalize_name

# The model string is a single constant so it's easy to bump.
DEFAULT_MODEL = "claude-sonnet-4-6"

# Cap how many of the user's patterns we send as grounding context, to bound
# token cost and keep the request small.
MAX_GROUNDING_PATTERNS = 40

# Cap materials listed per pattern in the grounding block — a pattern with
# dozens of materials would otherwise produce one enormous line.
MAX_MATERIALS_PER_PATTERN = 12

# Output token budget. Large enough that a full array of up to 10 detailed
# suggestions is not truncated mid-object (truncation would make the JSON
# unparseable). Truncation is also detected explicitly via `stop_reason`.
MAX_OUTPUT_TOKENS = 4096

# A Streamer takes (system_prompt, user_prompt) and yields response text chunks.
Streamer = Callable[[str, str], Iterator[str]]


class AIDependencyError(RuntimeError):
    """Raised when the optional `ai` extra (the `anthropic` SDK) is not installed."""


class AIError(RuntimeError):
    """Raised for runtime AI failures: missing key, network/auth errors, bad output."""


# --- DTOs --------------------------------------------------------------------


class SuggestionRequest(BaseModel):
    species: str
    season: str
    water: str | None = None
    conditions: str | None = None
    count: int = 3


class Suggestion(BaseModel):
    name: str
    hook_size: str = ""
    key_materials: list[str] = Field(default_factory=list)
    rationale: str = ""
    # True when this fly already exists in the user's library.
    is_existing: bool = False


class SuggestionResult(BaseModel):
    request: SuggestionRequest
    suggestions: list[Suggestion] = Field(default_factory=list)
    # The model's raw output, kept so the CLI can fall back to showing it
    # verbatim if structured parsing fails.
    raw_text: str = ""


# --- API key -----------------------------------------------------------------


def resolve_api_key() -> str:
    """Return the Anthropic API key from the environment, or raise `AIError`.

    The key is read only from `ANTHROPIC_API_KEY` — never from the config file
    or any other on-disk location.
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise AIError(
            "No Anthropic API key found. Set the ANTHROPIC_API_KEY environment "
            "variable:\n  export ANTHROPIC_API_KEY=sk-ant-...\n"
            "flytie never stores the key on disk."
        )
    return key


# --- prompt construction (pure) ----------------------------------------------


def _grounding_block(patterns: list[PatternDTO]) -> str:
    """Render the user's patterns as a compact context block.

    Only name, hook size, and material names are included — deliberately not
    instructions or notes, to minimize what's sent to the API. Materials are
    capped per pattern so one densely-specified fly can't bloat the request.
    """
    if not patterns:
        return "(the user's pattern library is empty)"
    lines: list[str] = []
    for p in patterns[:MAX_GROUNDING_PATTERNS]:
        v = p.current_version
        hook = v.hook_size if v else "?"
        names = [m.canonical_name for m in v.materials] if v else []
        materials = ", ".join(names[:MAX_MATERIALS_PER_PATTERN])
        line = f"- {p.name} (hook {hook})"
        if materials:
            line += f" — materials: {materials}"
            if len(names) > MAX_MATERIALS_PER_PATTERN:
                line += ", …"
        lines.append(line)
    return "\n".join(lines)


def build_prompt(request: SuggestionRequest, grounding: list[PatternDTO]) -> tuple[str, str]:
    """Return the (system_prompt, user_prompt) pair for a suggestion request."""
    system = (
        "You are an expert fly fishing guide and fly tier helping someone choose "
        "flies to tie. You will be given a target species, a season, optionally a "
        "water and water conditions, and a list of patterns already in the user's "
        "tying library.\n\n"
        "Recommend flies that suit the conditions. Prefer patterns the user "
        "already has when they fit; you may also suggest new patterns.\n\n"
        "Respond with ONLY a JSON array — no prose before or after, no code "
        "fences. Each array element is an object with exactly these keys:\n"
        '  "name": string — the fly pattern name\n'
        '  "hook_size": string — e.g. "14" or "12-16"\n'
        '  "key_materials": array of strings — a few signature materials\n'
        '  "rationale": string — one sentence on why it fits the conditions\n'
    )
    parts = [
        f"Target species: {request.species}",
        f"Season: {request.season}",
    ]
    if request.water:
        parts.append(f"Water: {request.water}")
    if request.conditions:
        parts.append(f"Water conditions: {request.conditions}")
    parts.append(f"Number of flies to recommend: {request.count}")
    parts.append("")
    parts.append("The user's existing pattern library:")
    parts.append(_grounding_block(grounding))
    parts.append("")
    parts.append(f"Recommend {request.count} flies as a JSON array following the schema above.")
    return system, "\n".join(parts)


# --- response parsing (pure) -------------------------------------------------


def _clean_str(value: object) -> str:
    """Coerce a JSON scalar to a stripped string; None/missing becomes ''.

    Without this, a JSON ``null`` reaches ``str()`` and renders as the literal
    text ``"None"`` in the CLI.
    """
    if value is None:
        return ""
    return str(value).strip()


def _extract_json_array(text: str) -> str | None:
    """Pull the first top-level JSON array substring out of arbitrary text.

    The scanner is string-literal aware: brackets that appear *inside* a JSON
    string value (e.g. a rationale containing "[NEW]") do not affect nesting
    depth, so a valid array is not truncated at the wrong byte.
    """
    stripped = text.strip()
    # Strip a ```json ... ``` or ``` ... ``` fence if present.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    start = stripped.find("[")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(stripped)):
        ch = stripped[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return stripped[start : i + 1]
    return None


def parse_suggestions(raw_text: str, library_names: set[str]) -> list[Suggestion]:
    """Parse the model's raw output into `Suggestion` objects.

    `library_names` is the set of normalized pattern names already in the user's
    library; matching suggestions are flagged `is_existing=True`. Returns an
    empty list if the output can't be parsed as the expected JSON array.
    Duplicate suggestions (same normalized name) are collapsed to the first.
    """
    blob = _extract_json_array(raw_text)
    if blob is None:
        return []
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    suggestions: list[Suggestion] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        name = _clean_str(item.get("name"))
        if not name:
            continue
        key = normalize_name(name)
        if key in seen:
            continue
        seen.add(key)
        raw_materials = item.get("key_materials", [])
        materials = (
            [_clean_str(m) for m in raw_materials if _clean_str(m)]
            if isinstance(raw_materials, list)
            else []
        )
        suggestions.append(
            Suggestion(
                name=name,
                hook_size=_clean_str(item.get("hook_size")),
                key_materials=materials,
                rationale=_clean_str(item.get("rationale")),
                is_existing=key in library_names,
            )
        )
    return suggestions


# --- the streamer seam -------------------------------------------------------


def _require_anthropic() -> object:
    """Lazy-import the Anthropic SDK, mapping a missing install to a typed error."""
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise AIDependencyError(
            "AI suggestions need the optional 'ai' extra. Install with: pip install 'flytie[ai]'"
        ) from exc
    return anthropic


def _status_error_message(exc: object) -> str:
    """Map an Anthropic `APIStatusError` to an actionable message by HTTP code.

    Crucially, this never interpolates the raw exception (which can carry
    request metadata) and never touches the API key.
    """
    code = getattr(exc, "status_code", None)
    if code in (401, 403):
        return (
            f"The Anthropic API rejected your credentials (HTTP {code}). "
            "Check that ANTHROPIC_API_KEY is set to a valid key."
        )
    if code == 429:
        return "The Anthropic API rate limit was exceeded (HTTP 429). Wait a moment and try again."
    if code == 529:
        return "The Anthropic API is temporarily overloaded (HTTP 529). Please try again shortly."
    return (
        f"The Anthropic API rejected the request (HTTP {code}). "
        "Check that your ANTHROPIC_API_KEY is valid and has available credit."
    )


def anthropic_streamer(api_key: str, model: str = DEFAULT_MODEL) -> Streamer:
    """Build a real `Streamer` backed by the Anthropic API.

    Every failure mode — auth, rate limit, overload, network, truncation, and
    any unexpected error — is translated into `AIError` so the CLI never shows
    a raw SDK traceback and the API key never reaches an error string.
    """
    anthropic = _require_anthropic()

    def _stream(system: str, user: str) -> Iterator[str]:
        client = anthropic.Anthropic(api_key=api_key)  # type: ignore[attr-defined]
        try:
            with client.messages.stream(
                model=model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            ) as stream:
                yield from stream.text_stream
                final = stream.get_final_message()
                if getattr(final, "stop_reason", None) == "max_tokens":
                    raise AIError(
                        "Claude's response was cut off before it finished "
                        "(it hit the output length limit). Try again, or "
                        "request fewer flies with a smaller --n value."
                    )
        except AIError:
            raise
        except anthropic.APIStatusError as exc:  # type: ignore[attr-defined]
            raise AIError(_status_error_message(exc)) from exc
        except anthropic.APIConnectionError as exc:  # type: ignore[attr-defined]
            raise AIError(
                "Could not reach the Anthropic API — check your network connection."
            ) from exc
        except anthropic.AnthropicError as exc:  # type: ignore[attr-defined]
            raise AIError("The Anthropic API request failed. Please try again.") from exc
        except Exception as exc:
            # Defensive catch-all: no unexpected error (transport bug, malformed
            # SSE event, etc.) may escape as a raw traceback.
            raise AIError(
                "Unexpected error while talking to the Anthropic API. Please try again."
            ) from exc

    return _stream


# --- orchestration -----------------------------------------------------------


def generate_suggestions(
    request: SuggestionRequest,
    grounding: list[PatternDTO],
    streamer: Streamer,
    on_chunk: Callable[[str], None] | None = None,
) -> SuggestionResult:
    """Run a suggestion request end-to-end against the given streamer.

    `on_chunk`, if supplied, is called with each text chunk as it arrives —
    the CLI uses it to drive a live streaming-progress display.

    The parsed result is trimmed to `request.count`: the model is *asked* for
    that many flies but may return more, and the user asked for a specific
    number.
    """
    system, user = build_prompt(request, grounding)
    chunks: list[str] = []
    for piece in streamer(system, user):
        chunks.append(piece)
        if on_chunk is not None:
            on_chunk(piece)
    raw = "".join(chunks)
    library_names = {normalize_name(p.name) for p in grounding}
    suggestions = parse_suggestions(raw, library_names)[: request.count]
    return SuggestionResult(request=request, suggestions=suggestions, raw_text=raw)
