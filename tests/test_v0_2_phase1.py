"""Tests for v0.2.0 Phase 1 features: undelete, stats, material merge.

Organized by feature with shared helpers at the top.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from flytie.cli import app
from flytie.core import patterns as patterns_repo
from flytie.core.dto import PatternInput
from flytie.models import Material

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init(runner: CliRunner) -> None:
    r = runner.invoke(app, ["init"])
    assert r.exit_code == 0, r.stdout


def _add_pattern(
    runner: CliRunner,
    name: str,
    hook: str = "14",
    *,
    tags: list[str] | None = None,
    species: list[str] | None = None,
    materials: list[str] | None = None,
) -> None:
    args = ["add", name, "--hook", hook]
    for t in tags or []:
        args += ["--tag", t]
    for s in species or []:
        args += ["--species", s]
    for m in materials or ["thread,thread,1,spool"]:
        args += ["--material", m]
    r = runner.invoke(app, args)
    assert r.exit_code == 0, r.stdout


# ===========================================================================
# FR-9 — Undelete
# ===========================================================================


class TestUndeleteCore:
    """Unit tests for undelete_pattern in core/patterns.py."""

    def test_undelete_restores_soft_deleted_pattern(self, session) -> None:
        patterns_repo.create_pattern(session, PatternInput(name="Adams", hook_size="14"))
        patterns_repo.soft_delete_pattern(session, "Adams")
        # Confirm it's gone from default queries
        with pytest.raises(patterns_repo.PatternNotFoundError):
            patterns_repo.get_pattern(session, "Adams")

        result = patterns_repo.undelete_pattern(session, "Adams")
        assert result is not None
        assert result.is_deleted is False
        # Now visible again
        p = patterns_repo.get_pattern(session, "Adams")
        assert p.name_display == "Adams"

    def test_undelete_returns_none_for_active_pattern(self, session) -> None:
        patterns_repo.create_pattern(session, PatternInput(name="Adams", hook_size="14"))
        result = patterns_repo.undelete_pattern(session, "Adams")
        assert result is None

    def test_undelete_raises_for_missing_pattern(self, session) -> None:
        with pytest.raises(patterns_repo.PatternNotFoundError):
            patterns_repo.undelete_pattern(session, "Nonexistent")

    def test_undelete_preserves_version_history(self, session) -> None:
        patterns_repo.create_pattern(session, PatternInput(name="Adams", hook_size="14"))
        patterns_repo.edit_pattern(session, "Adams", PatternInput(name="Adams", hook_size="16"))
        patterns_repo.soft_delete_pattern(session, "Adams")
        patterns_repo.undelete_pattern(session, "Adams")

        p = patterns_repo.get_pattern(session, "Adams")
        assert len(p.versions) == 2
        assert p.versions[-1].hook_size == "16"

    def test_undelete_case_insensitive(self, session) -> None:
        patterns_repo.create_pattern(session, PatternInput(name="Elk Hair Caddis", hook_size="14"))
        patterns_repo.soft_delete_pattern(session, "elk hair caddis")
        result = patterns_repo.undelete_pattern(session, "ELK HAIR CADDIS")
        assert result is not None
        assert result.name_display == "Elk Hair Caddis"


class TestUndeleteCLI:
    """CLI integration tests for flytie undelete."""

    def test_undelete_happy_path(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        _init(runner)
        _add_pattern(runner, "Adams")
        r = runner.invoke(app, ["delete", "Adams", "--yes"])
        assert r.exit_code == 0

        # Pattern gone from list
        r = runner.invoke(app, ["list"])
        assert "Adams" not in r.stdout

        # Undelete
        r = runner.invoke(app, ["undelete", "Adams"])
        assert r.exit_code == 0
        assert "Restored" in r.stdout
        assert "Adams" in r.stdout

        # Pattern back in list
        r = runner.invoke(app, ["list"])
        assert "Adams" in r.stdout

    def test_undelete_already_active(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        _init(runner)
        _add_pattern(runner, "Adams")
        r = runner.invoke(app, ["undelete", "Adams"])
        assert r.exit_code == 0
        assert "is not deleted" in r.stdout

    def test_undelete_not_found(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        _init(runner)
        r = runner.invoke(app, ["undelete", "Nonexistent"])
        assert r.exit_code == 1

    def test_undelete_after_hard_delete_fails(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        _init(runner)
        _add_pattern(runner, "Adams")
        r = runner.invoke(app, ["delete", "Adams", "--hard", "--yes"])
        assert r.exit_code == 0

        r = runner.invoke(app, ["undelete", "Adams"])
        assert r.exit_code == 1

    def test_undelete_then_redelete_cycle(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        _init(runner)
        _add_pattern(runner, "Adams")

        # delete → undelete → delete → undelete
        r = runner.invoke(app, ["delete", "Adams", "--yes"])
        assert r.exit_code == 0
        r = runner.invoke(app, ["undelete", "Adams"])
        assert r.exit_code == 0
        assert "Restored" in r.stdout
        r = runner.invoke(app, ["delete", "Adams", "--yes"])
        assert r.exit_code == 0
        r = runner.invoke(app, ["undelete", "Adams"])
        assert r.exit_code == 0
        assert "Restored" in r.stdout

        # Still visible
        r = runner.invoke(app, ["list"])
        assert "Adams" in r.stdout

    def test_undelete_versions_visible_after_restore(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        _init(runner)
        _add_pattern(runner, "Adams")
        # Create a second version
        r = runner.invoke(app, ["edit", "Adams", "--hook", "16"])
        assert r.exit_code == 0

        r = runner.invoke(app, ["delete", "Adams", "--yes"])
        assert r.exit_code == 0

        r = runner.invoke(app, ["undelete", "Adams"])
        assert r.exit_code == 0

        # Version history accessible
        r = runner.invoke(app, ["versions", "Adams"])
        assert r.exit_code == 0
        assert "v1" in r.stdout
        assert "v2" in r.stdout


# ===========================================================================
# FR-10 — Stats
# ===========================================================================


class TestStatsCore:
    """Unit tests for library_stats in core/stats.py."""

    def test_empty_library_returns_zeros(self, session) -> None:
        from flytie.core.stats import library_stats

        result = library_stats(session)
        assert result.active_patterns == 0
        assert result.total_versions == 0
        assert result.top_materials == []
        assert result.oldest is None

    def test_single_pattern_counts(self, session) -> None:
        from flytie.core.stats import library_stats

        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                tags=["dryfly"],
                species=["rainbow trout"],
                materials=[{"canonical_name": "grizzly hackle", "category": "hackle"}],
            ),
        )
        result = library_stats(session)
        assert result.active_patterns == 1
        assert result.deleted_patterns == 0
        assert result.total_versions == 1
        assert result.total_materials == 1
        assert result.total_species == 1
        assert result.total_tags == 1
        assert result.avg_versions_per_pattern == 1.0
        assert result.oldest is not None
        assert result.oldest.name == "Adams"

    def test_deleted_patterns_counted_separately(self, session) -> None:
        from flytie.core.stats import library_stats

        patterns_repo.create_pattern(session, PatternInput(name="Adams", hook_size="14"))
        patterns_repo.create_pattern(session, PatternInput(name="Woolly Bugger", hook_size="8"))
        patterns_repo.soft_delete_pattern(session, "Woolly Bugger")

        result = library_stats(session)
        assert result.active_patterns == 1
        assert result.deleted_patterns == 1

    def test_top_materials_counts_distinct_patterns(self, session) -> None:
        """A material used by 2 patterns counts as 2, not by version count."""
        from flytie.core.stats import library_stats

        hackle_mat = [{"canonical_name": "grizzly hackle", "category": "hackle"}]
        patterns_repo.create_pattern(
            session,
            PatternInput(name="Adams", hook_size="14", materials=hackle_mat),
        )
        patterns_repo.create_pattern(
            session,
            PatternInput(name="Parachute Adams", hook_size="16", materials=hackle_mat),
        )
        # Edit Adams to create a second version (same material) — should not
        # double-count the material for Adams.
        patterns_repo.edit_pattern(
            session,
            "Adams",
            PatternInput(name="Adams", hook_size="12", materials=hackle_mat),
        )

        result = library_stats(session)
        assert len(result.top_materials) == 1
        assert result.top_materials[0].name == "grizzly hackle"
        assert result.top_materials[0].count == 2  # 2 patterns, not 3 versions

    def test_top_versioned_ordering(self, session) -> None:
        from flytie.core.stats import library_stats

        patterns_repo.create_pattern(session, PatternInput(name="Adams", hook_size="14"))
        patterns_repo.edit_pattern(session, "Adams", PatternInput(name="Adams", hook_size="16"))
        patterns_repo.edit_pattern(session, "Adams", PatternInput(name="Adams", hook_size="12"))
        patterns_repo.create_pattern(session, PatternInput(name="Woolly Bugger", hook_size="8"))

        result = library_stats(session)
        assert result.top_versioned[0].name == "Adams"
        assert result.top_versioned[0].count == 3
        assert result.top_versioned[1].name == "Woolly Bugger"
        assert result.top_versioned[1].count == 1
        assert result.avg_versions_per_pattern == 2.0

    def test_deleted_pattern_excluded_from_top_lists(self, session) -> None:
        from flytie.core.stats import library_stats

        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                species=["rainbow trout"],
                materials=[{"canonical_name": "grizzly hackle", "category": "hackle"}],
            ),
        )
        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Woolly Bugger",
                hook_size="8",
                species=["rainbow trout", "brown trout"],
                materials=[
                    {"canonical_name": "marabou", "category": "tail"},
                    {"canonical_name": "grizzly hackle", "category": "hackle"},
                ],
            ),
        )
        patterns_repo.soft_delete_pattern(session, "Woolly Bugger")

        result = library_stats(session)
        # Only Adams is active
        assert result.top_materials[0].count == 1
        assert result.top_species[0].name == "rainbow trout"
        assert result.top_species[0].count == 1


class TestStatsCLI:
    """CLI integration tests for flytie stats."""

    def test_stats_empty_library(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        _init(runner)
        r = runner.invoke(app, ["stats"])
        assert r.exit_code == 0
        assert "No patterns yet" in r.stdout
        assert "flytie add" in r.stdout

    def test_stats_with_patterns(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        _init(runner)
        _add_pattern(
            runner,
            "Adams",
            tags=["dryfly", "classic"],
            species=["rainbow trout"],
            materials=["grizzly hackle,hackle,1,feather", "grey dubbing,dubbing,1,pinch"],
        )
        _add_pattern(
            runner,
            "Woolly Bugger",
            hook="8",
            tags=["streamer"],
            species=["brown trout"],
            materials=["marabou,tail,1,clump", "grizzly hackle,hackle,1,feather"],
        )

        r = runner.invoke(app, ["stats"])
        assert r.exit_code == 0
        assert "Library Stats" in r.stdout
        assert "2" in r.stdout  # 2 patterns
        assert "grizzly hackle" in r.stdout  # top material (used by both)
        assert "Adams" in r.stdout
        assert "Woolly Bugger" in r.stdout

    def test_stats_shows_deleted_count(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        _init(runner)
        _add_pattern(runner, "Adams")
        _add_pattern(runner, "Woolly Bugger", hook="8")
        runner.invoke(app, ["delete", "Woolly Bugger", "--yes"])

        r = runner.invoke(app, ["stats"])
        assert r.exit_code == 0
        assert "1 deleted" in r.stdout

    def test_stats_shows_version_info(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        _init(runner)
        _add_pattern(runner, "Adams")
        runner.invoke(app, ["edit", "Adams", "--hook", "16"])
        runner.invoke(app, ["edit", "Adams", "--hook", "12"])

        r = runner.invoke(app, ["stats"])
        assert r.exit_code == 0
        assert "3 versions" in r.stdout  # in the most-versioned list


# ===========================================================================
# FR-11 — Material Merge
# ===========================================================================


class TestMergeCore:
    """Unit tests for merge_materials in core/patterns.py."""

    def test_merge_rewrites_references(self, session) -> None:
        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[{"canonical_name": "grizzly hackle", "category": "hackle"}],
            ),
        )
        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Woolly Bugger",
                hook_size="8",
                materials=[{"canonical_name": "grizzly saddle hackle", "category": "hackle"}],
            ),
        )

        result = patterns_repo.merge_materials(session, "grizzly saddle hackle", "grizzly hackle")
        assert result.version_rows == 1
        assert "Woolly Bugger" in result.affected_patterns

        # Verify the material was rewritten on the Woolly Bugger pattern
        wb = patterns_repo.get_pattern(session, "Woolly Bugger")
        mat_names = [pm.material.canonical_name for pm in wb.current_version.materials]
        assert "grizzly hackle" in mat_names
        assert "grizzly saddle hackle" not in mat_names

    def test_merge_dry_run_makes_no_changes(self, session) -> None:
        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[{"canonical_name": "grizzly saddle hackle", "category": "hackle"}],
            ),
        )
        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Woolly Bugger",
                hook_size="8",
                materials=[{"canonical_name": "grizzly hackle", "category": "hackle"}],
            ),
        )

        result = patterns_repo.merge_materials(
            session, "grizzly saddle hackle", "grizzly hackle", dry_run=True
        )
        assert result.version_rows == 1
        assert "Adams" in result.affected_patterns

        # Source material should still exist
        mat = session.scalar(
            select(Material).where(Material.canonical_name == "grizzly saddle hackle")
        )
        assert mat is not None

    def test_merge_not_found_source(self, session) -> None:
        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[{"canonical_name": "grizzly hackle", "category": "hackle"}],
            ),
        )
        with pytest.raises(patterns_repo.MaterialNotFoundError):
            patterns_repo.merge_materials(session, "nonexistent", "grizzly hackle")

    def test_merge_not_found_target(self, session) -> None:
        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[{"canonical_name": "grizzly hackle", "category": "hackle"}],
            ),
        )
        with pytest.raises(patterns_repo.MaterialNotFoundError):
            patterns_repo.merge_materials(session, "grizzly hackle", "nonexistent")

    def test_merge_self_raises(self, session) -> None:
        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[{"canonical_name": "grizzly hackle", "category": "hackle"}],
            ),
        )
        with pytest.raises(ValueError, match="Cannot merge a material into itself"):
            patterns_repo.merge_materials(session, "grizzly hackle", "GRIZZLY HACKLE")

    def test_merge_duplicate_within_version_sums_quantities(self, session) -> None:
        """If a version has both from and to materials, merge sums quantities."""
        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[
                    {
                        "canonical_name": "grizzly hackle",
                        "category": "hackle",
                        "quantity": 2,
                        "unit": "feather",
                    },
                    {
                        "canonical_name": "grizzly saddle hackle",
                        "category": "hackle",
                        "quantity": 1,
                        "unit": "feather",
                    },
                ],
            ),
        )

        result = patterns_repo.merge_materials(session, "grizzly saddle hackle", "grizzly hackle")
        assert len(result.warnings) == 1
        assert "had both materials" in result.warnings[0]

        # Quantity should be summed
        p = patterns_repo.get_pattern(session, "Adams")
        hackle_rows = [
            pm
            for pm in p.current_version.materials
            if pm.material.canonical_name == "grizzly hackle"
        ]
        assert len(hackle_rows) == 1
        assert hackle_rows[0].quantity == 3  # 2 + 1

    def test_merge_duplicate_different_units_keeps_target(self, session) -> None:
        """If units differ, keep target row unchanged."""
        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[
                    {
                        "canonical_name": "grizzly hackle",
                        "category": "hackle",
                        "quantity": 2,
                        "unit": "feather",
                    },
                    {
                        "canonical_name": "grizzly saddle hackle",
                        "category": "hackle",
                        "quantity": 5,
                        "unit": "inch",
                    },
                ],
            ),
        )

        result = patterns_repo.merge_materials(session, "grizzly saddle hackle", "grizzly hackle")
        # Two warnings: the duplicate-within-version notice + the discarded-quantity notice
        # (Fix C in v0.2.1 added the explicit quantity-discard warning).
        assert len(result.warnings) == 2
        assert any("discarded quantity" in w for w in result.warnings)

        p = patterns_repo.get_pattern(session, "Adams")
        hackle_rows = [
            pm
            for pm in p.current_version.materials
            if pm.material.canonical_name == "grizzly hackle"
        ]
        assert len(hackle_rows) == 1
        assert hackle_rows[0].quantity == 2  # kept target, didn't sum

    def test_merge_orphan_material_no_references(self, session) -> None:
        """Merging a material used by no patterns just deletes the orphan."""
        from flytie.models import Material

        # Create two materials directly, one used, one not
        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[{"canonical_name": "grizzly hackle", "category": "hackle"}],
            ),
        )
        # Create orphan material
        orphan = Material(canonical_name="old hackle", category="hackle")
        session.add(orphan)
        session.flush()

        result = patterns_repo.merge_materials(session, "old hackle", "grizzly hackle")
        assert result.version_rows == 0
        assert result.affected_patterns == []

        # Orphan should be deleted
        assert (
            session.scalar(select(Material).where(Material.canonical_name == "old hackle")) is None
        )

    def test_merge_rewrites_historical_versions(self, session) -> None:
        """Merge rewrites ALL versions, not just the current one."""
        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[{"canonical_name": "old hackle", "category": "hackle"}],
            ),
        )
        # Edit to create v2 with the same material
        patterns_repo.edit_pattern(
            session,
            "Adams",
            PatternInput(
                name="Adams",
                hook_size="16",
                materials=[{"canonical_name": "old hackle", "category": "hackle"}],
            ),
        )
        # Create the target material via another pattern
        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Woolly Bugger",
                hook_size="8",
                materials=[{"canonical_name": "new hackle", "category": "hackle"}],
            ),
        )

        result = patterns_repo.merge_materials(session, "old hackle", "new hackle")
        assert result.version_rows == 2  # both versions rewritten

        # Expire cached ORM state so relationships reload from DB
        session.expire_all()
        p = patterns_repo.get_pattern(session, "Adams")
        for v in p.versions:
            mat_names = [pm.material.canonical_name for pm in v.materials]
            assert "new hackle" in mat_names
            assert "old hackle" not in mat_names


class TestMergeCLI:
    """CLI integration tests for flytie material merge."""

    def test_merge_happy_path(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        _init(runner)
        _add_pattern(
            runner,
            "Adams",
            materials=["grizzly hackle,hackle,1,feather"],
        )
        _add_pattern(
            runner,
            "Woolly Bugger",
            hook="8",
            materials=["grizzly saddle hackle,hackle,1,feather"],
        )

        r = runner.invoke(app, ["material", "merge", "grizzly saddle hackle", "grizzly hackle"])
        assert r.exit_code == 0
        assert "Merged" in r.stdout
        assert "1 pattern," in r.stdout

    def test_merge_dry_run(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        _init(runner)
        _add_pattern(runner, "Adams", materials=["old hackle,hackle,1,feather"])
        _add_pattern(runner, "Woolly Bugger", hook="8", materials=["new hackle,hackle,1,feather"])

        r = runner.invoke(app, ["material", "merge", "old hackle", "new hackle", "--dry-run"])
        assert r.exit_code == 0
        assert "Would merge" in r.stdout
        assert "Adams" in r.stdout

        # Verify nothing actually changed
        r = runner.invoke(app, ["view", "Adams"])
        assert "old hackle" in r.stdout

    def test_merge_not_found(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        _init(runner)
        _add_pattern(runner, "Adams", materials=["grizzly hackle,hackle,1,feather"])

        r = runner.invoke(app, ["material", "merge", "nonexistent", "grizzly hackle"])
        assert r.exit_code == 1

    def test_merge_self(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        _init(runner)
        _add_pattern(runner, "Adams", materials=["grizzly hackle,hackle,1,feather"])

        r = runner.invoke(app, ["material", "merge", "grizzly hackle", "grizzly hackle"])
        assert r.exit_code == 2
        assert "Cannot merge" in (r.stdout + r.stderr)

    def test_merge_with_duplicate_warning(self, env_dirs: tuple[Path, Path]) -> None:
        runner = CliRunner()
        _init(runner)
        _add_pattern(
            runner,
            "Adams",
            materials=[
                "grizzly hackle,hackle,2,feather",
                "grizzly saddle hackle,hackle,1,feather",
            ],
        )

        r = runner.invoke(app, ["material", "merge", "grizzly saddle hackle", "grizzly hackle"])
        assert r.exit_code == 0
        assert "Warning:" in r.stdout
        assert "had both materials" in r.stdout


# ===========================================================================
# Diff format redesign — sorted material blocks
# ===========================================================================


class TestDiffSortedBlocks:
    """Tests for the sorted-material diff format (Phase-3-deferred redesign)."""

    def test_pure_reorder_produces_no_diff(self, session) -> None:
        """Reordering materials without changing them should produce an empty diff."""
        from flytie.core import versions as versions_repo

        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[
                    {"canonical_name": "hackle", "category": "hackle"},
                    {"canonical_name": "dubbing", "category": "dubbing"},
                    {"canonical_name": "thread", "category": "thread"},
                ],
            ),
        )
        # Edit with same materials in different order
        patterns_repo.edit_pattern(
            session,
            "Adams",
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[
                    {"canonical_name": "thread", "category": "thread"},
                    {"canonical_name": "hackle", "category": "hackle"},
                    {"canonical_name": "dubbing", "category": "dubbing"},
                ],
            ),
        )
        _, _, lines = versions_repo.diff_versions(session, "Adams", 1, 2)
        assert lines == [], f"Expected empty diff for pure reorder, got: {lines}"

    def test_material_addition_still_shows_in_diff(self, session) -> None:
        """Adding a new material should appear in the diff even with sorting."""
        from flytie.core import versions as versions_repo

        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[
                    {"canonical_name": "hackle", "category": "hackle"},
                    {"canonical_name": "thread", "category": "thread"},
                ],
            ),
        )
        patterns_repo.edit_pattern(
            session,
            "Adams",
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[
                    {"canonical_name": "hackle", "category": "hackle"},
                    {"canonical_name": "dubbing", "category": "dubbing"},
                    {"canonical_name": "thread", "category": "thread"},
                ],
            ),
        )
        _, _, lines = versions_repo.diff_versions(session, "Adams", 1, 2)
        text = "\n".join(lines)
        assert "+  - dubbing" in text

    def test_material_removal_shows_in_diff(self, session) -> None:
        """Removing a material should appear in the diff."""
        from flytie.core import versions as versions_repo

        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[
                    {"canonical_name": "hackle", "category": "hackle"},
                    {"canonical_name": "dubbing", "category": "dubbing"},
                    {"canonical_name": "thread", "category": "thread"},
                ],
            ),
        )
        patterns_repo.edit_pattern(
            session,
            "Adams",
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[
                    {"canonical_name": "hackle", "category": "hackle"},
                    {"canonical_name": "thread", "category": "thread"},
                ],
            ),
        )
        _, _, lines = versions_repo.diff_versions(session, "Adams", 1, 2)
        text = "\n".join(lines)
        assert "-  - dubbing" in text

    def test_material_quantity_change_shows_in_diff(self, session) -> None:
        """Changing a material's quantity should appear in the diff."""
        from flytie.core import versions as versions_repo

        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[
                    {
                        "canonical_name": "hackle",
                        "category": "hackle",
                        "quantity": 1,
                        "unit": "feather",
                    },
                ],
            ),
        )
        patterns_repo.edit_pattern(
            session,
            "Adams",
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[
                    {
                        "canonical_name": "hackle",
                        "category": "hackle",
                        "quantity": 3,
                        "unit": "feather",
                    },
                ],
            ),
        )
        _, _, lines = versions_repo.diff_versions(session, "Adams", 1, 2)
        text = "\n".join(lines)
        assert "-  - hackle 1 feather" in text
        assert "+  - hackle 3 feather" in text


