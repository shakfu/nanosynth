"""Command-line interface for nanosynth."""

from __future__ import annotations

import argparse
import runpy
import sys
from typing import NoReturn


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nanosynth",
        description="nanosynth -- minimal embedded SuperCollider synthesis engine",
    )
    subparsers = parser.add_subparsers(dest="command")

    render = subparsers.add_parser(
        "render",
        help="Render a Score script to an audio file (non-real-time)",
    )
    render.add_argument(
        "script",
        help="Path to a Python script that defines a module-level `score` variable",
    )
    render.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output audio file path",
    )
    render.add_argument(
        "--sample-rate",
        type=int,
        default=44100,
        help="Sample rate in Hz (default: 44100)",
    )
    render.add_argument(
        "--format",
        choices=["WAV", "AIFF"],
        default="WAV",
        help="Audio file format (default: WAV)",
    )
    render.add_argument(
        "--sample-format",
        choices=["int16", "int24", "float"],
        default="int16",
        help="Sample encoding (default: int16)",
    )
    render.add_argument(
        "--channels",
        type=int,
        default=2,
        help="Number of output channels (default: 2)",
    )
    render.add_argument(
        "--input",
        default=None,
        help="Input audio file path for NRT processing",
    )
    render.add_argument(
        "--input-channels",
        type=int,
        default=0,
        help="Number of input channels (default: 0)",
    )
    render.add_argument(
        "--verbosity",
        type=int,
        default=0,
        help="Engine verbosity level (default: 0)",
    )

    return parser


def _run_render(args: argparse.Namespace) -> None:
    from .score import Score
    from .scsynth import Options

    script_path: str = args.script

    try:
        namespace = runpy.run_path(script_path)
    except FileNotFoundError:
        print(f"error: script not found: {script_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"error: failed to execute script: {exc}", file=sys.stderr)
        sys.exit(1)

    score = namespace.get("score")
    if score is None:
        print(
            f"error: script {script_path!r} does not define a `score` variable",
            file=sys.stderr,
        )
        sys.exit(1)

    if not isinstance(score, Score):
        print(
            f"error: `score` in {script_path!r} is {type(score).__name__}, "
            f"expected Score",
            file=sys.stderr,
        )
        sys.exit(1)

    options = Options(verbosity=args.verbosity) if args.verbosity != 0 else None

    score.render(
        output_path=args.output,
        sample_rate=args.sample_rate,
        header_format=args.format,
        sample_format=args.sample_format,
        output_channels=args.channels,
        input_path=args.input,
        input_channels=args.input_channels,
        options=options,
    )


def main(argv: list[str] | None = None) -> NoReturn | None:
    """Entry point for the ``nanosynth`` CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "render":
        _run_render(args)
        return None

    # Unreachable with current subcommands, but future-proof.
    parser.print_help()
    sys.exit(1)
