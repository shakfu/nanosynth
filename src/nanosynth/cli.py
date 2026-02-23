"""Command-line interface for nanosynth."""

from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path
from typing import NoReturn


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nanosynth",
        description="nanosynth -- minimal embedded SuperCollider synthesis engine",
    )
    subparsers = parser.add_subparsers(dest="command")

    info_parser = subparsers.add_parser(
        "info",
        help="Show build and environment information",
    )
    info_parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List all available UGen classes",
    )

    return parser


def _audio_backend() -> str:
    if sys.platform == "darwin":
        return "CoreAudio"
    if sys.platform == "win32":
        return "PortAudio (WASAPI)"
    return "PortAudio (ALSA)"


def _try_import(module_name: str) -> tuple[bool, str | None]:
    """Try importing a C extension, return (success, error_reason)."""
    try:
        __import__(module_name)
    except ImportError as exc:
        return False, str(exc)
    return True, None


def _run_info(args: argparse.Namespace) -> None:
    if args.list:
        _list_ugens()
        return

    import nanosynth

    from .scsynth import find_ugen_plugins_path

    plugins_path = find_ugen_plugins_path()
    plugin_count = 0
    if plugins_path is not None:
        plugin_count = len(list(Path(plugins_path).glob("*.scx")))

    scsynth_ok, scsynth_err = _try_import("nanosynth._scsynth")
    supernova_ok, supernova_err = _try_import("nanosynth._supernova")

    scsynth_status = "yes" if scsynth_ok else f"no ({scsynth_err})"
    supernova_status = "yes" if supernova_ok else f"no ({supernova_err})"

    lines = [
        f"nanosynth {nanosynth.__version__}",
        f"Python {platform.python_version()} ({sys.platform}, {platform.machine()})",
        f"Audio backend: {_audio_backend()}",
        f"UGen plugins: {plugins_path or 'not found'}",
        f"Plugin count: {plugin_count}",
        f"scsynth embedded: {scsynth_status}",
        f"supernova embedded: {supernova_status}",
    ]
    print("\n".join(lines))


def _list_ugens() -> None:
    from . import ugens as ugens_module
    from .envelopes import EnvGen
    from .synthdef import UGen

    names: list[str] = []
    for name in sorted(dir(ugens_module)):
        obj = getattr(ugens_module, name)
        if isinstance(obj, type) and issubclass(obj, UGen) and obj is not UGen:
            names.append(name)

    # Include EnvGen which lives outside the ugens package
    if "EnvGen" not in names:
        if isinstance(EnvGen, type) and issubclass(EnvGen, UGen):
            names.append("EnvGen")
            names.sort()

    print(f"{len(names)} UGens available:\n")
    for name in names:
        print(f"  {name}")


def main(argv: list[str] | None = None) -> NoReturn | None:
    """Entry point for the ``nanosynth`` CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "info":
        _run_info(args)
        return None

    parser.print_help()
    sys.exit(1)
