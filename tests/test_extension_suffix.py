"""Compiled extensions are named so every Python the wheel tag claims can load them."""

import importlib.util
import sys
from pathlib import Path

import pytest

import nanosynth

PACKAGE = Path(nanosynth.__file__).parent


def _extension_path(name: str) -> Path:
    spec = importlib.util.find_spec(f"nanosynth.{name}")
    if spec is not None and spec.origin is not None:
        return Path(spec.origin)
    # An unrecognized suffix makes find_spec miss a file that is present.
    found = [p for p in PACKAGE.glob(f"{name}.*") if p.suffix in (".so", ".pyd")]
    if not found:
        pytest.skip(f"{name} not built")
    return found[0]


@pytest.mark.skipif(sys.version_info < (3, 12), reason="version-specific build")
@pytest.mark.parametrize("name", ["_osc", "_scsynth", "_supernova", "_midi"])
def test_abi3_suffix(name: str) -> None:
    # CPython 3.15 also accepts `.abi3-<platform>.so`; 3.12-3.14 do not.
    suffix = ".pyd" if sys.platform == "win32" else ".abi3.so"
    assert _extension_path(name).name == name + suffix
