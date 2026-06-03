"""flytie command-line entry point.

Each subcommand is a thin shell that delegates to `flytie.core.*` for logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console

from flytie import __version__
from flytie.config import load_settings
from flytie.core import patterns as patterns_repo
from flytie.core import shop as shop_repo
from flytie.core import versions as versions_repo
from flytie.core.dto import MaterialLineDTO, PatternInput
from flytie.core.parsing import (
    MaterialParseError,
    PatternFileError,
    load_pattern_file,
    parse_material_spec,
)
from flytie.db import Database
from flytie.render import (
    patterns_table,
    render_diff,
    render_pattern,
    render_version,
    shopping_list_as_json,
    shopping_list_as_markdown,
    shopping_list_as_text,
    shopping_list_table,
    versions_table,
)

app = typer.Typer(
    name="flytie",
    help="Fly Tying Recipe Manager — manage, search, version, and export tying patterns.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    # Don't claim `-h` for help — keep it available for power-user short flags.
    context_settings={"help_option_names": ["--help"]},
)
tag_app = typer.Typer(help="Tag management commands.", no_args_is_help=True)
app.add_typer(tag_app, name="tag")
console = Console()
err_console = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"flytie {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    _version: bool = typer.Option(
        False,
        "--version",
        help="Print the flytie version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Top-level options."""


def _open_db() -> Database:
    return Database.from_settings(load_settings())


def _fail(message: str, code: int = 1) -> typer.Exit:
    """Print a red error to stderr and produce a typer.Exit with the given code."""
    err_console.print(f"[red]{message}[/red]")
    return typer.Exit(code=code)


def _format_pydantic_error(exc: ValidationError) -> str:
    """Human-friendly summary of a Pydantic ValidationError."""
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        msg = err.get("msg", "invalid value")
        lines.append(f"  - {loc}: {msg}" if loc else f"  - {msg}")
    return "Pattern input is invalid:\n" + "\n".join(lines)


def _parse_materials_or_exit(specs: list[str]) -> list[MaterialLineDTO]:
    try:
        return [parse_material_spec(spec) for spec in specs]
    except MaterialParseError as exc:
        raise _fail(str(exc), code=2) from exc


def _build_pattern_input(**fields: object) -> PatternInput:
    """Wrap PatternInput construction so Pydantic errors surface nicely."""
    try:
        return PatternInput(**fields)  # type: ignore[arg-type]
    except ValidationError as exc:
        raise _fail(_format_pydantic_error(exc), code=2) from exc


def _load_file_or_exit(path: Path) -> PatternInput:
    try:
        return load_pattern_file(path)
    except PatternFileError as exc:
        raise _fail(str(exc), code=2) from exc
    except ValidationError as exc:
        raise _fail(_format_pydantic_error(exc), code=2) from exc


# --- init ---------------------------------------------------------------------


@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="Re-create the schema even if the DB exists."),
) -> None:
    """Initialize the local SQLite database for flytie."""
    settings = load_settings()
    db = Database.from_settings(settings)
    existed = db.db_exists
    if existed and not force:
        console.print(f"[yellow]Database already exists at[/yellow] {settings.db_path}")
        console.print("Use [bold]--force[/bold] to recreate.")
        raise typer.Exit(code=0)
    if force and existed:
        db.drop_schema()
    db.create_schema()
    console.print(f"[green]Initialized flytie database[/green] at {settings.db_path}")


# --- add ----------------------------------------------------------------------


