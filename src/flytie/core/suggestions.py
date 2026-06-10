"""Persist and retrieve AI suggestion results.

The most recent ``flytie suggest`` run is saved to a JSON file in the data
directory so that ``flytie add --from-suggestion <n>`` can reference a
suggestion by its display index without re-querying the API.

Only the last run is kept -- a new ``suggest`` call overwrites the file.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flytie.ai.suggest import Suggestion, SuggestionResult
from flytie.config import Settings

SUGGESTIONS_FILENAME = "last_suggestions.json"


class NoSuggestionsError(RuntimeError):
    """No saved suggestions found (user hasn't run ``suggest`` yet)."""


class SuggestionIndexError(RuntimeError):
    """The requested suggestion index is out of range."""


def _suggestions_path(settings: Settings) -> Path:
    return settings.data_dir / SUGGESTIONS_FILENAME


def save_suggestions(settings: Settings, result: SuggestionResult) -> Path:
    """Write suggestion results to ``{data_dir}/last_suggestions.json``.

    Uses atomic tmp + rename so a crash never leaves a corrupt file.
    Returns the path written.
    """
    data: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request": result.request.model_dump(),
        "suggestions": [s.model_dump() for s in result.suggestions],
    }
    path = _suggestions_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return path


def load_suggestions(settings: Settings) -> list[Suggestion]:
    """Read saved suggestions from the last ``suggest`` run.

    Raises :class:`NoSuggestionsError` if no file exists or it cannot be parsed.
    """
    path = _suggestions_path(settings)
    if not path.exists():
        raise NoSuggestionsError(
            "No saved suggestions found. Run `flytie suggest` first, "
            "then use `flytie add --from-suggestion <n>`."
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [Suggestion(**s) for s in raw["suggestions"]]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise NoSuggestionsError(
            f"Could not read saved suggestions from {path} -- the file may be "
            "corrupt. Run `flytie suggest` again."
        ) from exc


def get_suggestion(settings: Settings, index: int) -> Suggestion:
    """Return the suggestion at 1-based *index*.

    Raises :class:`SuggestionIndexError` if the index is out of range.
    """
    suggestions = load_suggestions(settings)
    if index < 1 or index > len(suggestions):
        raise SuggestionIndexError(
            f"Suggestion #{index} does not exist. "
            f"The last `suggest` run returned {len(suggestions)} suggestion(s) "
            f"(valid range: 1-{len(suggestions)})."
        )
    return suggestions[index - 1]
