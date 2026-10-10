#!/usr/bin/env python3
"""Regenerate spec/sc3-plugins-reference.json: sclang's wire contract for sc3-plugins' UGens.

Runs scripts/sclang_reference.scd with the sc3-plugins class files added to the
class library, and keeps the classes those files define. Then regenerate the
wrappers with scripts/generate_sc3_ugens.py.

Usage::

    SCLANG=/path/to/sclang python scripts/sc3_plugins_reference.py /path/to/sc3-plugins

The sc3-plugins path is a source tree, e.g. the sc3-plugins-<version>-Source
release tarball. sclang and sc3-plugins must be at the vendored SuperCollider
version. See docs/dev/sc3-plugins-wrappers.md.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from sclang_reference import vendored_version

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "sclang_reference.scd"
OUT_PATH = ROOT / "spec" / "sc3-plugins-reference.json"
CLASS_DEF = re.compile(r"^\s*([A-Z]\w*)\s*:\s*\w+", re.M)
CPP = {
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
}  # not .OFF: sc3-plugins keeps disabled units that way


def class_files(source: Path) -> list[Path]:
    """The .sc files sc3-plugins installs: those under each library's sc/ directory."""
    return sorted(source.glob("source/*/sc/**/*.sc"))


def sc3_classes(source: Path) -> dict[str, str]:
    """Class name -> sc3-plugins library (the directory under source/) for each .sc class."""
    found = {}
    for sc in class_files(source):
        library = sc.relative_to(source / "source").parts[0]
        for name in CLASS_DEF.findall(sc.read_text(errors="replace")):
            found[name] = library
    return found


def cpp_tokens(source: Path) -> set[str]:
    """Identifiers in sc3-plugins' C and C++ sources. A UGen class whose name is not
    among them has no unit to load: it fails on a server with "UGen not installed"."""
    tokens: set[str] = set()
    for f in (source / "source").rglob("*"):
        if f.suffix in CPP and f.is_file():
            tokens.update(re.findall(r"[A-Za-z_]\w*", f.read_text(errors="replace")))
    return tokens


def version(source: Path) -> str:
    m = re.search(r"(\d+\.\d+\.\d+)", source.resolve().name)
    return m.group(1) if m else "unknown"


def main() -> int:
    if len(sys.argv) != 2 or not (Path(sys.argv[1]) / "source").is_dir():
        print(__doc__, file=sys.stderr)
        return 2
    source = Path(sys.argv[1])
    if version(source) != vendored_version():
        print(
            f"sc3-plugins {version(source)} != vendored SuperCollider {vendored_version()}",
            file=sys.stderr,
        )
        return 1
    sclang = os.environ.get("SCLANG") or shutil.which("sclang")
    if not sclang:
        print("sclang not found; set SCLANG=/path/to/sclang", file=sys.stderr)
        return 1
    exe = Path(sclang).resolve()
    candidates = [
        exe.parent.parent / "Resources" / "SCClassLibrary",
        exe.parent.parent / "share" / "SuperCollider" / "SCClassLibrary",
    ]
    library = next((c for c in candidates if c.is_dir()), None)
    if library is None:
        print(f"no SCClassLibrary next to {exe}", file=sys.stderr)
        return 1
    classes = sc3_classes(source)
    with tempfile.TemporaryDirectory() as tmp:
        conf = Path(tmp) / "sclang_conf.yaml"
        includes = [
            library,
            *sorted({p.parent for p in class_files(source)}),
        ]
        conf.write_text(
            "includePaths:\n"
            + "".join(f"  - {p}\n" for p in includes)
            + "excludePaths:\n"
            f"  - {library / 'scide_scqt'}\n"
            "excludeDefaultPaths: true\n"
            "postInlineWarnings: false\n"
        )
        raw = Path(tmp) / "reference.json"
        subprocess.run(
            [str(exe), "-l", str(conf), str(SCRIPT), str(raw)],
            check=True,
            timeout=600,
            stdout=subprocess.DEVNULL,
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
        )
        data = json.loads(raw.read_text())
    if data["sclang_version"] != vendored_version():
        print(
            f"sclang {data['sclang_version']} != vendored {vendored_version()}",
            file=sys.stderr,
        )
        return 1
    tokens = cpp_tokens(source)
    ugens = {}
    for name, entry in data["ugens"].items():
        if name in classes:
            ugens[name] = dict(entry, library=classes[name], has_unit=name in tokens)
    out = {
        "sclang_version": data["sclang_version"],
        "sc3_plugins_version": version(source),
        "ugens": ugens,
    }
    OUT_PATH.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(f"Wrote {OUT_PATH} ({len(ugens)} UGens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
