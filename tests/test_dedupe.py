"""Tests for flytie material dedupe — candidate discovery and CLI interaction.

Covers: Levenshtein ratio, Jaccard similarity, combined score,
find_duplicate_candidates (threshold, sorting, counts), and the
``flytie material dedupe`` CLI command (dry-run, interactive merge,
skip, quit).
"""

from __future__ import annotations

from typer.testing import CliRunner

from flytie.cli import app
from flytie.core.dedupe import (
    combined_similarity,
    find_duplicate_candidates,
    jaccard_similarity,
    levenshtein_ratio,
)
from flytie.core.dto import PatternInput
from flytie.core.patterns import create_pattern
from flytie.models import Material

# ===========================================================================
# Algorithm unit tests
# ===========================================================================


class TestLevenshteinRatio:
    def test_identical_strings(self) -> None:
        assert levenshtein_ratio("elk hair", "elk hair") == 1.0

    def test_completely_different(self) -> None:
        assert levenshtein_ratio("abc", "xyz") == 0.0

    def test_empty_strings(self) -> None:
        assert levenshtein_ratio("", "") == 1.0

    def test_one_empty(self) -> None:
        assert levenshtein_ratio("abc", "") == 0.0
        assert levenshtein_ratio("", "abc") == 0.0

    def test_one_char_typo(self) -> None:
        # "elk hair" vs "elk hare" — 2 subs (i→r, r→e) out of 8 chars = 0.75
        ratio = levenshtein_ratio("elk hair", "elk hare")
        assert ratio == 0.75

    def test_symmetry(self) -> None:
        assert levenshtein_ratio("abc", "ab") == levenshtein_ratio("ab", "abc")

    def test_single_characters(self) -> None:
        assert levenshtein_ratio("a", "b") == 0.0
        assert levenshtein_ratio("a", "a") == 1.0


class TestJaccardSimilarity:
    def test_identical_tokens(self) -> None:
        assert jaccard_similarity("elk hair", "elk hair") == 1.0

    def test_reordered_tokens(self) -> None:
        assert jaccard_similarity("dry fly hook", "hook dry fly") == 1.0

    def test_no_overlap(self) -> None:
        assert jaccard_similarity("copper wire", "elk hair") == 0.0

    def test_partial_overlap(self) -> None:
        # {"elk", "hair"} vs {"elk", "hare"} — intersection {"elk"}, union 3
        score = jaccard_similarity("elk hair", "elk hare")
        assert abs(score - 1 / 3) < 0.01

    def test_empty_strings(self) -> None:
        assert jaccard_similarity("", "") == 1.0


class TestCombinedSimilarity:
    def test_takes_max(self) -> None:
        # Reordered tokens: Jaccard=1.0, Levenshtein < 1.0 → combined=1.0
        assert combined_similarity("dry fly hook", "hook dry fly") == 1.0

    def test_typo_caught_by_levenshtein(self) -> None:
        # "elk hair" vs "elk hare" — Levenshtein is high, Jaccard is low
        score = combined_similarity("elk hair", "elk hare")
        lev = levenshtein_ratio("elk hair", "elk hare")
        jac = jaccard_similarity("elk hair", "elk hare")
        assert score == max(lev, jac)
        assert score == lev  # Levenshtein wins for typos


# ===========================================================================
# Candidate discovery (core)
# ===========================================================================


