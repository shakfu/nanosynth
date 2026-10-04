"""Package metadata consistency checks."""

from importlib.metadata import version
from pathlib import Path

import pytest

import nanosynth


def test_version_matches_package_metadata() -> None:
    """``nanosynth.__version__`` must match the installed package metadata.

    ``pyproject.toml`` reads the version from ``__init__.py`` at build time; a
    mismatch means the install is stale or the regex provider is misconfigured.
    """
    assert nanosynth.__version__ == version("nanosynth")


def test_pyproject_has_no_static_version() -> None:
    """The version is single-sourced; ``pyproject.toml`` must not repeat it."""
    tomllib = pytest.importorskip("tomllib")
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text())["project"]
    assert "version" not in project
    assert "version" in project["dynamic"]


def test_all_names_resolve() -> None:
    """Every name in ``__all__`` exists, so ``from nanosynth import *`` works."""
    assert [n for n in nanosynth.__all__ if not hasattr(nanosynth, n)] == []
