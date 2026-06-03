"""AI pattern suggestions.

Importing this module does not import the `anthropic` SDK — the SDK is
lazy-loaded inside `suggest.py` so `pip install flytie` (without the `ai`
extra) still works.
"""

from flytie.ai.suggest import (
    AIDependencyError,
    AIError,
    Suggestion,
    SuggestionRequest,
    SuggestionResult,
    anthropic_streamer,
    build_prompt,
    generate_suggestions,
    parse_suggestions,
    resolve_api_key,
)

__all__ = [
    "AIDependencyError",
    "AIError",
    "Suggestion",
    "SuggestionRequest",
    "SuggestionResult",
    "anthropic_streamer",
    "build_prompt",
    "generate_suggestions",
    "parse_suggestions",
    "resolve_api_key",
]
