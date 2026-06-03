"""Shopping list generation.

Given a set of patterns selected by name, tag, or species, walk each pattern's
*current* version, aggregate the material lines, and deduplicate them by
canonical material name. Quantities are summed when the unit matches.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from flytie.core import patterns as patterns_repo
from flytie.models import Pattern, normalize_name


def _normalize_unit(unit: str | None) -> str | None:
    """Canonicalize a unit so 'Feather'/'feather '/'FEATHER' all merge."""
    if unit is None:
        return None
    return " ".join(unit.strip().lower().split()) or None


class ShoppingLineItem(BaseModel):
    canonical_name: str
    category: str
    unit: str | None = None
    quantity: float | None = None
    used_in: list[str] = Field(default_factory=list)
    has_unitless: bool = False


class ShoppingList(BaseModel):
    items: list[ShoppingLineItem] = Field(default_factory=list)
    pattern_names: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)

    def by_category(self) -> dict[str, list[ShoppingLineItem]]:
        groups: dict[str, list[ShoppingLineItem]] = OrderedDict()
        for item in sorted(self.items, key=lambda i: (i.category, i.canonical_name)):
            groups.setdefault(item.category, []).append(item)
        return groups


def collect_patterns(
    session: Session,
    *,
    names: Iterable[str] = (),
    tags: Iterable[str] = (),
    species: Iterable[str] = (),
) -> list[Pattern]:
    """Resolve the union of patterns matching any of the selectors."""
    selected: dict[int, Pattern] = {}
    for name in names:
        try:
            p = patterns_repo.get_pattern(session, name)
        except patterns_repo.PatternNotFoundError:
            continue
        selected[p.id] = p
    for tag in tags:
        for p in patterns_repo.list_patterns(session, tag=tag):
            selected[p.id] = p
    for sp in species:
        for p in patterns_repo.list_patterns(session, species=sp):
            selected[p.id] = p
    return sorted(selected.values(), key=lambda p: p.name_display.lower())


def build_shopping_list(
    session: Session,
    *,
    names: Iterable[str] = (),
    tags: Iterable[str] = (),
    species: Iterable[str] = (),
    exclude: Iterable[str] = (),
) -> ShoppingList:
    """Aggregate the current-version materials across the selected patterns."""
    patterns = collect_patterns(session, names=names, tags=tags, species=species)
    exclude_keys = {normalize_name(e) for e in exclude if normalize_name(e)}

    accum: dict[tuple[str, str | None], ShoppingLineItem] = OrderedDict()
    pattern_names: list[str] = []

    for p in patterns:
        pattern_names.append(p.name_display)
        v = p.current_version
        if v is None:
            continue
        for pm in v.materials:
            name = pm.material.canonical_name
            if normalize_name(name) in exclude_keys:
                continue
            normalized_unit = _normalize_unit(pm.unit)
            key = (name, normalized_unit)
            entry = accum.get(key)
            if entry is None:
                entry = ShoppingLineItem(
                    canonical_name=name,
                    category=pm.material.category,
                    unit=normalized_unit,
                    quantity=pm.quantity,
                    used_in=[p.name_display],
                    has_unitless=pm.quantity is None,
                )
                accum[key] = entry
                continue
            if pm.quantity is not None:
                entry.quantity = (entry.quantity or 0) + pm.quantity
            else:
                entry.has_unitless = True
            if p.name_display not in entry.used_in:
                entry.used_in.append(p.name_display)

    return ShoppingList(
        items=list(accum.values()),
        pattern_names=pattern_names,
        excluded=sorted(exclude_keys),
    )
