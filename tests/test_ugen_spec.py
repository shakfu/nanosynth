"""Tests for the language-neutral UGen spec (spec/nanosynth-ugens.json).

The committed spec is a generated artifact; these tests fail if it drifts from
the code, so it is regenerated in lockstep (the same guarantee the golden SCgf
fixtures give for the byte format). Regenerate with::

    python scripts/generate_ugen_spec.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "spec" / "nanosynth-ugens.json"
GENERATOR_PATH = REPO_ROOT / "scripts" / "generate_ugen_spec.py"


def _load_generator() -> Any:
    spec = importlib.util.spec_from_file_location("_gen_ugen_spec", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = _load_generator()


@pytest.fixture(scope="module")
def committed_spec() -> dict[str, Any]:
    return json.loads(SPEC_PATH.read_text())


def test_spec_file_exists() -> None:
    assert SPEC_PATH.is_file(), (
        "spec/nanosynth-ugens.json is missing; run the generator"
    )


def test_committed_spec_is_up_to_date() -> None:
    """The committed JSON must match a fresh regeneration byte-for-byte."""
    expected = generator.render(generator.build_spec())
    actual = SPEC_PATH.read_text()
    assert actual == expected, (
        "spec/nanosynth-ugens.json is stale. Run: python scripts/generate_ugen_spec.py"
    )


def test_check_mode_passes_on_committed_file() -> None:
    """The generator's own --check mode agrees the file is current."""
    assert generator.main(["--check"]) == 0


def test_spec_metadata(committed_spec: dict[str, Any]) -> None:
    assert committed_spec["scgf_version"] == 2
    assert committed_spec["spec_version"]
    assert committed_spec["supercollider_version"]
    rates = committed_spec["enums"]["calculation_rates"]
    # Rate integers are the values written into each UGen record.
    assert rates == {"ir": 0, "kr": 1, "ar": 2, "dr": 3}


def test_operator_tables_present(committed_spec: dict[str, Any]) -> None:
    binops = committed_spec["enums"]["binary_operators"]
    unops = committed_spec["enums"]["unary_operators"]
    assert binops["ADDITION"] == 0
    assert binops["MULTIPLICATION"] == 2
    assert "NEGATIVE" in unops


def test_operator_ugens_enumerated(committed_spec: dict[str, Any]) -> None:
    """BinaryOpUGen/UnaryOpUGen are listed with the enum that drives their special_index."""
    ops = {op["name"]: op for op in committed_spec["operator_ugens"]}
    assert set(ops) == {"BinaryOpUGen", "UnaryOpUGen"}

    binary = ops["BinaryOpUGen"]
    assert binary["inputs"] == ["left", "right"]
    assert binary["output_count"] == 1
    assert binary["special_index_enum"] == "binary_operators"
    assert binary["flags"]["pure"] is True

    unary = ops["UnaryOpUGen"]
    assert unary["inputs"] == ["source"]
    assert unary["special_index_enum"] == "unary_operators"

    # Each operator UGen points at a real enum table in the spec.
    for op in ops.values():
        assert op["special_index_enum"] in committed_spec["enums"]

    # Operator UGens are listed separately, not duplicated in the metadata table.
    ugen_names = {u["name"] for u in committed_spec["ugens"]}
    assert ugen_names.isdisjoint(ops)


def test_ugen_entries_are_well_formed(committed_spec: dict[str, Any]) -> None:
    ugens = committed_spec["ugens"]
    assert len(ugens) > 300
    names = [u["name"] for u in ugens]
    assert names == sorted(names), "UGen entries must be sorted by name"
    assert len(names) == len(set(names)), "UGen names must be unique"

    valid_rate_tokens = set(committed_spec["enums"]["calculation_rates"])
    valid_defaults = {"required", "computed", "inf", "-inf", "nan"}
    for ugen in ugens:
        assert set(ugen["flags"]) == {"pure", "output", "width_first", "has_done_flag"}
        for token in ugen["rates"]:
            assert token in valid_rate_tokens
        for param in ugen["parameters"]:
            assert set(param) == {"name", "default", "unexpanded"}
            default = param["default"]
            assert (
                default is None
                or isinstance(default, (int, float))
                or default in valid_defaults
            )


def test_known_ugen_shapes(committed_spec: dict[str, Any]) -> None:
    by_name = {u["name"]: u for u in committed_spec["ugens"]}

    sinosc = by_name["SinOsc"]
    assert sinosc["rates"] == ["ar", "kr"]
    assert sinosc["flags"]["pure"] is True
    assert [p["name"] for p in sinosc["parameters"]] == ["frequency", "phase"]
    assert by_name["SinOsc"]["parameters"][0]["default"] == 440.0

    # Out writes to a bus: an output UGen with no outputs of its own.
    assert by_name["Out"]["flags"]["output"] is True