# ===========================================================================
# Review-fix regression tests (v0.2.0 Phase 1 review)
# ===========================================================================


class TestReviewFixesPhase1:
    """Regression tests for findings from the v0.2.0 Phase 1 three-reviewer pass.

    Reviewer: skeptical-senior-engineer (#1, #2), data-integrity (#M3).
    Severity: CRITICAL.
    """

    def test_stats_deleted_only_library_core(self, session) -> None:
        """library_stats returns nonzero deleted_patterns and reference-table
        totals when all patterns are deleted (not zeros across the board)."""
        from flytie.core.stats import library_stats

        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Adams",
                hook_size="14",
                materials=[{"canonical_name": "hackle", "category": "hackle"}],
            ),
        )
        patterns_repo.soft_delete_pattern(session, "Adams")

        result = library_stats(session)
        assert result.active_patterns == 0
        assert result.deleted_patterns == 1
        # Reference-table totals should reflect what exists, not zeros
        assert result.total_materials >= 1

    def test_stats_deleted_only_library_cli(self, env_dirs: tuple[Path, Path]) -> None:
        """CLI stats with only deleted patterns says 'No active patterns',
        not 'No patterns yet'."""
        runner = CliRunner()
        _init(runner)
        _add_pattern(runner, "Adams", "14")
        runner.invoke(app, ["delete", "Adams", "--yes"])

        r = runner.invoke(app, ["stats"])
        output = r.stdout + r.stderr
        assert "No active patterns" in output
        assert "1 deleted" in output
        assert "No patterns yet" not in output

    def test_stats_truly_empty_library_cli(self, env_dirs: tuple[Path, Path]) -> None:
        """CLI stats with zero patterns (active or deleted) still says
        'No patterns yet'."""
        runner = CliRunner()
        _init(runner)
        r = runner.invoke(app, ["stats"])
        assert "No patterns yet" in r.stdout

    def test_merge_self_exits_code_2(self, env_dirs: tuple[Path, Path]) -> None:
        """Self-merge is an input error — exit code 2, not 1.

        Reviewer: UX-CLI-surface (#2). Severity: HIGH.
        """
        runner = CliRunner()
        _init(runner)
        _add_pattern(runner, "Adams", "14", materials=["hackle,hackle"])
        r = runner.invoke(app, ["material", "merge", "hackle", "hackle"])
        assert r.exit_code == 2

    def test_merge_dry_run_shows_version_rows_without_affected(
        self, env_dirs: tuple[Path, Path]
    ) -> None:
        """Dry-run output always shows the version-rows line, even when
        no active patterns are affected.

        Reviewer: UX-CLI-surface (#3). Severity: HIGH.
        """
        runner = CliRunner()
        _init(runner)
        _add_pattern(runner, "Adams", "14", materials=["hackle,hackle"])
        # Delete the pattern so the merge affects zero active patterns
        runner.invoke(app, ["delete", "Adams", "--yes"])
        # Add a second material so the merge target exists
        _add_pattern(runner, "Bugger", "8", materials=["thread,thread"])
        r = runner.invoke(app, ["material", "merge", "hackle", "thread", "--dry-run"])
        output = r.stdout + r.stderr
        assert "Version rows:" in output
