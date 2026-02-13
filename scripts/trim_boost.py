#!/usr/bin/env python3
"""Trim boost headers to only what the compiler actually uses.

Requires a prior build so that ninja dependency info exists in build/.

Usage:
    python scripts/trim_boost.py              # dry-run: print needed files
    python scripts/trim_boost.py --apply      # trim boost/ in-place
"""

import shutil
import subprocess
import sys
from pathlib import Path

SC_ROOT = Path(__file__).resolve().parent.parent / "thirdparty" / "supercollider"
BOOST_ROOT = SC_ROOT / "external_libraries" / "boost"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def find_build_dir() -> Path | None:
    """Find the scikit-build-core build directory with ninja deps."""
    build = PROJECT_ROOT / "build"
    if not build.exists():
        return None
    for d in build.iterdir():
        if d.is_dir() and (d / ".ninja_deps").exists():
            return d
    return None


def get_needed_boost_files(build_dir: Path) -> set[Path]:
    """Extract boost headers from ninja's dependency tracking."""
    result = subprocess.run(
        ["ninja", "-t", "deps"],
        cwd=build_dir,
        capture_output=True,
        text=True,
    )
    needed: set[Path] = set()
    boost_marker = "external_libraries/boost/boost/"
    for line in result.stdout.splitlines():
        line = line.strip()
        if boost_marker in line:
            path = Path(line)
            if path.is_file():
                needed.add(path)
    return needed


def main() -> None:
    apply_mode = "--apply" in sys.argv

    build_dir = find_build_dir()
    if build_dir is None:
        print("No build directory found. Run 'make build' or 'make dev' first.")
        sys.exit(1)

    print(f"Using build dir: {build_dir.name}")
    print("Extracting boost dependencies from ninja...")
    needed = get_needed_boost_files(build_dir)
    print(f"  Boost headers used by compiler: {len(needed)}")

    if not needed:
        print("  No boost headers found in deps -- is the build complete?")
        sys.exit(1)

    # Calculate sizes
    total_size = sum(f.stat().st_size for f in BOOST_ROOT.rglob("*") if f.is_file())
    needed_size = sum(f.stat().st_size for f in needed if f.exists())
    print(f"\n  Current boost size: {total_size / 1024 / 1024:.1f} MB")
    print(f"  Needed headers:     {needed_size / 1024 / 1024:.1f} MB")
    print(f"  Savings:            {(total_size - needed_size) / 1024 / 1024:.1f} MB")

    if not apply_mode:
        print("\nDry run. Pass --apply to trim boost in-place.")
        return

    # Build trimmed tree
    print("\nTrimming boost directory...")
    trimmed = BOOST_ROOT.parent / "boost_trimmed"
    if trimmed.exists():
        shutil.rmtree(trimmed)

    for f in needed:
        rel = f.relative_to(BOOST_ROOT)
        dest = trimmed / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)

    # Also copy any top-level non-header files (LICENSE, etc.)
    for f in BOOST_ROOT.iterdir():
        if f.is_file():
            shutil.copy2(f, trimmed / f.name)

    # Swap directories
    backup = BOOST_ROOT.parent / "boost_original"
    BOOST_ROOT.rename(backup)
    trimmed.rename(BOOST_ROOT)
    shutil.rmtree(backup)

    final_size = sum(f.stat().st_size for f in BOOST_ROOT.rglob("*") if f.is_file())
    print(f"  Trimmed boost size: {final_size / 1024 / 1024:.1f} MB")
    print("Done.")


if __name__ == "__main__":
    main()
