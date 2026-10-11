"""Tests for scripts/release_notes.py (CHANGELOG section -> release body)."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_notes.py"
_spec = importlib.util.spec_from_file_location("release_notes", _SCRIPT)
assert _spec is not None and _spec.loader is not None
release_notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_notes)

CHANGELOG = """\
# Changelog

## [Unreleased]

### Changed

- unreleased item

## [0.10.0]

### Added

- ten item

## [0.1.0]

- one item
"""


def _run(tmp_path: Path, version: str, changelog: str = CHANGELOG) -> tuple[int, Path]:
    src = tmp_path / "CHANGELOG.md"
    src.write_text(changelog)
    out = tmp_path / "notes.md"
    rc = release_notes.main([version, "--changelog", str(src), "-o", str(out)])
    return rc, out


def test_extracts_version_section(tmp_path: Path) -> None:
    rc, out = _run(tmp_path, "0.10.0")
    assert rc == 0
    assert (
        out.read_text()
        == "## Changes since the last Release\n\n### Added\n\n- ten item\n"
    )


def test_last_section_runs_to_eof(tmp_path: Path) -> None:
    rc, out = _run(tmp_path, "0.1.0")
    assert rc == 0
    assert out.read_text().endswith("\n\n- one item\n")


def test_version_dots_are_literal(tmp_path: Path) -> None:
    # "0.1.0" must not match "0.10.0" or similar via regex-style dots.
    _, out = _run(tmp_path, "0.1.0")
    assert "ten item" not in out.read_text()


def test_missing_version_falls_back_to_unreleased(tmp_path: Path) -> None:
    rc, out = _run(tmp_path, "9.9.9")
    assert rc == 0
    assert "- unreleased item" in out.read_text()


def test_empty_version_section_falls_back_to_unreleased(tmp_path: Path) -> None:
    rc, out = _run(
        tmp_path, "2.0.0", CHANGELOG.replace("## [0.10.0]", "## [2.0.0]\n\n## [0.10.0]")
    )
    assert rc == 0
    assert "- unreleased item" in out.read_text()


@pytest.mark.parametrize(
    "changelog", ["# Changelog\n", "# Changelog\n\n## [Unreleased]\n\n"]
)
def test_no_section_returns_2_and_writes_nothing(
    tmp_path: Path, changelog: str
) -> None:
    rc, out = _run(tmp_path, "9.9.9", changelog)
    assert rc == 2
    assert not out.exists()


def test_custom_header(tmp_path: Path) -> None:
    src = tmp_path / "CHANGELOG.md"
    src.write_text(CHANGELOG)
    out = tmp_path / "notes.md"
    release_notes.main(
        ["0.1.0", "--changelog", str(src), "-o", str(out), "--header", "Notes"]
    )
    assert out.read_text().startswith("## Notes\n\n")


@pytest.mark.parametrize("version", ["9.9.9", "2.0.0"])
def test_no_fallback_fails_on_missing_or_empty_section(
    tmp_path: Path, version: str
) -> None:
    src = tmp_path / "CHANGELOG.md"
    src.write_text(CHANGELOG.replace("## [0.10.0]", "## [2.0.0]\n\n## [0.10.0]"))
    out = tmp_path / "notes.md"
    rc = release_notes.main(
        [version, "--changelog", str(src), "-o", str(out), "--no-fallback"]
    )
    assert rc == 2
    assert not out.exists()


def test_no_fallback_still_extracts_version(tmp_path: Path) -> None:
    src = tmp_path / "CHANGELOG.md"
    src.write_text(CHANGELOG)
    out = tmp_path / "notes.md"
    rc = release_notes.main(
        ["0.10.0", "--changelog", str(src), "-o", str(out), "--no-fallback"]
    )
    assert rc == 0
    assert "- ten item" in out.read_text()
