#!/usr/bin/env python3
"""Regenerate spec/sclang-reference.json by running scripts/sclang_reference.scd.

Needs sclang at the vendored SuperCollider version. Default class-library paths
are excluded, so user extensions (sc3-plugins) do not leak into the reference.

Usage::

    SCLANG=/path/to/sclang python scripts/sclang_reference.py
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

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "sclang_reference.scd"
OUT_PATH = ROOT / "spec" / "sclang-reference.json"
SC_VERSION_TXT = ROOT / "thirdparty" / "supercollider" / "SCVersion.txt"


def vendored_version() -> str:
    text = SC_VERSION_TXT.read_text()
    parts = [
        re.search(rf"set\(SC_VERSION_{p} (\d+)\)", text) for p in ("MAJOR", "MINOR", "PATCH")
    ]
    return ".".join(m.group(1) for m in parts if m)


def main() -> int:
    sclang = os.environ.get("SCLANG") or shutil.which("sclang")
    if not sclang:
        print("sclang not found; set SCLANG=/path/to/sclang", file=sys.stderr)
        return 1
    # sclang lives in <App>/Contents/MacOS; the class library in <App>/Contents/Resources.
    exe = Path(sclang).resolve()
    candidates = [
        exe.parent.parent / "Resources" / "SCClassLibrary",
        exe.parent.parent / "share" / "SuperCollider" / "SCClassLibrary",
    ]
    library = next((c for c in candidates if c.is_dir()), None)
    if library is None:
        print(f"no SCClassLibrary next to {exe}", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        conf = Path(tmp) / "sclang_conf.yaml"
        conf.write_text(
            "includePaths:\n"
            f"  - {library}\n"
            "excludePaths:\n"
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
        )
        data = json.loads(raw.read_text())
    if data["sclang_version"] != vendored_version():
        print(
            f"sclang {data['sclang_version']} != vendored {vendored_version()}",
            file=sys.stderr,
        )
        return 1
    OUT_PATH.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    print(f"Wrote {OUT_PATH} ({len(data['ugens'])} UGens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