class TestFindDuplicateCandidates:
    def test_no_materials_returns_empty(self, session) -> None:
        assert find_duplicate_candidates(session) == []

    def test_single_material_returns_empty(self, session) -> None:
        session.add(Material(canonical_name="elk hair", category="hackle"))
        session.flush()
        assert find_duplicate_candidates(session) == []

    def test_similar_pair_found(self, session) -> None:
        session.add(Material(canonical_name="elk hair", category="hackle"))
        session.add(Material(canonical_name="elk hare", category="hackle"))
        session.flush()
        candidates = find_duplicate_candidates(session, threshold=0.5)
        assert len(candidates) == 1
        assert {candidates[0].name_a, candidates[0].name_b} == {"elk hair", "elk hare"}

    def test_dissimilar_pair_filtered(self, session) -> None:
        session.add(Material(canonical_name="elk hair", category="hackle"))
        session.add(Material(canonical_name="copper wire", category="flash"))
        session.flush()
        assert find_duplicate_candidates(session, threshold=0.5) == []

    def test_sorted_by_score_descending(self, session) -> None:
        session.add(Material(canonical_name="elk hair", category="hackle"))
        session.add(Material(canonical_name="elk hare", category="hackle"))  # very similar
        session.add(Material(canonical_name="elk fur", category="hackle"))  # less similar
        session.flush()
        candidates = find_duplicate_candidates(session, threshold=0.3)
        assert len(candidates) >= 2
        scores = [c.score for c in candidates]
        assert scores == sorted(scores, reverse=True)

    def test_threshold_filtering(self, session) -> None:
        session.add(Material(canonical_name="elk hair", category="hackle"))
        session.add(Material(canonical_name="elk hare", category="hackle"))
        session.flush()
        # Very high threshold should exclude even similar pairs
        assert find_duplicate_candidates(session, threshold=0.99) == []

    def test_pattern_counts(self, session) -> None:
        """Count reflects the number of active patterns using each material."""
        create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[{"canonical_name": "elk hair", "category": "hackle"}],
            ),
        )
        create_pattern(
            session,
            PatternInput(
                name="Elk Hair Caddis",
                hook_size="16",
                materials=[{"canonical_name": "elk hair", "category": "hackle"}],
            ),
        )
        # Add a similar-but-different material with no patterns
        session.add(Material(canonical_name="elk hare", category="hackle"))
        session.flush()

        candidates = find_duplicate_candidates(session, threshold=0.5)
        assert len(candidates) == 1
        c = candidates[0]
        # "elk hair" is used by 2 patterns, "elk hare" by 0
        if c.name_a == "elk hair":
            assert c.count_a == 2
            assert c.count_b == 0
        else:
            assert c.count_a == 0
            assert c.count_b == 2

    def test_deleted_patterns_not_counted(self, session) -> None:
        """Deleted patterns shouldn't inflate the count."""
        from flytie.core.patterns import soft_delete_pattern

        create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[{"canonical_name": "elk hair", "category": "hackle"}],
            ),
        )
        soft_delete_pattern(session, "Adams")
        session.add(Material(canonical_name="elk hare", category="hackle"))
        session.flush()

        candidates = find_duplicate_candidates(session, threshold=0.5)
        assert len(candidates) == 1
        # Both should show 0 active patterns
        assert candidates[0].count_a == 0
        assert candidates[0].count_b == 0


# ===========================================================================
# CLI tests
# ===========================================================================


def _add_pattern(
    runner: CliRunner,
    name: str,
    hook: str = "14",
    *,
    materials: list[str] | None = None,
) -> None:
    args = ["add", name, "--hook", hook]
    for m in materials or ["thread,thread,1,spool"]:
        args += ["--material", m]
    r = runner.invoke(app, args)
    assert r.exit_code == 0, r.stdout


