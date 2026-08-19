"""Package metadata consistency checks."""

from importlib.metadata import version

import nanosynth


def test_version_matches_package_metadata() -> None:
    """``nanosynth.__version__`` must match the installed package metadata.

    The version is currently hard-coded in both ``pyproject.toml`` and
    ``src/nanosynth/__init__.py`` with nothing else asserting they agree; this
    catches the two drifting (the metadata version is derived from
    ``pyproject.toml`` at build time).
    """
    assert nanosynth.__version__ == version("nanosynth")
