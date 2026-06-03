"""Rich rendering helpers for CLI output.

All functions take DTOs (never ORM objects) so they're safe to call after the
session has closed and easy to unit-test without a database.
"""

from __future__ import annotations

from collections.abc import Iterable

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from flytie.ai.suggest import SuggestionResult
from flytie.core.dto import PatternDTO, PatternVersionDTO
from flytie.core.shop import ShoppingList


def patterns_table(patterns: Iterable[PatternDTO]) -> Table:
    table = Table(title="Patterns", show_lines=False, header_style="bold cyan")
    table.add_column("Name", no_wrap=True)
    table.add_column("Hook", justify="right")
    table.add_column("Version", justify="right")
    table.add_column("Tags")
    table.add_column("Species")
    for p in patterns:
        v = p.current_version
        table.add_row(
            p.name,
            v.hook_size if v else "—",
            f"v{v.version_number}" if v else "—",
            ", ".join(p.tags) or "—",
            ", ".join(p.species) or "—",
        )
    return table


def _materials_table(version: PatternVersionDTO) -> Table:
    table = Table(title="Materials", show_lines=False, header_style="bold")
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Material")
    table.add_column("Category", style="cyan")
    table.add_column("Qty", justify="right")
    table.add_column("Unit")
    table.add_column("Notes", style="dim")
    for i, m in enumerate(version.materials, 1):
        table.add_row(
            str(i),
            m.canonical_name,
            m.category,
            "" if m.quantity is None else f"{m.quantity:g}",
            m.unit or "",
            m.notes,
        )
    return table


def render_pattern(console: Console, pattern: PatternDTO) -> None:
    v = pattern.current_version
    if v is None:
        console.print(f"[yellow]{pattern.name} has no current version.[/yellow]")
        return
    header = (
        f"[bold]{pattern.name}[/bold]  "
        f"hook [cyan]{v.hook_size}[/cyan]  "
        f"[magenta]v{v.version_number}[/magenta]"
    )
    if v.difficulty is not None:
        header += f"  difficulty [green]{v.difficulty}[/green]"
    console.print(header)
    if pattern.tags:
        console.print("tags: " + ", ".join(f"[green]{t}[/green]" for t in pattern.tags))
    if pattern.species:
        console.print("species: " + ", ".join(f"[blue]{s}[/blue]" for s in pattern.species))
    console.print(_materials_table(v))
    if v.instructions:
        console.print(Panel(v.instructions, title="Instructions", border_style="green"))
    if v.notes:
        console.print(Panel(v.notes, title="Notes", border_style="yellow"))


def render_version(console: Console, name: str, version: PatternVersionDTO) -> None:
    console.print(
        f"[bold]{name}[/bold] v{version.version_number} — hook [cyan]{version.hook_size}[/cyan]"
        f" — created {version.created_at:%Y-%m-%d %H:%M}"
    )
    if version.materials:
        console.print(_materials_table(version))
    if version.instructions:
        console.print(Panel(version.instructions, title="Instructions", border_style="green"))
    if version.notes:
        console.print(Panel(version.notes, title="Notes", border_style="yellow"))


def versions_table(name: str, versions: Iterable[PatternVersionDTO]) -> Table:
    table = Table(title=f"{name} — version history", header_style="bold cyan")
    table.add_column("Version", justify="right")
    table.add_column("Hook")
    table.add_column("Difficulty", justify="right")
    table.add_column("Materials", justify="right")
    table.add_column("Created")
    for v in versions:
        table.add_row(
            f"v{v.version_number}",
            v.hook_size,
            "" if v.difficulty is None else str(v.difficulty),
            str(len(v.materials)),
            f"{v.created_at:%Y-%m-%d %H:%M}",
        )
    return table


def render_diff(console: Console, diff_lines: Iterable[str]) -> None:
    text = "\n".join(diff_lines)
    if not text:
        console.print("[green]No differences.[/green]")
        return
    console.print(Syntax(text, "diff", theme="ansi_dark", background_color="default"))