@app.command()
def add(
    name: str = typer.Argument(..., help="Pattern name (case-insensitive unique)."),
    hook: str | None = typer.Option(
        None, "--hook", help="Hook size or range, e.g. '14' or '12-16'. Required unless --from-file supplies it."
    ),
    difficulty: int | None = typer.Option(None, "--difficulty", min=1, max=5),
    instructions: str = typer.Option("", "--instructions"),
    notes: str = typer.Option("", "--notes"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Repeatable tag."),
    species: list[str] = typer.Option([], "--species", "-s", help="Repeatable target species."),
    material: list[str] = typer.Option(
        [],
        "--material",
        "-m",
        help='Material spec "name,category,qty,unit,notes" (repeatable).',
    ),
    from_file: Path | None = typer.Option(
        None, "--from-file", help="Load pattern fields from a JSON or TOML file. CLI flags override."
    ),
) -> None:
    """Add a new tying pattern to the local library.

    Examples:
      flytie add "Parachute Adams" --hook 14 -t dryfly -m "hackle,hackle,1,feather"
      flytie add "Zebra Midge" --from-file zebra.json
    """
    if from_file is not None:
        base = _load_file_or_exit(from_file)
        # CLI flags override only when explicitly supplied.
        overrides: dict[str, object] = {}
        if name and name != base.name:
            # Positional name was given explicitly; treat as an override.
            overrides["name"] = name
        if hook is not None:
            overrides["hook_size"] = hook
        if difficulty is not None:
            overrides["difficulty"] = difficulty
        if instructions:
            overrides["instructions"] = instructions
        if notes:
            overrides["notes"] = notes
        if tag:
            overrides["tags"] = tag
        if species:
            overrides["species"] = species
        if material:
            overrides["materials"] = _parse_materials_or_exit(material)
        payload = base.model_copy(update=overrides)
    else:
        if hook is None:
            raise _fail("--hook is required when --from-file is not supplied.", code=2)
        materials = _parse_materials_or_exit(material)
        payload = _build_pattern_input(
            name=name,
            hook_size=hook,
            difficulty=difficulty,
            instructions=instructions,
            notes=notes,
            tags=tag or [],
            species=species or [],
            materials=materials,
        )

    db = _open_db()
    try:
        with db.session() as s:
            pattern = patterns_repo.create_pattern(s, payload)
            dto = patterns_repo.to_dto(pattern)
    except patterns_repo.DuplicatePatternError as exc:
        raise _fail(str(exc), code=1) from exc
    except ValueError as exc:
        raise _fail(str(exc), code=2) from exc

    v = dto.current_version
    suffix = f"v{v.version_number}" if v else "(no version)"
    console.print(f"[green]Added[/green] {dto.name} ({suffix})")


# --- list ---------------------------------------------------------------------


@app.command(name="list")
def list_cmd(
    tag: str | None = typer.Option(None, "--tag", "-t"),
    species: str | None = typer.Option(None, "--species", "-s"),
    include_deleted: bool = typer.Option(False, "--include-deleted"),
) -> None:
    """List patterns, optionally filtering by tag or species."""
    db = _open_db()
    with db.session() as s:
        rows = patterns_repo.list_patterns(
            s, tag=tag, species=species, include_deleted=include_deleted
        )
        dtos = [patterns_repo.to_dto(p) for p in rows]
    if not dtos:
        console.print("[yellow]No patterns found.[/yellow]")
        return
    console.print(patterns_table(dtos))


# --- view ---------------------------------------------------------------------


@app.command()
def view(
    name: str = typer.Argument(...),
    version: int | None = typer.Option(
        None, "--version", help="Show this version number instead of the current one."
    ),
) -> None:
    """Show full details for a pattern (current version by default)."""
    db = _open_db()
    with db.session() as s:
        if version is not None:
            try:
                v_dto = versions_repo.get_version(s, name, version)
            except patterns_repo.PatternNotFoundError as exc:
                raise _fail(str(exc), code=1) from exc
            except versions_repo.VersionNotFoundError as exc:
                raise _fail(str(exc), code=1) from exc
            render_version(console, name, v_dto)
            return
        try:
            p = patterns_repo.get_pattern(s, name)
        except patterns_repo.PatternNotFoundError as exc:
            raise _fail(str(exc), code=1) from exc
        dto = patterns_repo.to_dto(p)
    render_pattern(console, dto)


# --- versions / diff / restore ----------------------------------------------


@app.command()
def versions(name: str = typer.Argument(...)) -> None:
    """List every version of a pattern, oldest first."""
    db = _open_db()
    with db.session() as s:
        try:
            vs = versions_repo.list_versions(s, name)
        except patterns_repo.PatternNotFoundError as exc:
            raise _fail(str(exc), code=1) from exc
    if not vs:
        console.print(f"[yellow]{name} has no recorded versions.[/yellow]")
        return
    console.print(versions_table(name, vs))


@app.command()
def diff(
    name: str = typer.Argument(...),
    v1: int = typer.Argument(..., help="The base version number."),
    v2: int = typer.Argument(..., help="The compared version number."),
) -> None:
    """Show a unified diff between two versions of a pattern."""
    db = _open_db()
    with db.session() as s:
        try:
            _, _, lines = versions_repo.diff_versions(s, name, v1, v2)
        except patterns_repo.PatternNotFoundError as exc:
            raise _fail(str(exc), code=1) from exc
        except versions_repo.VersionNotFoundError as exc:
            raise _fail(str(exc), code=1) from exc
    render_diff(console, lines)


@app.command()
def restore(
    name: str = typer.Argument(...),
    version: int = typer.Argument(..., help="The version number to copy forward."),
) -> None:
    """Restore an old version by appending it as a new version (non-destructive)."""
    db = _open_db()
    with db.session() as s:
        try:
            new_v = versions_repo.restore_version(s, name, version)
        except patterns_repo.PatternNotFoundError as exc:
            raise _fail(str(exc), code=1) from exc
        except versions_repo.VersionNotFoundError as exc:
            raise _fail(str(exc), code=1) from exc
    console.print(
        f"[green]Restored[/green] {name} v{version} → new v{new_v.version_number}"
    )


# --- shop -------------------------------------------------------------------


@app.command()
def shop(
    pattern: list[str] | None = typer.Option(
        None, "--pattern", "-p", help="Pattern name (repeatable)."
    ),
    tag: list[str] | None = typer.Option(None, "--tag", "-t", help="Tag (repeatable)."),
    species: list[str] | None = typer.Option(
        None, "--species", "-s", help="Target species (repeatable)."
    ),
    exclude: list[str] | None = typer.Option(
        None,
        "--exclude",
        "-x",
        help="Material you already own; will be dropped from the output (repeatable).",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table (Rich), markdown, text, or json.",
    ),
) -> None:
    """Generate a deduplicated shopping list from selected patterns/tags/species."""
    if not (pattern or tag or species):
        raise _fail(
            "Specify at least one of --pattern, --tag, or --species.", code=2
        )
    valid_formats = {"table", "markdown", "text", "json"}
    if output_format not in valid_formats:
        raise _fail(
            f"Unknown --format {output_format!r}; choose one of "
            f"{', '.join(sorted(valid_formats))}.",
            code=2,
        )
    db = _open_db()
    with db.session() as s:
        shopping_list = shop_repo.build_shopping_list(
            s,
            names=pattern or [],
            tags=tag or [],
            species=species or [],
            exclude=exclude or [],
        )
    if not shopping_list.items:
        console.print("[yellow]Nothing to buy — selected patterns have no materials.[/yellow]")
        return
    if output_format == "markdown":
        console.print(shopping_list_as_markdown(shopping_list))
    elif output_format == "text":
        console.print(shopping_list_as_text(shopping_list))
    elif output_format == "json":
        console.print(shopping_list_as_json(shopping_list))
    else:
        console.print(shopping_list_table(shopping_list))


# --- search -------------------------------------------------------------------


@app.command()
def search(query: str = typer.Argument(..., help="Free-text query.")) -> None:
    """Search patterns by name, instructions, notes, or material."""
    db = _open_db()
    with db.session() as s:
        rows = patterns_repo.search_patterns(s, query)
        dtos = [patterns_repo.to_dto(p) for p in rows]
    if not dtos:
        console.print(f"[yellow]No patterns match '{query}'.[/yellow]")
        return
    console.print(patterns_table(dtos))


# --- edit ---------------------------------------------------------------------


def _resolve_list_arg(
    flag_label: str,
    value: list[str] | None,
    clear: bool,
) -> list[str] | None:
    """Apply None/[]/list sentinel rules with an explicit conflict check."""
    if value and clear:
        raise _fail(
            f"Cannot combine {flag_label} with --clear-{flag_label.lstrip('-')}. "
            f"Use one or the other.",
            code=2,
        )
    if clear:
        return []
    return value  # may be None (leave alone) or a non-empty list


@app.command()
def edit(
    name: str = typer.Argument(...),
    hook: str | None = typer.Option(None, "--hook"),
    difficulty: int | None = typer.Option(None, "--difficulty", min=1, max=5),
    instructions: str | None = typer.Option(None, "--instructions"),
    notes: str | None = typer.Option(None, "--notes"),
    tag: list[str] | None = typer.Option(
        None, "--tag", "-t", help="Set tags; pass --clear-tags to clear."
    ),
    clear_tags: bool = typer.Option(False, "--clear-tags"),
    species: list[str] | None = typer.Option(None, "--species", "-s"),
    clear_species: bool = typer.Option(False, "--clear-species"),
    material: list[str] | None = typer.Option(None, "--material", "-m"),
    clear_materials: bool = typer.Option(False, "--clear-materials"),
    rename_to: str | None = typer.Option(
        None,
        "--rename-to",
        help="Update the display name (must be the same canonical name).",
    ),
    from_file: Path | None = typer.Option(None, "--from-file"),
) -> None:
    """Edit a pattern. Creates a new immutable version.

    Sentinel rules:
      - omit a flag to leave that field unchanged
      - --clear-tags / --clear-species / --clear-materials clear the list
      - --from-file supplies a baseline; later CLI flags override individual fields
    """
    tags_value = _resolve_list_arg("--tag", tag, clear_tags)
    species_value = _resolve_list_arg("--species", species, clear_species)
    if material and clear_materials:
        raise _fail("Cannot combine --material with --clear-materials.", code=2)
    if clear_materials:
        materials_value: list[MaterialLineDTO] | None = []
    elif material is not None:
        materials_value = _parse_materials_or_exit(material)
    else:
        materials_value = None

    db = _open_db()
    # Single session: read current state, build payload, write new version.
    with db.session() as s:
        try:
            current = patterns_repo.get_pattern(s, name)
        except patterns_repo.PatternNotFoundError as exc:
            raise _fail(str(exc), code=1) from exc
        current_v = current.current_version
        if current_v is None:
            raise _fail(f"Pattern {name!r} has no current version to edit.", code=1)
        # Capture defaults inside the session (post-close use would be safe with
        # expire_on_commit=False but we keep things explicit and easy to audit).
        defaults = PatternInput(
            name=current.name_display,
            hook_size=current_v.hook_size,
            difficulty=current_v.difficulty,
            instructions=current_v.instructions,
            notes=current_v.notes,
            tags=None,
            species=None,
            materials=None,
        )

        if from_file is not None:
            base = _load_file_or_exit(from_file)
            payload = base
        else:
            payload = defaults

        # Layer CLI flags on top of either the file payload or the defaults.
        overrides: dict[str, object] = {}
        if hook is not None:
            overrides["hook_size"] = hook
        if difficulty is not None:
            overrides["difficulty"] = difficulty
        if instructions is not None:
            overrides["instructions"] = instructions
        if notes is not None:
            overrides["notes"] = notes
        if tags_value is not None:
            overrides["tags"] = tags_value
        if species_value is not None:
            overrides["species"] = species_value
        if materials_value is not None:
            overrides["materials"] = materials_value
        # Preserve the existing display name unless the user explicitly renames.
        # This protects against accidental case-changes (e.g. `flytie edit adams`)
        # and against a `--from-file` payload whose `name` differs from the target.
        if rename_to is not None:
            overrides["name"] = rename_to
        else:
            overrides["name"] = current.name_display
        payload = payload.model_copy(update=overrides)

        try:
            pattern = patterns_repo.edit_pattern(s, name, payload)
        except ValueError as exc:
            raise _fail(str(exc), code=2) from exc
        dto = patterns_repo.to_dto(pattern)

    v = dto.current_version
    suffix = f"v{v.version_number}" if v else "(no version)"
    console.print(f"[green]Edited[/green] {dto.name} → {suffix}")


# --- delete -------------------------------------------------------------------


@app.command()
def delete(
    name: str = typer.Argument(...),
    hard: bool = typer.Option(False, "--hard", help="Permanently delete instead of soft-delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Delete a pattern (soft by default). Soft-deleted patterns can be restored later."""
    if not yes:
        is_tty = sys.stdin.isatty()
        if not is_tty:
            raise _fail("Refusing to delete without --yes when stdin is not a TTY.", code=2)
        verb = "permanently delete" if hard else "soft-delete"
        ok = typer.confirm(f"Are you sure you want to {verb} {name!r}?")
        if not ok:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(code=0)
    db = _open_db()
    with db.session() as s:
        try:
            if hard:
                patterns_repo.hard_delete_pattern(s, name)
            else:
                patterns_repo.soft_delete_pattern(s, name)
        except patterns_repo.PatternNotFoundError as exc:
            raise _fail(str(exc), code=1) from exc
    console.print(f"[green]{'Hard-' if hard else ''}Deleted[/green] {name}")


# --- tag add / remove ---------------------------------------------------------


@tag_app.command("add")
def tag_add(
    name: str = typer.Argument(..., help="Pattern name."),
    tags: list[str] = typer.Argument(..., help="One or more tags to add."),
) -> None:
    """Add tags to a pattern."""
    db = _open_db()
    with db.session() as s:
        try:
            patterns_repo.add_tags(s, name, tags)
        except patterns_repo.PatternNotFoundError as exc:
            raise _fail(str(exc), code=1) from exc
    console.print(f"[green]Tagged[/green] {name} with {', '.join(tags)}")


@tag_app.command("remove")
def tag_remove(
    name: str = typer.Argument(...),
    tags: list[str] = typer.Argument(..., help="One or more tags to remove."),
) -> None:
    """Remove tags from a pattern."""
    db = _open_db()
    with db.session() as s:
        try:
            patterns_repo.remove_tags(s, name, tags)
        except patterns_repo.PatternNotFoundError as exc:
            raise _fail(str(exc), code=1) from exc
    console.print(f"[green]Untagged[/green] {name}: removed {', '.join(tags)}")


if __name__ == "__main__":  # pragma: no cover
    app()
