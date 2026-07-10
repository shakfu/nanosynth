# Benchmarks

Performance benchmarks for the hot paths: SynthDef graph compilation
(`SynthDefBuilder.build()` and `SynthDef.compile()`) and OSC message/bundle
encode/decode. They live outside `tests/` so the coverage-gated `make test` run
does not collect or time them.

## Running

```bash
make bench            # run, write benchmarks/last.json, print a table
make bench-check      # run and fail if >25% slower than the committed baseline
make bench-baseline   # regenerate benchmarks/baseline.json (then commit it)
```

Or directly:

```bash
uv run pytest benchmarks/ --benchmark-disable-gc --benchmark-json=benchmarks/last.json
uv run python benchmarks/check_regression.py benchmarks/baseline.json benchmarks/last.json --threshold 25
```

## How the regression gate works

`check_regression.py` compares two pytest-benchmark JSON files and exits non-zero
if any shared benchmark is slower in the second file by more than `--threshold`
percent (default 25%, compared on the `median` for outlier robustness).

The metrics are **absolute wall-clock times**, so both files must come from the
**same machine** -- comparing across different hardware is meaningless. There are
two supported flows:

- **Local (tight gate).** `make bench-check` compares your working tree against
  the committed `benchmarks/baseline.json` at 25%. Meaningful because it runs on
  the same machine that produced the baseline. Regenerate the baseline with
  `make bench-baseline` when a change legitimately shifts performance.

- **CI (gross-regression gate, manual).** The `benchmarks` workflow job runs
  on demand only (`workflow_dispatch` -- the Actions "Run workflow" button),
  since the double build is expensive. It benchmarks the HEAD build, then
  rebuilds the previous commit (`HEAD^`) with the same harness and benchmarks
  that -- both on one runner -- and fails at 50%. The looser threshold absorbs
  shared-runner noise while still catching algorithmic blowups (e.g. an
  accidental O(n^2) or a lost constant-dedup pass).

`benchmarks/baseline.json` is committed; `benchmarks/last.json` is transient and
git-ignored.
