"""flytie command-line entry point.

Each subcommand is a thin shell that delegates to `flytie.core.*` for logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

from flytie import __version__
from flytie.config import ConfigError, ConfigFile, Settings, load_settings
from flytie.core import patterns as patterns_repo
from flytie.core import portability as portability_repo
from flytie.core import shop as shop_repo
from flytie.core import versions as versions_repo
from flytie.core.dto import MaterialLineDTO, PatternInput
from flytie.core.parsing import (
    MaterialParseError,
    PatternFileError,
    load_pattern_file,
    parse_material_spec,
)
from flytie.db import Database, IncompatibleDatabaseError
from flytie.models import Pattern, Species, Tag
from flytie.render import (
    patterns_table,
    render_diff,
    render_pattern,
    render_suggestions,
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
    context_settings={"help_option_names": ["--help"]},
)
tag_app = typer.Typer(help="Tag management commands.", no_args_is_help=True)
app.add_typer(tag_app, name="tag")
config_app = typer.Typer(help="Manage user-scoped flytie settings.", no_args_is_help=True)
app.add_typer(config_app, name="config")
console = Console()
err_console = Console(stderr=True)

# Settings the `config` command knows how to manage. Dotted keys map into the
# TOML config file. The API key is deliberately NOT here — it is read only from
# the ANTHROPIC_API_KEY environment variable and never persisted to disk.
_CONFIG_KEYS = {
    "database.path": "Path to the SQLite database file.",
    "pdf.template": "Default PDF template name or path.",
    "pdf.output_dir": "Default directory for exported PDFs.",
}


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"flytie {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    _version: bool = typer.Option(
        False, "--version", help="Print the flytie version and exit.",
        callback=_version_callback, is_eager=True,
    ),
) -> None:
    """Top-level options."""


def _open_db() -> Database:
    """Open the database, refusing to operate against a future schema.

    `validate_compatibility` enforces the spec's §8 guarantee that we never
    silently open a DB this build doesn't know how to interpret. Surfaced as
    exit code 4 (incompatible environment), distinct from the existing 1/2/3
    for data / input / missing-dep errors.
    """
    db = Database.from_settings(load_settings())
    try:
        db.validate_compatibility()
    except IncompatibleDatabaseError as exc:
        raise _fail(str(exc), code=4) from exc
    return db


def _fail(message: str, code: int = 1) -> typer.Exit:
    err_console.print(f"[red]{message}[/red]")
    return typer.Exit(code=code)


def _format_pydantic_error(exc: ValidationError) -> str:
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


@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="Re-create the schema even if the DB exists."),
) -> None:
    """Initialize the local SQLite database for flytie.

    Safe to re-run. If a previous `init` was interrupted mid-run and left the
    database stamped but missing tables, this command detects that and repairs
    the schema in place — no `--force` (and no data loss) required.
    """
    settings = load_settings()
    db = Database.from_settings(settings)
    existed = db.db_exists
    repairing = False
    if existed and not force:
        if db.schema_is_complete():
            console.print(f"[yellow]Database already exists at[/yellow] {settings.db_path}")
            console.print("Use [bold]--force[/bold] to recreate.")
            raise typer.Exit(code=0)
        # File present but schema incomplete (e.g. interrupted earlier init).
        # Repair without dropping — there's nothing usable to lose.
        repairing = True
        console.print(
            "[yellow]Database file exists but its schema is incomplete "
            "(an earlier init may have been interrupted) — repairing.[/yellow]"
        )
    if force and existed:
        db.drop_schema()
    db.create_schema()
    verb = "Repaired" if repairing else "Initialized"
    console.print(f"[green]{verb} flytie database[/green] at {settings.db_path}")


@app.command()
def info() -> None:
    """Show resolved paths and a quick library summary.

    Safe to run before `flytie init` (reports "not initialized") and against
    an incompatible database (reports the situation rather than failing).
    The Anthropic API key is never displayed — by design, it lives only in
    the ANTHROPIC_API_KEY environment variable, never on disk.
    """
    settings = load_settings()
    db = Database.from_settings(settings)

    revision = db.alembic_version()
    incompatibility_msg: str | None = None
    schema_complete = db.db_exists and db.schema_is_complete()
    pattern_count: int | None = None
    tag_count: int | None = None
    species_count: int | None = None

    # Detect (don't fail on) an incompatible DB. `info` is the one command that
    # must still work in this state — it's the diagnostic the user runs to
    # figure out *why* every other command is failing.
    if revision is not None:
        try:
            db.validate_compatibility()
        except IncompatibleDatabaseError as exc:
            incompatibility_msg = str(exc)

    if schema_complete and incompatibility_msg is None:
        with db.session() as s:
            pattern_count = (
                s.scalar(
                    select(func.count())
                    .select_from(Pattern)
                    .where(Pattern.is_deleted.is_(False))
                )
                or 0
            )
            tag_count = s.scalar(select(func.count()).select_from(Tag)) or 0
            species_count = s.scalar(select(func.count()).select_from(Species)) or 0

    # Plain key/value rows rather than a Rich `Table` so that long paths are
    # never truncated by terminal-width-aware layout. `info` is a diagnostic
    # command — readability of the full path beats visual polish.
    def _row(label: str, value: str) -> None:
        console.print(f"[cyan]{label:<18}[/cyan] {value}", soft_wrap=True, highlight=False)

    _row("Database path", str(settings.db_path))
    _row("Config file", str(settings.config_file))
    _row("Data directory", str(settings.data_dir))
    if revision is not None:
        _row("Schema revision", revision)
    else:
        _row("Schema revision", "[yellow]not initialized — run `flytie init`[/yellow]")
    if db.db_exists and not schema_complete:
        _row(
            "Schema status",
            "[yellow]incomplete — run `flytie init` to repair[/yellow]",
        )
    if pattern_count is not None:
        _row("Patterns", str(pattern_count))
        _row("Tags", str(tag_count))
        _row("Species", str(species_count))
    if incompatibility_msg is not None:
        err_console.print(f"\n[red]Compatibility warning:[/red] {incompatibility_msg}")


@app.command()
def add(
    name: str = typer.Argument(..., help="Pattern name (case-insensitive unique)."),
    hook: str | None = typer.Option(
        None,
        "--hook",
        help="Hook size or range — e.g. '14' for a single size, or '12-16' for a range.",
    ),
    difficulty: int | None = typer.Option(None, "--difficulty", min=1, max=5),
    instructions: str = typer.Option("", "--instructions"),
    notes: str = typer.Option("", "--notes"),
    tag: list[str] = typer.Option(
        [],
        "--tag",
        "-t",
        help="A tag to attach to this pattern. Repeatable.",
    ),
    species: list[str] = typer.Option(
        [],
        "--species",
        "-s",
        help="A target species for this pattern. Repeatable.",
    ),
    material: list[str] = typer.Option(
        [],
        "--material",
        "-m",
        help=(
            "A material line as `name,category,quantity,unit` — only `name` is "
            "required. Repeatable. Valid categories: thread, hook, hackle, "
            "dubbing, flash, body, tail, wing, head, bead, weight, adhesive, other."
        ),
    ),
    from_file: Path | None = typer.Option(
        None,
        "--from-file",
        help="Load fields from a JSON or TOML pattern file. See docs/pattern-file-format.md.",
    ),
) -> None:
    """Add a new tying pattern to the local library."""
    if from_file is not None:
        base = _load_file_or_exit(from_file)
        overrides: dict[str, object] = {}
        if name and name != base.name:
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
            raise _fail("--hook with a hook size is required, e.g. '14' for a single size, or '12-16' for a range (flytie add --help).", code=2)
        materials = _parse_materials_or_exit(material)
        payload = _build_pattern_input(
            name=name, hook_size=hook, difficulty=difficulty,
            instructions=instructions, notes=notes,
            tags=tag or [], species=species or [], materials=materials,
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


@app.command(name="list")
def list_cmd(
    tag: str | None = typer.Option(None, "--tag", "-t"),
    species: str | None = typer.Option(None, "--species", "-s"),
    hook_size: str | None = typer.Option(
        None, "--hook-size", help="Filter by hook size or range, e.g. '14' or '12-16'."
    ),
    include_deleted: bool = typer.Option(False, "--include-deleted"),
) -> None:
    """List patterns, optionally filtering by tag, species, or hook size."""
    db = _open_db()
    with db.session() as s:
        rows = patterns_repo.list_patterns(
            s, tag=tag, species=species, hook_size=hook_size, include_deleted=include_deleted
        )
        dtos = [patterns_repo.to_dto(p) for p in rows]
    if not dtos:
        console.print("[yellow]No patterns found.[/yellow]")
        return
    console.print(patterns_table(dtos))


@app.command()
def view(
    name: str = typer.Argument(...),
    version: int | None = typer.Option(None, "--version"),
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
    v1: int = typer.Argument(..., help="The base version number.", min=1),
    v2: int = typer.Argument(..., help="The compared version number.", min=1),
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
    version: int = typer.Argument(..., min=1),
) -> None:
    """Restore an old version by appending it as a new version."""
    db = _open_db()
    with db.session() as s:
        try:
            new_v = versions_repo.restore_version(s, name, version)
        except patterns_repo.PatternNotFoundError as exc:
            raise _fail(str(exc), code=1) from exc
        except versions_repo.VersionNotFoundError as exc:
            raise _fail(str(exc), code=1) from exc
    console.print(f"[green]Restored[/green] {name} v{version} → new v{new_v.version_number}")


@app.command()
def shop(
    pattern: list[str] | None = typer.Option(None, "--pattern", "-p", help="Include this pattern by name."),
    tag: list[str] | None = typer.Option(None, "--tag", "-t", help="Include every pattern with this tag."),
    species: list[str] | None = typer.Option(None, "--species", "-s", help="Include every pattern for this target species."),
    exclude: list[str] | None = typer.Option(None, "--exclude", "-x", help="Drop this material from the shopping list (already owned)."),
    output_format: str = typer.Option(
        "table", "--format", "-f",
        help="Output format: table, markdown, text, or json.",
    ),
) -> None:
    """Generate a deduplicated shopping list."""
    if not (pattern or tag or species):
        raise _fail("Specify at least one of --pattern, --tag, or --species.", code=2)
    valid_formats = {"table", "markdown", "text", "json"}
    if output_format not in valid_formats:
        raise _fail(
            f"Unknown --format {output_format!r}; choose one of {', '.join(sorted(valid_formats))}.",
            code=2,
        )
    db = _open_db()
    with db.session() as s:
        shopping_list = shop_repo.build_shopping_list(
            s, names=pattern or [], tags=tag or [], species=species or [],
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


@app.command()
def suggest(
    species: str = typer.Option(..., "--species", "-s", help="Target fish species."),
    season: str = typer.Option(
        ..., "--season", help="Season or time of year, e.g. 'late October' or 'fall'."
    ),
    water: str | None = typer.Option(
        None, "--water", help='Water name, e.g. "Henry\'s Fork".'
    ),
    conditions: str | None = typer.Option(
        None, "--conditions", help="Water conditions, e.g. 'low and clear'."
    ),
    n: int = typer.Option(3, "--n", min=1, max=10, help="Number of flies to suggest."),
) -> None:
    """Ask Claude for fly suggestions grounded in your pattern library.

    Examples:
      flytie suggest --species "rainbow trout" --season "late October"
      flytie suggest -s "brown trout" --season fall --water "Henry's Fork" --conditions "low and clear"
    """
    from flytie import ai as ai_mod

    request = ai_mod.SuggestionRequest(
        species=species, season=season, water=water, conditions=conditions, count=n
    )

    # Grounding context: patterns targeting this species, falling back to the
    # whole library if none match. Only names/hooks/materials are sent (see
    # build_prompt), never instructions or notes.
    db = _open_db()
    with db.session() as s:
        rows = patterns_repo.list_patterns(s, species=species)
        if not rows:
            rows = patterns_repo.list_patterns(s)
        grounding = [patterns_repo.to_dto(p) for p in rows]

    try:
        api_key = ai_mod.resolve_api_key()
        streamer = ai_mod.anthropic_streamer(api_key)
    except ai_mod.AIDependencyError as exc:
        raise _fail(str(exc), code=3) from exc
    except ai_mod.AIError as exc:
        raise _fail(str(exc), code=2) from exc

    # Tell the user, before the call, exactly what leaves their machine.
    if grounding:
        console.print(
            f"[dim]Sending {len(grounding)} pattern name(s) and their material "
            "lists to the Anthropic API. Instructions and notes are never sent.[/dim]"
        )

    try:
        with console.status("[cyan]Consulting Claude…[/cyan]") as status:
            received = 0

            def _on_chunk(chunk: str) -> None:
                # Update the spinner with real streaming progress so the wait
                # reflects actual API activity rather than a static spinner.
                nonlocal received
                received += len(chunk)
                status.update(
                    f"[cyan]Consulting Claude…[/cyan] "
                    f"[dim]({received} characters received)[/dim]"
                )

            result = ai_mod.generate_suggestions(
                request, grounding, streamer, on_chunk=_on_chunk
            )
    except ai_mod.AIError as exc:
        raise _fail(str(exc), code=2) from exc
    except KeyboardInterrupt:
        raise _fail("Cancelled.", code=130) from None

    render_suggestions(console, result)


@app.command("export-db")
def export_db(
    out: Path = typer.Option(
        ..., "--out", "-o", help="Path to write the JSON export file."
    ),
    tag: str | None = typer.Option(
        None, "--tag", help="Only export patterns carrying this tag."
    ),
    species: str | None = typer.Option(
        None, "--species", help="Only export patterns for this target species."
    ),
    include_deleted: bool = typer.Option(
        False, "--include-deleted", help="Also export soft-deleted patterns."
    ),
) -> None:
    """Export patterns to a portable JSON file.

    Exports the whole library, or a subset selected by --tag / --species. The
    full version history of each pattern is included so the export round-trips
    losslessly through `flytie import-db`.

    Examples:
      flytie export-db --out my-patterns.json
      flytie export-db -o dries.json --tag dry
    """
    db = _open_db()
    with db.session() as s:
        document = portability_repo.build_export_document(
            s, tag=tag, species=species, include_deleted=include_deleted
        )
    out_path = out.expanduser()
    if out_path.parent and not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(portability_repo.document_to_json(document), encoding="utf-8")
    count = len(document.patterns)
    if count == 0:
        console.print(
            f"[yellow]No patterns matched — wrote an empty export to {out_path}.[/yellow]"
        )
    else:
        console.print(
            f"[green]Exported {count} pattern(s) to {out_path}.[/green]"
        )


@app.command("import-db")
def import_db(
    path: Path = typer.Argument(
        ..., help="Path to a flytie JSON export file to import."
    ),
    on_conflict: str = typer.Option(
        "skip",
        "--on-conflict",
        help="What to do when a pattern name already exists: skip, overwrite, or rename.",
    ),
) -> None:
    """Import patterns from a flytie JSON export file.

    The import is transactional: if anything goes wrong, the database is left
    completely unchanged. Use --on-conflict to control name collisions.

    Examples:
      flytie import-db shared-patterns.json
      flytie import-db backup.json --on-conflict overwrite
    """
    mode = on_conflict.strip().lower()
    if mode not in portability_repo.CONFLICT_MODES:
        raise _fail(
            "Invalid --on-conflict value. "
            f"Choose one of: {', '.join(portability_repo.CONFLICT_MODES)}.",
            code=2,
        )
    src = path.expanduser()
    if not src.is_file():
        raise _fail(f"Import file not found: {src}", code=2)
    # Cap import file size up front so a runaway file can't exhaust memory
    # (the JSON is held three times during parse: raw text, json.loads, model).
    size = src.stat().st_size
    if size > portability_repo.MAX_IMPORT_FILE_BYTES:
        raise _fail(
            f"Import file is {size} bytes; flytie refuses to import files "
            f"larger than {portability_repo.MAX_IMPORT_FILE_BYTES} bytes.",
            code=2,
        )
    try:
        raw = src.read_text(encoding="utf-8")
    except OSError as exc:
        raise _fail(f"Could not read import file: {exc}", code=2) from exc
    try:
        document = portability_repo.parse_document(raw)
    except portability_repo.PortabilityError as exc:
        raise _fail(str(exc), code=2) from exc

    db = _open_db()
    try:
        with db.session() as s:
            result = portability_repo.import_document(s, document, on_conflict=mode)
    except portability_repo.PortabilityError as exc:
        raise _fail(f"Import failed — no changes were made. {exc}", code=2) from exc
    except Exception as exc:
        # Defensive net: import_document already converts SQLAlchemy errors,
        # but a truly unexpected exception must still be reported as a CLI
        # error (with the rollback guaranteed by db.session()), not as a raw
        # traceback the end user can't act on.
        raise _fail(
            f"Import failed — no changes were made. Unexpected error: {exc}",
            code=1,
        ) from exc

    if result.total == 0:
        console.print("[yellow]The import file contained no patterns.[/yellow]")
        return
    console.print("[green]Import complete.[/green]")
    if result.created:
        console.print(f"  created: {len(result.created)}")
    if result.overwritten:
        console.print(f"  overwritten: {len(result.overwritten)}")
    if result.skipped:
        console.print(
            f"  skipped (name already exists): {len(result.skipped)}"
        )
    if result.renamed:
        console.print(f"  renamed to avoid collisions: {len(result.renamed)}")
        for original, new_name in result.renamed.items():
            console.print(f"    [dim]{original}[/dim] → {new_name}")


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


def _resolve_list_arg(flag_label: str, value: list[str] | None, clear: bool) -> list[str] | None:
    if value and clear:
        raise _fail(
            f"Cannot combine {flag_label} with --clear-{flag_label.lstrip('-')}. Use one or the other.",
            code=2,
        )
    if clear:
        return []
    return value


@app.command()
def edit(
    name: str = typer.Argument(...),
    hook: str | None = typer.Option(None, "--hook", help="Change hook size or range — e.g. '14' for a single size, or '12-16' for a range."),
    difficulty: int | None = typer.Option(None, "--difficulty", min=1, max=5, help="Change pattern difficulty (1 easiest, 5 most difficult)."),
    instructions: str | None = typer.Option(None, "--instructions", help="Change pattern instructions."),
    notes: str | None = typer.Option(None, "--notes", help="Update pattern notes."),
    tag: list[str] | None = typer.Option(None, "--tag", "-t",  help="Replace tag list, tags don't carry over."),
    clear_tags: bool = typer.Option(False, "--clear-tags", help="Clear tag list."),
    species: list[str] | None = typer.Option(None, "--species", "-s", help="Replace species list, tags don't carry over."),
    clear_species: bool = typer.Option(False, "--clear-species", help="Clear species list."),
    material: list[str] | None = typer.Option(None, "--material", "-m", help="Replace material list, materials don't carry over."),
    clear_materials: bool = typer.Option(False, "--clear-materials", help="Clear material list."),
    rename_to: str | None = typer.Option(None, "--rename-to", help="Rename pattern."),
    from_file: Path | None = typer.Option(
        None,
        "--from-file",
        help="Load fields from a JSON or TOML pattern file. See docs/pattern-file-format.md.",
    ),
) -> None:
    """Edit a pattern. Creates a new immutable version."""
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
    with db.session() as s:
        try:
            current = patterns_repo.get_pattern(s, name)
        except patterns_repo.PatternNotFoundError as exc:
            raise _fail(str(exc), code=1) from exc
        current_v = current.current_version
        if current_v is None:
            raise _fail(f"Pattern {name!r} has no current version to edit.", code=1)
        defaults = PatternInput(
            name=current.name_display, hook_size=current_v.hook_size,
            difficulty=current_v.difficulty, instructions=current_v.instructions,
            notes=current_v.notes, tags=None, species=None, materials=None,
        )
        if from_file is not None:
            base = _load_file_or_exit(from_file)
            payload = base
        else:
            payload = defaults
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


@app.command()
def delete(
    name: str = typer.Argument(...),
    hard: bool = typer.Option(False, "--hard"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Delete a pattern (soft by default)."""
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


