"""Unit tests for the CLI input parsers in `flytie.core.parsing`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flytie.core.parsing import MaterialParseError, load_pattern_file, parse_material_spec


def test_parse_material_name_only() -> None:
    m = parse_material_spec("grizzly hackle")
    assert m.canonical_name == "grizzly hackle"
    assert m.category == "other"
    assert m.quantity is None
    assert m.unit is None
    assert m.notes == ""


def test_parse_material_full() -> None:
    m = parse_material_spec("thread,thread,1,spool,8/0 black")
    assert m.canonical_name == "thread"
    assert m.category == "thread"
    assert m.quantity == 1.0
    assert m.unit == "spool"
    assert m.notes == "8/0 black"


def test_parse_material_partial() -> None:
    m = parse_material_spec("pheasant tail,tail")
    assert m.canonical_name == "pheasant tail"
    assert m.category == "tail"
    assert m.quantity is None


def test_parse_material_rejects_empty() -> None:
    with pytest.raises(MaterialParseError):
        parse_material_spec("")
    with pytest.raises(MaterialParseError):
        parse_material_spec(",,1,spool")


def test_parse_material_rejects_bad_quantity() -> None:
    with pytest.raises(MaterialParseError):
        parse_material_spec("name,cat,notanumber,spool")


def test_parse_material_preserves_commas_in_notes() -> None:
    # `split(",", maxsplit=4)` lets the notes field carry literal commas
    # and their surrounding whitespace intact.
    m = parse_material_spec("name,cat,1,spool,a, b, c")
    assert m.notes == "a, b, c"


def test_load_pattern_json(tmp_path: Path) -> None:
    f = tmp_path / "p.json"
    f.write_text(
        json.dumps(
            {
                "name": "Adams",
                "hook_size": "14",
                "materials": [{"canonical_name": "hackle", "category": "hackle"}],
            }
        )
    )
    p = load_pattern_file(f)
    assert p.name == "Adams"
    assert p.materials is not None
    assert p.materials[0].canonical_name == "hackle"


def test_load_pattern_toml(tmp_path: Path) -> None:
    f = tmp_path / "p.toml"
    f.write_text(
        'name = "Adams"\nhook_size = "14"\n'
        '[[materials]]\ncanonical_name = "hackle"\ncategory = "hackle"\n'
    )
    p = load_pattern_file(f)
    assert p.name == "Adams"
    assert p.materials is not None
    assert p.materials[0].category == "hackle"


def test_load_pattern_rejects_unknown_extension(tmp_path: Path) -> None:
    f = tmp_path / "p.yaml"
    f.write_text("name: Adams")
    with pytest.raises(ValueError):
        load_pattern_file(f)
