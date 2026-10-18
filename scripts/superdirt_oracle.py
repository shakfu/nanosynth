#!/usr/bin/env python3
"""Run SuperDirt on nanosynth's embedded engine, as a parity oracle for nanodirt.

nanosynth boots the engine as client 0; headless sclang attaches SuperDirt as
client 1 and listens for ``/dirt/play`` on UDP 57120. See docs/dev/roadmap.md.

Usage::

    python scripts/superdirt_oracle.py setup            # clone and build, once
    python scripts/superdirt_oracle.py run [--samples GLOB] [--record out.wav]

``setup`` puts everything under ``$NANODIRT_CACHE`` (default ``~/.cache/nanodirt``):
SuperCollider 3.14.1 (sclang only, no Qt), sc3-plugins class files, the SuperDirt
quark at the revision nanodirt pins, Vowel, and Dirt-Samples.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "superdirt_oracle.scd"
CACHE = Path(os.environ.get("NANODIRT_CACHE", Path.home() / ".cache" / "nanodirt"))
SC_TAG = "Version-3.14.1"
SUPERDIRT_REV = "650a1d6"
MAX_LOGINS = 4
BUFFERS = 1024 * 256

SCLANG = CACHE / "src" / "scbuild" / "lang" / "sclang"
CLASS_PATHS = [
    CACHE / "src" / "sc" / "SCClassLibrary",
    CACHE / "src" / "sc3-plugins" / "source",
    CACHE / "quarks" / "SuperDirt",
    CACHE / "quarks" / "Vowel",
    ROOT / "scripts" / "oracle_classes",
]
EXCLUDE_PATHS = [CACHE / "src" / "sc" / "SCClassLibrary" / "scide_scqt"]
CMAKE_FLAGS = [
    "-DCMAKE_BUILD_TYPE=Release",
    "-DSC_QT=OFF",
    "-DSC_IDE=OFF",
    "-DSUPERNOVA=OFF",
    "-DSC_EL=OFF",
    "-DSC_VIM=OFF",
    "-DSC_ED=OFF",
    "-DSC_HIDAPI=OFF",
    "-DSC_ABLETON_LINK=OFF",
    "-DNO_X11=ON",
    "-DINSTALL_HELP=OFF",
    "-DFFT_GREEN=ON",
    "-DAUDIOAPI=portaudio",
    "-DSYSTEM_PORTAUDIO=OFF",
]


def _git_clone(url: str, dest: Path, *args: str) -> None:
    if dest.exists():
        print(f"exists: {dest}")
        return
    subprocess.run(["git", "clone", *args, url, str(dest)], check=True)


def setup() -> None:
    """Clone and build everything the oracle needs. Idempotent."""
    src = CACHE / "src"
    src.mkdir(parents=True, exist_ok=True)
    shallow = ["--depth", "1", "--branch", SC_TAG]
    _git_clone(
        "https://github.com/supercollider/supercollider.git",
        src / "sc",
        *shallow,
        "--recurse-submodules",
        "--shallow-submodules",
    )
    _git_clone("https://github.com/supercollider/sc3-plugins.git", src / "sc3-plugins", *shallow)
    if not SCLANG.exists():
        build = src / "scbuild"
        subprocess.run(
            ["cmake", "-S", str(src / "sc"), "-B", str(build), "-G", "Ninja", *CMAKE_FLAGS],
            check=True,
        )
        subprocess.run(["ninja", "-C", str(build), "sclang"], check=True)
    superdirt = CACHE / "quarks" / "SuperDirt"
    _git_clone("https://github.com/musikinformatik/SuperDirt.git", superdirt)
    subprocess.run(["git", "-C", str(superdirt), "checkout", "-q", SUPERDIRT_REV], check=True)
    _git_clone(
        "https://github.com/supercollider-quarks/Vowel.git",
        CACHE / "quarks" / "Vowel",
        "--depth",
        "1",
    )
    _git_clone(
        "https://github.com/tidalcycles/Dirt-Samples.git",
        CACHE / "Dirt-Samples",
        "--depth",
        "1",
    )
    print(f"ready: {SCLANG}")


def oracle_options(**overrides: object):  # type: ignore[no-untyped-def]
    """Engine options matching superdirt_oracle.scd, with nanosynth as client 0."""
    from nanosynth import Options

    kwargs: dict[str, object] = dict(
        client_id=0,
        maximum_logins=MAX_LOGINS,
        buffer_count=BUFFERS,
        memory_size=8192 * 32,
        maximum_node_count=1024 * 32,
        maximum_synthdef_count=4096,
        wire_buffer_count=2048,
        input_bus_channel_count=2,
        output_bus_channel_count=2,
    )
    kwargs.update(overrides)
    return Options(**kwargs)  # type: ignore[arg-type]


@contextmanager
def superdirt(
    server,  # type: ignore[no-untyped-def]
    samples: list[str] | None = None,
    *,
    dirt_port: int = 57120,
    orbits: int = 12,
    timeout: float = 120.0,
    log: bool = False,
) -> Iterator[subprocess.Popen[str]]:
    """Attach SuperDirt to *server*'s engine for the duration of the block."""
    if not SCLANG.exists():
        raise FileNotFoundError(f"{SCLANG} missing; run `superdirt_oracle.py setup`")
    opts = server._options
    with tempfile.TemporaryDirectory() as tmp:
        conf = Path(tmp) / "sclang_conf.yaml"
        conf.write_text(
            "includePaths:\n"
            + "".join(f"  - {p}\n" for p in CLASS_PATHS)
            + "excludePaths:\n"
            + "".join(f"  - {p}\n" for p in EXCLUDE_PATHS)
            + "excludeDefaultPaths: true\npostInlineWarnings: false\n"
        )
        env = dict(
            os.environ,
            ORACLE_ENGINE_PORT=str(opts.port),
            ORACLE_DIRT_PORT=str(dirt_port),
            ORACLE_SAMPLES=":".join(samples or []),
            ORACLE_ORBITS=str(orbits),
            ORACLE_BUFFERS=str(opts.buffer_count),
            ORACLE_MAX_LOGINS=str(opts.maximum_logins),
        )
        proc = subprocess.Popen(
            [str(SCLANG), "-l", str(conf), str(SCRIPT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=tmp,
        )
        ready = threading.Event()
        failed: list[str] = []
        lines: list[str] = []

        def pump() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                lines.append(line)
                if log:
                    sys.stdout.write("sclang: " + line)
                if line.startswith("ORACLE READY"):
                    ready.set()
                elif line.startswith("ORACLE FAILED"):
                    failed.append(line)
                    ready.set()

        threading.Thread(target=pump, daemon=True).start()
        try:
            if not ready.wait(timeout) or failed:
                tail = "".join(lines[-40:])
                raise RuntimeError(f"SuperDirt did not start:\n{tail}")
            yield proc
        finally:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()


def run(args: argparse.Namespace) -> None:
    from nanosynth import Server

    server = Server(oracle_options())
    server.boot()
    try:
        with superdirt(server, args.samples, log=True):
            print(f"SuperDirt on nanosynth: /dirt/play to UDP {57120}. Ctrl-C to stop.")
            if args.record:
                server.record(args.record, num_channels=2)
            try:
                if args.duration:
                    time.sleep(args.duration)
                else:
                    while True:
                        time.sleep(1)
            except KeyboardInterrupt:
                pass
            finally:
                if args.record:
                    server.stop_recording()
    finally:
        server.quit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="clone and build sclang, quarks and samples")
    r = sub.add_parser("run", help="boot the engine and attach SuperDirt")
    r.add_argument(
        "--samples",
        action="append",
        help="sample folder glob, e.g. ~/.cache/nanodirt/Dirt-Samples/bd (repeatable)",
    )
    r.add_argument("--record", help="record the main output to this file")
    r.add_argument("--duration", type=float, help="stop after this many seconds")
    args = parser.parse_args()
    if args.cmd == "setup":
        setup()
    else:
        run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
