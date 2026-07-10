#!/usr/bin/env python3
"""Compare two pytest-benchmark JSON runs and fail on regression.

Usage::

    python benchmarks/check_regression.py BASELINE.json CURRENT.json [--threshold 25] [--metric median]

Exits 1 if any benchmark present in both runs is slower in CURRENT than in
BASELINE by more than ``--threshold`` percent, on the chosen ``--metric``.

Both JSON files MUST come from the same machine (and ideally the same run): the
metrics are absolute wall-clock times, so comparing across different hardware is
meaningless. The two supported flows are (1) a developer comparing their working
tree against the committed ``benchmarks/baseline.json`` on their own machine, and
(2) CI comparing a base checkout against the head checkout within a single runner.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: str) -> dict[str, dict[str, float]]:
    data = json.loads(Path(path).read_text())
    return {bench["name"]: bench["stats"] for bench in data["benchmarks"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", help="baseline pytest-benchmark JSON")
    parser.add_argument("current", help="current pytest-benchmark JSON")
    parser.add_argument(
        "--threshold",
        type=float,
        default=25.0,
        help="allowed slowdown before failing, in percent (default: 25)",
    )
    parser.add_argument(
        "--metric",
        default="median",
        choices=["median", "mean", "min"],
        help="statistic to compare (default: median -- robust to outliers)",
    )
    args = parser.parse_args(argv)

    baseline = _load(args.baseline)
    current = _load(args.current)
    factor = 1.0 + args.threshold / 100.0

    regressions: list[tuple[str, float, float, float]] = []
    rows: list[tuple[str, str, str, str, str]] = []
    for name in sorted(current):
        cur = current[name][args.metric]
        if name not in baseline:
            rows.append((name, "--", f"{cur * 1e6:.2f}us", "--", "new"))
            continue
        base = baseline[name][args.metric]
        ratio = cur / base if base else float("inf")
        regressed = ratio > factor
        status = "REGRESS" if regressed else "ok"
        rows.append(
            (
                name,
                f"{base * 1e6:.2f}us",
                f"{cur * 1e6:.2f}us",
                f"{(ratio - 1) * 100:+.1f}%",
                status,
            )
        )
        if regressed:
            regressions.append((name, base, cur, ratio))

    _print_table(rows, args.metric, args.threshold)

    if regressions:
        print(
            f"\nFAIL: {len(regressions)} benchmark(s) regressed beyond {args.threshold}%:"
        )
        for name, base, cur, ratio in regressions:
            print(
                f"  {name}: {base * 1e6:.2f}us -> {cur * 1e6:.2f}us ({(ratio - 1) * 100:+.1f}%)"
            )
        return 1
    print(f"\nOK: no benchmark regressed beyond {args.threshold}% ({args.metric}).")
    return 0


def _print_table(
    rows: list[tuple[str, str, str, str, str]], metric: str, threshold: float
) -> None:
    headers = ("benchmark", f"base {metric}", f"current {metric}", "delta", "status")
    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows))
        if rows
        else len(headers[i])
        for i in range(len(headers))
    ]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*("-" * w for w in widths)))
    for row in rows:
        print(fmt.format(*row))


if __name__ == "__main__":
    raise SystemExit(main())
