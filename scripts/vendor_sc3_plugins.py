#!/usr/bin/env python3
"""Copy a trimmed sc3-plugins checkout into thirdparty/sc3-plugins/.

The checkout must be at the tag matching the vendored SuperCollider, with
submodules (``git clone --recursive -b Version-3.14.1
https://github.com/supercollider/sc3-plugins``). cmake/sc3_plugins.cmake
builds the result; see docs/dev/sc3-plugins-build.md.

Usage::

    python scripts/vendor_sc3_plugins.py /path/to/sc3-plugins
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "thirdparty" / "sc3-plugins"
PATCHES = [ROOT / "patches" / "sc3-plugins-sms-bufnum.patch"]

# top-level entries kept; everything else (website, quarks, osx_package, the
# upstream CMake files, packaging) is dropped
KEEP_TOP = ["license.txt", "README.md", "source", "external_libraries"]
# plugin directories dropped from source/: HOA by decision, NovaDiskIO and
# LadspaUGen because they are off, local/ because it is empty upstream
DROP_SOURCE = {"HOAUGens", "NovaDiskIO", "LadspaUGen", "local"}
# stk: headers and sources only (no rawwaves, docs, projects or build files)
KEEP_STK = ["LICENSE", "README.md", "include", "src"]
# nova-simd is not copied: the build uses thirdparty/supercollider's copy


def _ignore(directory: str, names: list[str]) -> set[str]:
    """Drop VCS files, the upstream CMake files and the sclang ``sc/`` trees."""
    dropped = {n for n in names if n.startswith(".git") or n == "CMakeLists.txt"}
    if "sc" in names and (Path(directory) / "sc").is_dir():
        dropped.add("sc")
    return dropped


def _keep_licences(src_plugin: Path, dest_plugin: Path) -> None:
    """Copy licence files that live only inside a dropped ``sc/`` tree."""
    for path in (src_plugin / "sc").rglob("*"):
        if path.is_file() and path.name.upper().startswith(("LICEN", "COPYING")):
            target = dest_plugin / path.relative_to(src_plugin)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def vendor(src: Path) -> None:
    if not (src / "external_libraries" / "stk" / "include" / "Stk.h").exists():
        sys.exit(f"{src}: not an sc3-plugins checkout with submodules")
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)
    for name in KEEP_TOP:
        if name in {"source", "external_libraries"}:
            continue
        shutil.copy2(src / name, DEST / name)
    for plugin in sorted((src / "source").iterdir()):
        if not plugin.is_dir() or plugin.name in DROP_SOURCE:
            continue
        shutil.copytree(plugin, DEST / "source" / plugin.name, ignore=_ignore)
        if (plugin / "sc").is_dir():
            _keep_licences(plugin, DEST / "source" / plugin.name)
    stk_src = src / "external_libraries" / "stk"
    stk_dest = DEST / "external_libraries" / "stk"
    stk_dest.mkdir(parents=True)
    for name in KEEP_STK:
        path = stk_src / name
        if path.is_dir():
            shutil.copytree(path, stk_dest / name, ignore=_ignore)
        else:
            shutil.copy2(path, stk_dest / name)
    for patch in PATCHES:
        subprocess.run(
            ["patch", "-p1", "-N", "-d", str(DEST), "-i", str(patch)], check=True
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    vendor(Path(sys.argv[1]).resolve())
