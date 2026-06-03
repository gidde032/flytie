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

from flytie.core.dto import PatternDTO, PatternVersionDTO
from flytie.core.shop import ShoppingList


def patterns_table(patterns: Iterable[PatternDTO]) -> Table:
    """Build a Rich table summarizing many patterns."""
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
    """Print a full pattern card (header + materials + instructions + notes)."""
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
    """Print a single historical version (used by `flytie versions/view`)."""
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
    """Compact list of every version of a pattern."""
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
    """Print a unified-diff blob with syntax highlighting."""
    text = "\n".join(diff_lines)
    if not text:
        console.print("[green]No differences.[/green]")
        return
    console.print(Syntax(text, "diff", theme="ansi_dark", background_color="default"))


def shopping_list_table(shopping_list: ShoppingList) -> Table:
    """Grouped, deduplicated shopping list rendered as a Rich table."""
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


def _escape_md(text: str) -> str:
    """Escape Markdown special characters so material names render as literals.

    Real-world tying materials contain `#`, `*`, `[`, `_`, `(` — left as-is they
    would render as headings, emphasis, or links. This is the conservative set
    that CommonMark requires escaping at the start of a line or token.
    """
    specials = "\\`*_{}[]()#+-.!|<>"
    out = []
    for ch in text:
        if ch in specials:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def shopping_list_as_markdown(shopping_list: ShoppingList) -> str:
    """Markdown export of the shopping list, grouped by category."""
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
    """JSON export of the shopping list (machine-readable; reviewers' missing spec format)."""
    return shopping_list.model_dump_json(indent=2)


def shopping_list_as_text(shopping_list: ShoppingList) -> str:
    """Plain text export of the shopping list, suitable for piping to a printer."""
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
                f"  - {item.canonical_name}"
                + (f"  ({qty_section})" if qty_section else "")
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