@tag_app.command("list")
def tag_list_cmd() -> None:
    """List every tag currently used by a pattern, with usage counts.

    Tags attached only to soft-deleted patterns are not shown. Orphan tags
    (created at some point but no longer attached to any active pattern)
    likewise don't appear — only tags you'd see in `flytie list --tag <name>`.
    """
    db = _open_db()
    with db.session() as s:
        stmt = (
            select(Tag.name, func.count(Pattern.id))
            .join(Pattern.tags)
            .where(Pattern.is_deleted.is_(False))
            .group_by(Tag.name)
            .order_by(Tag.name)
        )
        rows = list(s.execute(stmt))
    if not rows:
        console.print("[yellow]No tags in use.[/yellow]")
        return
    table = Table(title="Tags", header_style="bold cyan")
    table.add_column("Tag", style="green")
    table.add_column("Patterns", justify="right")
    for name, count in rows:
        table.add_row(name, str(count))
    console.print(table)


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




@app.command()
def export(
    name: str | None = typer.Argument(
        None, help="Pattern name. Omit and use --tag/--species for a batch export."
    ),
    tag: str | None = typer.Option(None, "--tag", "-t", help="Batch-export every pattern with this tag."),
    species: str | None = typer.Option(
        None, "--species", "-s", help="Batch-export every pattern for this target species."
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        help=(
            "Output destination. A path ending in .pdf is treated as a file; "
            "a path with no extension (or an existing directory) is treated as "
            "a directory, created if missing, into which an auto-named card "
            "is written. Default: current directory."
        ),
    ),
    template: Path | None = typer.Option(None, "--template", help="Custom Jinja2 HTML template path."),
    css: Path | None = typer.Option(None, "--css", help="Custom CSS stylesheet path."),
    photo: Path | None = typer.Option(None, "--photo", help="Optional image to embed (single-pattern export only)."),
    html_only: bool = typer.Option(
        False, "--html", help="Render styled HTML to stdout instead of PDF (single pattern; no WeasyPrint needed)."
    ),
) -> None:
    """Export a pattern as a printable PDF card, or batch-export many.

    Examples:
      flytie export "Parachute Adams" --out ~/cards/parachute-adams.pdf
      flytie export "Parachute Adams" --out ~/cards/    # directory, auto-named
      flytie export "RS2" --photo ~/Pictures/rs2.jpg
      flytie export "Adams" --html > adams.html
      flytie export --tag dryfly --out ~/cards/
    """
    from flytie.pdf import (
        PDFDependencyError,
        PDFTemplateError,
        default_filename,
        render_pattern_html,
        render_pattern_pdf,
    )

    selectors = [bool(name), bool(tag), bool(species)]
    if sum(selectors) == 0:
        raise _fail("Specify a pattern name, or --tag / --species for batch export.", code=2)
    if sum(selectors) > 1:
        raise _fail("Use only one of: a pattern name, --tag, or --species.", code=2)

    batch = name is None
    if batch and html_only:
        raise _fail("--html renders one pattern to stdout; it can't be combined with batch export.", code=2)
    if batch and photo is not None:
        raise _fail("--photo applies to a single pattern; omit it for batch export.", code=2)

    # Collect the pattern DTOs to export.
    db = _open_db()
    with db.session() as s:
        if batch:
            rows = patterns_repo.list_patterns(s, tag=tag, species=species)
            dtos = [patterns_repo.to_dto(p) for p in rows]
        else:
            try:
                p = patterns_repo.get_pattern(s, name)  # type: ignore[arg-type]
            except patterns_repo.PatternNotFoundError as exc:
                raise _fail(str(exc), code=1) from exc
            dtos = [patterns_repo.to_dto(p)]

    if not dtos:
        selector = f"--tag {tag}" if tag else f"--species {species}"
        console.print(f"[yellow]No patterns match {selector}; nothing exported.[/yellow]")
        return

    # HTML-only single-pattern path: print to stdout, no WeasyPrint needed.
    if html_only:
        try:
            html = render_pattern_html(
                dtos[0], template_path=template, css_path=css, photo_path=photo
            )
        except PDFDependencyError as exc:
            raise _fail(str(exc), code=3) from exc
        except PDFTemplateError as exc:
            raise _fail(str(exc), code=2) from exc
        typer.echo(html)
        return

    # Resolve the output directory/file.
    if batch:
        out_dir = out if out is not None else Path.cwd()
        out_dir.mkdir(parents=True, exist_ok=True)
        targets = [(d, out_dir / default_filename(d)) for d in dtos]
    else:
        dto = dtos[0]
        if out is None:
            out_path = Path.cwd() / default_filename(dto)
        elif out.is_dir() or out.suffix == "":
            # An existing directory, or a path with no file extension: treat
            # as a directory and drop the auto-named card inside it. The
            # directory itself is created by `render_pattern_pdf` if missing.
            # Note: pathlib strips a trailing slash from "--out ~/cards/", so
            # we can't rely on the slash to detect "directory intent" — the
            # extension check is what makes that case work.
            out_path = out / default_filename(dto)
        else:
            out_path = out
        targets = [(dto, out_path)]

    written_paths: list[Path] = []
    for dto, dest in targets:
        try:
            written = render_pattern_pdf(
                dto, dest, template_path=template, css_path=css, photo_path=photo
            )
        except PDFDependencyError as exc:
            raise _fail(str(exc), code=3) from exc
        except PDFTemplateError as exc:
            raise _fail(str(exc), code=2) from exc
        written_paths.append(written)

    if len(written_paths) == 1:
        console.print(f"[green]Wrote[/green] {written_paths[0]}")
    else:
        console.print(f"[green]Wrote {len(written_paths)} cards[/green] to {written_paths[0].parent}")


