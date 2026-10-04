"""Package metadata consistency checks."""

from importlib.metadata import version

import nanosynth


def test_version_matches_package_metadata() -> None:
    """``nanosynth.__version__`` must match the installed package metadata.

    The version is set in both ``pyproject.toml`` and ``__init__.py``; a
    mismatch means they drifted or the install is stale.
    """
    assert nanosynth.__version__ == version("nanosynth")


def test_all_names_resolve() -> None:
    """Every name in ``__all__`` exists, so ``from nanosynth import *`` works."""
    assert [n for n in nanosynth.__all__ if not hasattr(nanosynth, n)] == []