class TestDedupeCLI:
    def test_no_candidates(self, env_dirs) -> None:
        runner = CliRunner()
        runner.invoke(app, ["init"])
        _add_pattern(runner, "Adams", materials=["elk hair,hackle"])
        r = runner.invoke(app, ["material", "dedupe"])
        assert r.exit_code == 0
        assert "No duplicate candidates" in r.stdout

    def test_dry_run_lists_candidates(self, env_dirs) -> None:
        runner = CliRunner()
        runner.invoke(app, ["init"])
        _add_pattern(runner, "Adams", materials=["elk hair,hackle"])
        _add_pattern(runner, "Caddis", materials=["elk hare,hackle"])
        r = runner.invoke(app, ["material", "dedupe", "--dry-run"])
        assert r.exit_code == 0
        assert "elk hair" in r.stdout
        assert "elk hare" in r.stdout
        assert "Candidate" in r.stdout

    def test_interactive_merge_keep_1(self, env_dirs) -> None:
        runner = CliRunner()
        runner.invoke(app, ["init"])
        _add_pattern(runner, "Adams", materials=["elk hair,hackle"])
        _add_pattern(runner, "Caddis", materials=["elk hare,hackle"])
        r = runner.invoke(app, ["material", "dedupe"], input="1\n")
        assert r.exit_code == 0
        assert "Merged" in r.stdout

    def test_interactive_merge_keep_2(self, env_dirs) -> None:
        runner = CliRunner()
        runner.invoke(app, ["init"])
        _add_pattern(runner, "Adams", materials=["elk hair,hackle"])
        _add_pattern(runner, "Caddis", materials=["elk hare,hackle"])
        r = runner.invoke(app, ["material", "dedupe"], input="2\n")
        assert r.exit_code == 0
        assert "Merged" in r.stdout

    def test_interactive_skip(self, env_dirs) -> None:
        runner = CliRunner()
        runner.invoke(app, ["init"])
        _add_pattern(runner, "Adams", materials=["elk hair,hackle"])
        _add_pattern(runner, "Caddis", materials=["elk hare,hackle"])
        r = runner.invoke(app, ["material", "dedupe"], input="skip\n")
        assert r.exit_code == 0
        assert "Merged" not in r.stdout

    def test_interactive_quit(self, env_dirs) -> None:
        runner = CliRunner()
        runner.invoke(app, ["init"])
        _add_pattern(runner, "Adams", materials=["elk hair,hackle"])
        _add_pattern(runner, "Caddis", materials=["elk hare,hackle"])
        r = runner.invoke(app, ["material", "dedupe"], input="quit\n")
        assert r.exit_code == 0
        assert "Stopped" in r.stdout

    def test_threshold_flag(self, env_dirs) -> None:
        runner = CliRunner()
        runner.invoke(app, ["init"])
        _add_pattern(runner, "Adams", materials=["elk hair,hackle"])
        _add_pattern(runner, "Caddis", materials=["elk hare,hackle"])
        # Very high threshold — no candidates
        r = runner.invoke(app, ["material", "dedupe", "--threshold", "0.99"])
        assert r.exit_code == 0
        assert "No duplicate candidates" in r.stdout

    def test_merge_actually_removes_material(self, env_dirs) -> None:
        """After merging, the source material should no longer appear in list."""
        runner = CliRunner()
        runner.invoke(app, ["init"])
        _add_pattern(runner, "Adams", materials=["elk hair,hackle"])
        _add_pattern(runner, "Caddis", materials=["elk hare,hackle"])
        runner.invoke(app, ["material", "dedupe"], input="1\n")
        # The kept material should still exist; the merged-away one should not
        r = runner.invoke(app, ["view", "Caddis"])
        assert r.exit_code == 0
        # The pattern should now reference the kept name
        assert "elk hair" in r.stdout.lower()

    def test_unit_mismatch_warns_about_discarded_quantity(self, env_dirs) -> None:
        """Review fix C: merging materials with different units warns about discarded qty.

        Reviewer: data-integrity specialist (HIGH).
        """
        runner = CliRunner()
        runner.invoke(app, ["init"])
        # One pattern with BOTH similar materials (different units) — triggers
        # the duplicate-within-version path in merge_materials.
        _add_pattern(
            runner,
            "Adams",
            materials=["copper wire,flash,2,spool", "copper wir,flash,3,feet"],
        )
        r = runner.invoke(app, ["material", "dedupe", "--threshold", "0.5"], input="1\n")
        assert r.exit_code == 0
        assert "Merged" in r.stdout
        assert "discarded quantity" in r.stdout
        # "units differ" is also in the warning but wraps at COLUMNS=80,
        # so we check a shorter fragment that stays on one line.
        assert "differ" in r.stdout

    def test_stale_candidate_skipped_after_merge(self, env_dirs) -> None:
        """Review fix B: a candidate referencing an already-merged material is skipped.

        Reviewer: skeptical-senior-engineer, data-integrity specialist (MEDIUM).
        """
        runner = CliRunner()
        runner.invoke(app, ["init"])
        # Three similar materials: merging A→B should cause the A-C pair to be
        # silently skipped rather than producing a confusing "Merge failed" error.
        _add_pattern(runner, "P1", materials=["elk hair,hackle"])
        _add_pattern(runner, "P2", materials=["elk hare,hackle"])
        _add_pattern(runner, "P3", materials=["elk har,hackle"])
        # Merge first pair (keep 1 = "elk hair"), then skip for remaining.
        r = runner.invoke(app, ["material", "dedupe", "--threshold", "0.5"], input="1\nskip\n")
        assert r.exit_code == 0
        # Should NOT see "Merge failed" — the stale pair is skipped silently.
        assert "Merge failed" not in r.stdout