# --- config -----------------------------------------------------------------


def _load_config() -> tuple[ConfigFile, Settings]:
    settings = load_settings()
    try:
        cfg = ConfigFile.load(settings)
    except ConfigError as exc:
        raise _fail(str(exc), code=2) from exc
    return cfg, settings


@config_app.command("path")
def config_path() -> None:
    """Print the location of the flytie config file."""
    settings = load_settings()
    console.print(str(settings.config_file))


@config_app.command("show")
def config_show() -> None:
    """Show all configured settings (the API key is never stored or shown)."""
    cfg, _ = _load_config()
    any_set = False
    for key in _CONFIG_KEYS:
        value = cfg.get(key)
        if value is not None:
            console.print(f"[cyan]{key}[/cyan] = {value}")
            any_set = True
    if not any_set:
        console.print("[yellow]No settings configured; defaults are in effect.[/yellow]")


@config_app.command("get")
def config_get(
    key: str = typer.Argument(..., help="Dotted setting key, e.g. 'database.path'."),
) -> None:
    """Read a single setting."""
    if key not in _CONFIG_KEYS:
        raise _fail(
            f"Unknown config key {key!r}. Known keys: {', '.join(sorted(_CONFIG_KEYS))}.",
            code=2,
        )
    cfg, _ = _load_config()
    value = cfg.get(key)
    if value is None:
        console.print(f"[yellow]{key} is not set (default in effect).[/yellow]")
    else:
        console.print(str(value))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Dotted setting key, e.g. 'database.path'."),
    value: str = typer.Argument(..., help="The value to store."),
) -> None:
    """Write a single setting to the config file."""
    if key not in _CONFIG_KEYS:
        raise _fail(
            f"Unknown config key {key!r}. Known keys: {', '.join(sorted(_CONFIG_KEYS))}.",
            code=2,
        )
    cfg, settings = _load_config()
    cfg.set(key, value)
    cfg.save(settings)
    console.print(f"[green]Set[/green] {key} = {value}")


if __name__ == "__main__":  # pragma: no cover
    app()
