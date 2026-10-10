"""UGen metadata checked against sclang, the SynthDef wire-contract oracle.

``spec/sclang-reference.json`` records, per UGen class and rate method, the
inputs, outputs and special index sclang emits when the method is called with
its defaults (``scripts/sclang_reference.scd``). Each nanosynth UGen is probed
the same way and compared slot by slot. Known deviations live in
``tests/fixtures/ugen_reference_allowlist.json`` with a reason each; an entry
whose problems no longer occur fails too, so the allowlist cannot go stale.
See ``docs/dev/ugen-metadata-audit.md``.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

from nanosynth.synthdef import UGen

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = json.loads((ROOT / "spec" / "sclang-reference.json").read_text())
ALLOWLIST: dict[str, dict[str, Any]] = json.loads(
    (ROOT / "tests" / "fixtures" / "ugen_reference_allowlist.json").read_text()
)

_spec = importlib.util.spec_from_file_location(
    "_gen_ugen_spec", ROOT / "scripts" / "generate_ugen_spec.py"
)
assert _spec is not None and _spec.loader is not None
_generator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_generator)
UGEN_CLASSES: list[type[UGen]] = _generator._ugen_classes()

_probe_spec = importlib.util.spec_from_file_location(
    "_ugen_probe", ROOT / "scripts" / "ugen_probe.py"
)
assert _probe_spec is not None and _probe_spec.loader is not None
_ugen_probe = importlib.util.module_from_spec(_probe_spec)
_probe_spec.loader.exec_module(_ugen_probe)


def _problems(cls: type[UGen]) -> list[str]:
    return list(_ugen_probe.problems(cls, REFERENCE["ugens"].get(cls.__name__)))


def test_reference_matches_vendored_version() -> None:
    text = (ROOT / "thirdparty" / "supercollider" / "SCVersion.txt").read_text()
    version = ".".join(
        re.search(rf"set\(SC_VERSION_{p} (\d+)\)", text).group(1)  # type: ignore[union-attr]
        for p in ("MAJOR", "MINOR", "PATCH")
    )
    assert REFERENCE["sclang_version"] == version


def test_allowlist_names_known_ugens() -> None:
    names = {cls.__name__ for cls in UGEN_CLASSES}
    assert set(ALLOWLIST) <= names
    assert all(entry.get("reason") for entry in ALLOWLIST.values())


@pytest.mark.parametrize("cls", UGEN_CLASSES, ids=lambda c: c.__name__)
def test_ugen_matches_sclang(cls: type[UGen]) -> None:
    expected = ALLOWLIST.get(cls.__name__, {}).get("problems", [])
    assert sorted(_problems(cls)) == sorted(expected)
