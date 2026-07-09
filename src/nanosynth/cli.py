"""Command-line interface for nanosynth."""

from __future__ import annotations

import argparse
import importlib.util
import platform
import sys
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:
    from .synthdef import SynthDef


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

    compile_parser = subparsers.add_parser(
        "compile",
        help="Compile SynthDefs from a Python file to .scsyndef binaries",
    )
    compile_parser.add_argument(
        "input",
        metavar="FILE.py",
        help="Python file defining one or more SynthDef objects",
    )
    compile_parser.add_argument(
        "-o",
        "--output",
        metavar="DIR",
        default=".",
        help="Directory for per-SynthDef .scsyndef files (default: current directory)",
    )
    compile_parser.add_argument(
        "-b",
        "--bundle",
        metavar="FILE",
        help="Write all SynthDefs into a single .scsyndef file instead of one per def",
    )
    compile_parser.add_argument(
        "-n",
        "--name",
        action="append",
        metavar="NAME",
        help="Only compile the named SynthDef (repeatable); default is all",
    )
    compile_parser.add_argument(
        "--anonymous",
        action="store_true",
        help="Use MD5-hash names in the binary instead of declared names",
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


def _error(message: str) -> NoReturn:
    """Print an error to stderr and exit with status 1."""
    print(f"nanosynth compile: error: {message}", file=sys.stderr)
    sys.exit(1)


def _load_module_from_path(path: Path) -> object:
    """Import a standalone .py file as a module and return it."""
    spec = importlib.util.spec_from_file_location(
        f"_nanosynth_compile_{path.stem}", path
    )
    if spec is None or spec.loader is None:
        _error(f"cannot load {path} as a Python module")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 -- report any error from user code
        _error(f"failed to execute {path}: {exc}")
    return module


def _discover_synthdefs(module: object) -> list[SynthDef]:
    """Collect SynthDef instances bound as attributes of a module, in order."""
    from .synthdef import SynthDef

    found: list[SynthDef] = []
    seen: set[int] = set()
    for value in vars(module).values():
        if isinstance(value, SynthDef) and id(value) not in seen:
            seen.add(id(value))
            found.append(value)
    return found


def _run_compile(args: argparse.Namespace) -> None:
    from .compiler import compile_synthdefs

    input_path = Path(args.input)
    if not input_path.is_file():
        _error(f"input file not found: {input_path}")
    if input_path.suffix != ".py":
        _error(f"input must be a .py file: {input_path}")

    module = _load_module_from_path(input_path.resolve())
    synthdefs = _discover_synthdefs(module)
    if not synthdefs:
        _error(f"no SynthDef objects found in {input_path}")

    if args.name:
        requested = list(args.name)
        by_name = {sd.effective_name: sd for sd in synthdefs}
        missing = [name for name in requested if name not in by_name]
        if missing:
            available = ", ".join(sorted(by_name)) or "(none)"
            _error(
                f"SynthDef(s) not found: {', '.join(missing)}. Available: {available}"
            )
        synthdefs = [by_name[name] for name in requested]

    if args.bundle:
        bundle_path = Path(args.bundle)
        if bundle_path.parent and not bundle_path.parent.exists():
            _error(f"output directory does not exist: {bundle_path.parent}")
        data = compile_synthdefs(*synthdefs, use_anonymous_names=args.anonymous)
        bundle_path.write_bytes(data)
        names = ", ".join(sd.effective_name for sd in synthdefs)
        print(f"Wrote {len(synthdefs)} SynthDef(s) to {bundle_path} ({names})")
        return

    output_dir = Path(args.output)
    if not output_dir.is_dir():
        _error(f"output directory does not exist: {output_dir}")

    effective_names = [sd.effective_name for sd in synthdefs]
    duplicates = {n for n in effective_names if effective_names.count(n) > 1}
    if duplicates:
        _error(
            "duplicate SynthDef names would overwrite each other: "
            f"{', '.join(sorted(duplicates))}. Use --bundle to write a single file."
        )

    for synthdef in synthdefs:
        out_path = output_dir / f"{synthdef.effective_name}.scsyndef"
        synthdef.save(out_path, use_anonymous_name=args.anonymous)
        print(f"Wrote {out_path}")


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

    if args.command == "compile":
        _run_compile(args)
        return None

    parser.print_help()
    sys.exit(1)
