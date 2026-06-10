"""Duplicate material candidate discovery.

Scans the materials table for likely duplicates using a combination of
Levenshtein edit distance and Jaccard token overlap.  Returns ranked
candidates for the user to confirm; confirmed pairs are delegated to
:func:`~flytie.core.patterns.merge_materials` by the CLI layer.

No side effects — this module only reads.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from flytie.models import Material, Pattern, PatternMaterial, PatternVersion

# ---------------------------------------------------------------------------
# Similarity algorithms
# ---------------------------------------------------------------------------


def levenshtein_ratio(a: str, b: str) -> float:
    """Normalised Levenshtein similarity in [0, 1].

    1.0 means identical; 0.0 means completely different.
    Uses the standard DP algorithm — O(n*m) time and O(min(n,m)) space.
    """
    if a == b:
        return 1.0
    len_a, len_b = len(a), len(b)
    if len_a == 0 or len_b == 0:
        return 0.0

    # Ensure the shorter string drives the inner loop (space optimisation).
    if len_a > len_b:
        a, b = b, a
        len_a, len_b = len_b, len_a

    prev: list[int] = list(range(len_a + 1))
    curr: list[int] = [0] * (len_a + 1)

    for j in range(1, len_b + 1):
        curr[0] = j
        for i in range(1, len_a + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[i] = min(
                prev[i] + 1,  # deletion
                curr[i - 1] + 1,  # insertion
                prev[i - 1] + cost,  # substitution
            )
        prev, curr = curr, prev

    distance = prev[len_a]
    max_len = max(len_a, len_b)
    return 1.0 - distance / max_len


def jaccard_similarity(a: str, b: str) -> float:
    """Token-level Jaccard similarity in [0, 1].

    Splits on whitespace (names are already normalised to lowercase with
    collapsed whitespace by :func:`~flytie.models.normalize_name`).
    """
    set_a = set(a.split())
    set_b = set(b.split())
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 1.0  # pragma: no cover - both empty handled above
    return len(set_a & set_b) / len(union)


def combined_similarity(a: str, b: str) -> float:
    """Max of Levenshtein ratio and Jaccard similarity."""
    return max(levenshtein_ratio(a, b), jaccard_similarity(a, b))


# ---------------------------------------------------------------------------
# Candidate discovery
# ---------------------------------------------------------------------------


@dataclass
class DupeCandidate:
    """A pair of materials that look like duplicates."""

    name_a: str
    name_b: str
    score: float
    count_a: int = 0
    count_b: int = 0


def find_duplicate_candidates(
    session: Session,
    *,
    threshold: float = 0.6,
) -> list[DupeCandidate]:
    """Return material pairs scoring above *threshold*, sorted by score desc.

    Each material's *count* is the number of **distinct active patterns** that
    reference it (across all versions).  This gives the user a sense of which
    name is more established in the library.
    """
    # Load all materials.
    materials: list[Material] = list(
        session.execute(select(Material).order_by(Material.canonical_name)).scalars()
    )

    if len(materials) < 2:
        return []

    # Pre-compute per-material pattern counts (active patterns only).
    # PatternMaterial -> PatternVersion -> Pattern(is_deleted=False), distinct.
    count_subq = (
        select(
            PatternMaterial.material_id,
            func.count(func.distinct(Pattern.id)).label("pat_count"),
        )
        .join(PatternVersion, PatternMaterial.pattern_version_id == PatternVersion.id)
        .join(Pattern, PatternVersion.pattern_id == Pattern.id)
        .where(Pattern.is_deleted.is_(False))
        .group_by(PatternMaterial.material_id)
    )
    counts: dict[int, int] = {row.material_id: row.pat_count for row in session.execute(count_subq)}

    # Pairwise comparison.
    candidates: list[DupeCandidate] = []
    for i, mat_a in enumerate(materials):
        for mat_b in materials[i + 1 :]:
            score = combined_similarity(mat_a.canonical_name, mat_b.canonical_name)
            if score >= threshold:
                candidates.append(
                    DupeCandidate(
                        name_a=mat_a.canonical_name,
                        name_b=mat_b.canonical_name,
                        score=score,
                        count_a=counts.get(mat_a.id, 0),
                        count_b=counts.get(mat_b.id, 0),
                    )
                )

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates
