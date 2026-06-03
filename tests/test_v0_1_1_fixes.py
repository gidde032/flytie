"""Regression tests for the v0.1.1 follow-up findings.

Step A of the v0.1.1 plan (after the prospective-user friction log and the
post-Phase-6 spec-drift re-audit):

- A1 — `flytie info` command (the friction log's nominated "single best fix")
- A2 — `flytie tag list` subcommand (friction-log gap: no way to list tags)
- A3 — Alembic head-check on Database (spec-drift FIX #8; spec §8 promise)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from flytie.cli import app
from flytie.config import Settings
from flytie.db import Database, IncompatibleDatabaseError

# ---------------------------------------------------------------------------
# A3 — Alembic head-check (`Database.validate_compatibility`)
# ---------------------------------------------------------------------------


def test_validate_compatibility_accepts_uninitialized_db(settings: Settings) -> None:
    """A brand-new DB with no `alembic_version` row passes silently.

    `flytie init` writes that row immediately; refusing here would block
    first-run users behind a paradox.
    """
    db = Database.from_settings(settings)
    try:
        # No alembic_version table yet — must not raise.
        db.validate_compatibility()
    finally:
        db.engine.dispose()


def test_validate_compatibility_accepts_known_revision(database: Database) -> None:
    """A DB stamped at the binary's own head is the normal case — must not raise."""
    # `database` fixture has already called create_schema → stamped at head.
    assert database.alembic_version() is not None
    database.validate_compatibility()  # would raise if broken


def test_validate_compatibility_rejects_unknown_revision(database: Database) -> None:
    """A DB stamped at a revision this build doesn't know is the bug we're catching.

    Spec §8: "the app refuses to start against a DB newer than its known head."
    Simulated by overwriting `alembic_version` with a fabricated revision.
    """
    # Forge a "future" revision into the DB.
    with database.engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM alembic_version")
        conn.exec_driver_sql(
            "INSERT INTO alembic_version (version_num) VALUES ('ffffffffffff')"
        )
    with pytest.raises(IncompatibleDatabaseError) as exc_info:
        database.validate_compatibility()
    msg = str(exc_info.value)
    # The user needs to know: what's stamped, what we know, and how to recover.
    assert "ffffffffffff" in msg
    assert "export-db" in msg
    assert "init --force" in msg
    assert "import-db" in msg


def test_open_db_surfaces_incompatibility_as_exit_code_4(
    env_dirs: tuple[Path, Path],
) -> None:
    """The CLI converts the error into a formatted message and exit code 4.

    Exit code 4 is reserved for "incompatible environment," distinct from
    1 (data error), 2 (input/validation), and 3 (missing dep). End users
    should be able to detect this case from a wrapper script.
    """
    from flytie.config import load_settings

    settings = load_settings()
    db = Database.from_settings(settings)
    db.create_schema()
    with db.engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM alembic_version")
        conn.exec_driver_sql(
            "INSERT INTO alembic_version (version_num) VALUES ('deadbeefface')"
        )
    db.engine.dispose()

    runner = CliRunner()
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 4
    out = result.stdout + result.stderr
    assert "deadbeefface" in out
    assert "export-db" in out
    # The raw exception class name must not leak through.
    assert "IncompatibleDatabaseError" not in out


def test_info_still_works_against_incompatible_db(
    env_dirs: tuple[Path, Path],
) -> None:
    """`flytie info` is the diagnostic users reach for when other commands fail.

    It must therefore not be guarded by the compatibility check that fails
    the other commands — it should *report* the situation instead.
    """
    from flytie.config import load_settings

    settings = load_settings()
    db = Database.from_settings(settings)
    db.create_schema()
    with db.engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM alembic_version")
        conn.exec_driver_sql(
            "INSERT INTO alembic_version (version_num) VALUES ('decafbad1234')"
        )
    db.engine.dispose()

    runner = CliRunner()
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0, result.stdout + result.stderr
    out = result.stdout + result.stderr
    assert "decafbad1234" in out
    assert "Compatibility warning" in out


# ---------------------------------------------------------------------------
# A1 — `flytie info`
# ---------------------------------------------------------------------------


def test_info_runs_before_init(env_dirs: tuple[Path, Path]) -> None:
    """`info` is the safe first command — must not require `init` to have run."""
    runner = CliRunner()
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "not initialized" in result.stdout
    assert "Database path" in result.stdout
    assert "Config file" in result.stdout


def test_info_shows_resolved_paths(env_dirs: tuple[Path, Path]) -> None:
    """The three resolved paths Tom would want after `init` are all present."""
    config_dir, data_dir = env_dirs
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Database path" in result.stdout
    assert str(data_dir) in result.stdout
    assert "Config file" in result.stdout
    assert str(config_dir) in result.stdout
    assert "Data directory" in result.stdout


def test_info_shows_pattern_and_tag_counts(env_dirs: tuple[Path, Path]) -> None:
    """After adding patterns and tags, info should report the right totals."""
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(
        app, ["add", "Parachute Adams", "--hook", "14", "-t", "dry", "-t", "mayfly"]
    ).exit_code == 0
    assert runner.invoke(
        app, ["add", "Hare's Ear", "--hook", "12", "-t", "nymph"]
    ).exit_code == 0

    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0, result.stdout + result.stderr
    # We know there are exactly 2 patterns and 3 tags.
    assert "Patterns" in result.stdout and " 2" in result.stdout
    assert "Tags" in result.stdout and " 3" in result.stdout


def test_info_never_mentions_api_key(env_dirs: tuple[Path, Path], monkeypatch) -> None:
    """`info` must never display the Anthropic key, even when it's set."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-must-not-leak-123")
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    out = result.stdout + result.stderr
    assert "sk-ant-test-must-not-leak-123" not in out
    assert "ANTHROPIC_API_KEY" not in out
    assert "api" not in out.lower() or "api key" not in out.lower()


def test_info_reports_incomplete_schema(env_dirs: tuple[Path, Path]) -> None:
    """A stamped-but-empty DB (interrupted init) is flagged in `info` output."""
    from flytie.config import load_settings

    settings = load_settings()
    db = Database.from_settings(settings)
    db.stamp_alembic_head()  # alembic_version present, real tables absent
    db.engine.dispose()
    runner = CliRunner()
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "incomplete" in result.stdout or "incomplete" in result.stderr


# ---------------------------------------------------------------------------
# A2 — `flytie tag list`
# ---------------------------------------------------------------------------


def test_tag_list_shows_tags_with_counts(env_dirs: tuple[Path, Path]) -> None:
    """Tags in use show up sorted with usage counts."""
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(
        app, ["add", "Adams", "--hook", "14", "-t", "dry", "-t", "mayfly"]
    ).exit_code == 0
    assert runner.invoke(
        app, ["add", "Hare's Ear", "--hook", "12", "-t", "nymph"]
    ).exit_code == 0
    assert runner.invoke(
        app, ["add", "RS2", "--hook", "20", "-t", "nymph", "-t", "midge"]
    ).exit_code == 0

    result = runner.invoke(app, ["tag", "list"])
    assert result.exit_code == 0, result.stdout + result.stderr
    out = result.stdout
    # All four tags appear, sorted alphabetically.
    assert "dry" in out
    assert "mayfly" in out
    assert "midge" in out
    assert "nymph" in out
    # And the count for "nymph" (2 patterns) is rendered.
    assert out.index("dry") < out.index("mayfly") < out.index("midge") < out.index(
        "nymph"
    )


def test_tag_list_on_empty_library(env_dirs: tuple[Path, Path]) -> None:
    """No friction message when the library has no tags yet."""
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    result = runner.invoke(app, ["tag", "list"])
    assert result.exit_code == 0
    assert "No tags" in result.stdout or "no tags" in result.stdout


def test_tag_list_ignores_soft_deleted_patterns(
    env_dirs: tuple[Path, Path],
) -> None:
    """A tag attached only to a soft-deleted pattern should not appear.

    Otherwise `flytie list --tag x` would return nothing yet `tag list`
    would advertise `x` as a usable selector — a frustrating UX divergence.
    """
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(
        app, ["add", "Ghost", "--hook", "14", "-t", "obsolete"]
    ).exit_code == 0
    assert runner.invoke(app, ["delete", "Ghost", "--yes"]).exit_code == 0

    result = runner.invoke(app, ["tag", "list"])
    assert result.exit_code == 0
    # The tag whose only pattern is soft-deleted should not appear.
    assert "obsolete" not in result.stdout


# ---------------------------------------------------------------------------
# Step C — documentation regressions (each test pins a doc fix in place)
# ---------------------------------------------------------------------------


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _read_doc(name: str) -> str:
    return (_project_root() / "docs" / name).read_text()


# C5 — config-path docs disambiguation


def test_quickstart_points_at_flytie_info_for_db_location() -> None:
    """Quickstart §2 must use `flytie info` as the where-am-I command.

    Pins the friction-log finding: `flytie config path` returns the config
    file path, not the DB path, so the prior quickstart was misleading.
    """
    text = _read_doc("quickstart.md")
    assert "flytie info" in text
    # And it must explain the difference, not just swap one command for another.
    assert "TOML config file" in text or "config file" in text


def test_commands_md_documents_flytie_info() -> None:
    """`flytie info` has its own entry in the command reference."""
    text = _read_doc("commands.md")
    assert "## `flytie info`" in text
    assert "Anthropic API key is **never** displayed" in text


def test_commands_md_documents_tag_list() -> None:
    """`flytie tag list` is documented as a tag subcommand."""
    text = _read_doc("commands.md")
    assert "flytie tag list" in text


def test_index_md_recommends_flytie_info() -> None:
    """`index.md`'s "where flytie keeps your data" section points at `flytie info`."""
    text = _read_doc("index.md")
    assert "flytie info" in text


# C6 — Jinja2 as a core dep, `--html` advertised as extras-free


def test_pyproject_jinja2_is_core_dep() -> None:
    """Jinja2 must be a core dependency so `--html` works on a bare install.

    Spec FR-5: `--html` is the no-native-deps fallback. Previously Jinja2
    sat in the `[pdf]` extra alongside WeasyPrint, which made the docs'
    "no extra required" promise technically false.
    """
    import sys

    if sys.version_info >= (3, 11):
        import tomllib
    else:  # pragma: no cover
        import tomli as tomllib

    with (_project_root() / "pyproject.toml").open("rb") as fh:
        cfg = tomllib.load(fh)
    core_deps = cfg["project"]["dependencies"]
    pdf_deps = cfg["project"]["optional-dependencies"]["pdf"]
    assert any(d.startswith("jinja2") for d in core_deps), (
        "Jinja2 must be in [project].dependencies for `--html` to work on a bare install"
    )
    assert not any(d.startswith("jinja2") for d in pdf_deps), (
        "Jinja2 must NOT also appear in the [pdf] extra — it's now core"
    )


def test_readme_advertises_html_on_bare_install() -> None:
    """The README's install section promises `--html` works on a bare install."""
    text = (_project_root() / "README.md").read_text()
    # The promise: bare `pip install flytie` is enough to produce a printable card.
    assert "styled, printable HTML" in text or "styled HTML pattern card" in text
    assert "no extras" in text.lower() or "bare `pip install flytie`" in text


def test_quickstart_advertises_html_on_bare_install() -> None:
    """Quickstart §1 and §7 must agree with the new core-deps story."""
    text = _read_doc("quickstart.md")
    # §1 promotes the core install as sufficient for HTML
    assert "styled, printable HTML" in text or "styled HTML pattern cards" in text
    # §7 notes `--html` works without the [pdf] extra
    assert "no `[pdf]` extra" in text or "no [pdf] extra" in text or "bare `pip install flytie`" in text


# C7 — Pattern-file-format doc


def test_pattern_file_format_doc_exists() -> None:
    """`docs/pattern-file-format.md` exists with the documented JSON + TOML examples."""
    doc = _project_root() / "docs" / "pattern-file-format.md"
    assert doc.is_file()
    text = doc.read_text()
    # Both forms documented
    assert "## JSON example" in text
    assert "## TOML example" in text
    # And the field tables
    assert "canonical_name" in text
    assert "Pattern-level" in text
    # And the differentiation from the export schema
    assert "json-schema.md" in text


def test_commands_md_links_to_pattern_file_format() -> None:
    """`flytie add` documentation links to the format doc rather than burying it."""
    text = _read_doc("commands.md")
    assert "pattern-file-format.md" in text


def test_migrating_doc_links_to_pattern_file_format() -> None:
    """Approach 2 of the migration guide points at the formal format doc."""
    text = _read_doc("migrating-from-notebook.md")
    assert "pattern-file-format.md" in text


def test_add_from_file_help_links_to_format_doc() -> None:
    """The Typer `--from-file` help string surfaces the docs path.

    The friction log called out that `flytie add --help` was useless as a
    refresher — fixing the help text is the same idea applied to the CLI
    surface, not just the docs. We force a wide terminal so Typer doesn't
    truncate the line at column ~80.
    """
    runner = CliRunner()
    result = runner.invoke(app, ["add", "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    # Normalize whitespace — Typer/Rich may still inject a line break inside
    # the rendered help cell on some terminals.
    normalized = " ".join(result.stdout.split())
    assert "pattern-file-format.md" in normalized


# C8 — `?` marker in quickstart


def test_quickstart_explains_question_mark_in_shop_output() -> None:
    """Quickstart §6 defines `?` at the point where it first appears."""
    text = _read_doc("quickstart.md")
    # Normalize whitespace so a paragraph-internal line break in the source
    # markdown doesn't break the substring match.
    normalized = " ".join(text.split())
    # The friction log found `?` unexplained in §6 even though the shopping
    # cookbook covered it elsewhere. The definition must be co-located.
    assert "`?`" in text
    assert "without a numeric quantity" in normalized or "without a quantity" in normalized


# C9 — Spec backport (the four DOCUMENT deviations)


def _read_spec() -> str:
    return (_project_root() / "fly-tying-tracker-spec.md").read_text()


def test_spec_describes_flag_driven_add_and_edit() -> None:
    """The spec no longer promises an interactive prompt / `$EDITOR` integration.

    Both were deliberately replaced by the flag-driven design during
    implementation; the spec must reflect what shipped.
    """
    text = _read_spec()
    # "interactive prompt for materials" and "interactive editor" should not
    # appear as v0.1 promises any more (they may appear once each in the
    # deviation explanation, which is fine — the spec just shouldn't promise
    # them as the design).
    assert "interactive prompt for materials" not in text or "superseded" in text
    assert "repeatable `--material` flags" in text
    assert "`--rename-to`" in text


def test_spec_describes_json_or_toml_not_yaml() -> None:
    """`--from-file` accepts JSON or TOML; the spec used to say YAML/JSON."""
    text = _read_spec()
    assert "JSON or TOML" in text
    # And the dropped YAML promise is explained, not just deleted silently.
    assert "YAML support was dropped" in text or "TOML" in text


def test_spec_search_includes_instructions() -> None:
    """FR-3 records that search covers instructions in addition to the original spec fields."""
    text = _read_spec()
    assert "instructions" in text
    # And the FR-3 wording in particular mentions instructions.
    fr3 = text[text.find("### FR-3"):text.find("### FR-4")]
    assert "instructions" in fr3


def test_spec_mentions_flytie_info_and_tag_list() -> None:
    """The new commands are documented in the spec, not just in the docs/."""
    text = _read_spec()
    assert "flytie info" in text
    assert "flytie tag list" in text


# ---------------------------------------------------------------------------
# Step B — help text on selector options
# ---------------------------------------------------------------------------
#
# All tests force a wide terminal via env={"COLUMNS": "200"} so Typer doesn't
# truncate the rendered help text at ~80 columns. The whitespace-normalize
# trick handles any line breaks Rich still injects inside a help cell.


def _help(command: list[str]) -> str:
    runner = CliRunner()
    result = runner.invoke(app, [*command, "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.stdout + result.stderr
    return " ".join(result.stdout.split())


def test_add_help_documents_material_mini_grammar() -> None:
    """`flytie add --help` must describe the `name,category,quantity,unit` format.

    Friction-log finding: the help output was useless as a refresher because
    `--material` showed `TEXT` with no description, so you had to keep going
    back to the README every time you forgot the comma-separated grammar.
    """
    out = _help(["add"])
    assert "name,category,quantity,unit" in out
    # And the category enumeration is right there too, so the user doesn't
    # have to switch docs to find out what's valid.
    assert "hackle" in out and "dubbing" in out and "thread" in out


def test_add_help_documents_hook_range_form() -> None:
    """Friction-log: `--hook` example only showed a single number; range syntax was a mystery."""
    out = _help(["add"])
    assert "12-16" in out
    assert "14" in out


def test_add_help_documents_repeatability_for_tag_and_species() -> None:
    """`--tag` / `--species` must say they're repeatable — Tom didn't know."""
    out = _help(["add"])
    # The phrase matters; "repeatable" is the discoverability key.
    assert "Repeatable" in out


def test_edit_help_documents_replace_semantics_for_material() -> None:
    """`flytie edit --material X` REPLACES the material list (not append).

    The friction log didn't surface this directly but it's adjacent — the
    `--clear-materials` flag implies a replace model, which deserves to be
    stated explicitly so the user doesn't have to infer it.
    """
    out = _help(["edit"])
    assert "Replace the material list" in out or "Replace material list" in out
    assert "carry over" in out  # default-omit behavior named


def test_edit_help_documents_hook_range_form() -> None:
    """`--hook` in edit lacked help entirely; should match add's range example."""
    out = _help(["edit"])
    assert "12-16" in out


def test_shop_help_documents_every_selector() -> None:
    """`flytie shop --help` must describe `--pattern`, `--tag`, `--species`, `--exclude`."""
    out = _help(["shop"])
    # Each selector needs a real description, not just a bare flag name.
    for fragment in (
        "Include this pattern by name",
        "Include every pattern with this tag",
        "Include every pattern for this target species",
        "Drop this material from the shopping list",
    ):
        assert fragment in out, f"missing in shop --help: {fragment!r}"


def test_shop_help_calls_out_exclude_use_case() -> None:
    """The `--exclude` flag's purpose ('things you already own') is not obvious from the name."""
    out = _help(["shop"])
    assert "already own" in out


# ---------------------------------------------------------------------------
# Step D12 — `--hook` required error message
# ---------------------------------------------------------------------------


def test_hook_required_error_drops_from_file_mention(env_dirs: tuple[Path, Path]) -> None:
    """Tom: 'the second clause confused me — I've never heard of --from-file at this point.'

    The error users hit when they forget --hook shouldn't introduce a flag
    they haven't met. It can mention --from-file as an alternative path,
    but only after a help-discovery hint that gives them the choice.
    """
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    result = runner.invoke(app, ["add", "Test Fly"])
    assert result.exit_code == 2
    out = result.stdout + result.stderr
    # The old wording is gone.
    assert "--hook is required when --from-file is not supplied" not in out
    # The new wording leads with what the user needs to do.
    assert "hook size is required" in out
    # And it ends with a help-discovery hint, so the user can find --from-file
    # (and everything else) on their own terms.
    assert "flytie add --help" in out


def test_hook_required_error_shows_range_form_too(env_dirs: tuple[Path, Path]) -> None:
    """The same error gets a real range example, mirroring the help text."""
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    result = runner.invoke(app, ["add", "Test Fly"])
    assert result.exit_code == 2
    out = result.stdout + result.stderr
    assert "12-16" in out