def shopping_list_table(shopping_list: ShoppingList) -> Table:
    table = Table(title="Shopping list", header_style="bold cyan")
    table.add_column("Category", style="cyan")
    table.add_column("Material")
    table.add_column("Qty", justify="right")
    table.add_column("Unit")
    table.add_column("Used in", style="dim")
    for category, items in shopping_list.by_category().items():
        for item in items:
            qty = "" if item.quantity is None else f"{item.quantity:g}"
            if item.has_unitless and item.quantity is not None:
                qty += "+?"
            elif item.has_unitless:
                qty = "?"
            table.add_row(
                category,
                item.canonical_name,
                qty,
                item.unit or "",
                ", ".join(item.used_in),
            )
    return table


_MD_SPECIALS = "\\`*_{}[]()#+-.!|<>"


def _escape_md(text: str) -> str:
    """Escape Markdown special characters so material names render as literals."""
    out = []
    for ch in text:
        if ch in _MD_SPECIALS:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def shopping_list_as_markdown(shopping_list: ShoppingList) -> str:
    lines: list[str] = ["# Shopping list", ""]
    if shopping_list.pattern_names:
        lines.append(
            "For patterns: " + ", ".join(_escape_md(n) for n in shopping_list.pattern_names)
        )
        lines.append("")
    for category, items in shopping_list.by_category().items():
        lines.append(f"## {_escape_md(category)}")
        for item in items:
            qty_str = ""
            if item.quantity is not None:
                qty_str = f"{item.quantity:g}"
                if item.has_unitless:
                    qty_str += "+?"
            elif item.has_unitless:
                qty_str = "?"
            unit_str = f" {_escape_md(item.unit)}" if item.unit else ""
            qty_section = f"{qty_str}{unit_str}".strip()
            qty_label = f" — {qty_section}" if qty_section else ""
            lines.append(f"- {_escape_md(item.canonical_name)}{qty_label}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def shopping_list_as_json(shopping_list: ShoppingList) -> str:
    """JSON export — added per Phase 3 review (spec lists --format json)."""
    return shopping_list.model_dump_json(indent=2)


def shopping_list_as_text(shopping_list: ShoppingList) -> str:
    lines: list[str] = ["Shopping list", "=" * 13, ""]
    for category, items in shopping_list.by_category().items():
        lines.append(category.upper())
        for item in items:
            qty_str = ""
            if item.quantity is not None:
                qty_str = f"{item.quantity:g}"
                if item.has_unitless:
                    qty_str += "+?"
            elif item.has_unitless:
                qty_str = "?"
            unit_str = f" {item.unit}" if item.unit else ""
            qty_section = f"{qty_str}{unit_str}".strip()
            lines.append(
                f"  - {item.canonical_name}" + (f"  ({qty_section})" if qty_section else "")
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_suggestions(console: Console, result: SuggestionResult) -> None:
    """Print AI suggestions as Rich panels.

    Existing library patterns are tagged `[in library]`; novel suggestions get
    a `[NEW]` badge. If structured parsing failed, the model's raw text is
    shown as a fallback so the user still sees something useful.
    """
    req = result.request
    context = f"[bold]{req.species}[/bold] · {req.season}"
    if req.water:
        context += f" · {req.water}"
    if req.conditions:
        context += f" · {req.conditions}"
    console.print(f"AI suggestions for {context}")

    if not result.suggestions:
        console.print(
            "[yellow]Could not parse structured suggestions from the model. Raw response:[/yellow]"
        )
        console.print(Panel(result.raw_text or "(empty response)", border_style="yellow"))
        return

    for i, s in enumerate(result.suggestions, 1):
        # Brackets are escaped (\[) so Rich renders them literally rather than
        # treating "[NEW]" / "[in library]" as markup tags.
        badge = r"[dim]\[in library][/dim]" if s.is_existing else r"[bold green]\[NEW][/bold green]"
        title = f"{i}. {s.name}  {badge}"
        body_lines: list[str] = []
        if s.hook_size:
            body_lines.append(f"[cyan]Hook:[/cyan] {s.hook_size}")
        if s.key_materials:
            body_lines.append("[cyan]Key materials:[/cyan] " + ", ".join(s.key_materials))
        if s.rationale:
            body_lines.append(f"[cyan]Why:[/cyan] {s.rationale}")
        border = "green" if not s.is_existing else "blue"
        console.print(Panel("\n".join(body_lines), title=title, border_style=border))

    new_count = sum(1 for s in result.suggestions if not s.is_existing)
    if new_count:
        console.print(
            f"[dim]{new_count} suggestion(s) are not yet in your library — "
            f"add one with `flytie add`.[/dim]"
        )
