"""Compilation corpus checked against sclang 3.14.1 without needing sclang.

``tests/fixtures/sclang_corpus/`` holds what ``scripts/compile_corpus.scd``
compiles in sclang. Each case renders both SynthDefs in NRT and compares the
samples. After adding a case to both corpus scripts, regenerate with::

    sclang -l sclang_conf.yaml scripts/compile_corpus.scd tests/fixtures/sclang_corpus/
"""

import struct
import sys
from pathlib import Path

import pytest

from nanosynth.osc import OscMessage
from nanosynth.score import Score
from nanosynth.scsynth import Options

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import compile_corpus  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "sclang_corpus"


def _render(def_bytes: bytes, path: Path) -> list[float]:
    score = Score()
    score.add(0.0, OscMessage("/d_recv", def_bytes))
    score.add(0.0, OscMessage("/s_new", "corpus", 1000, 0, 0))
    score.add(compile_corpus.SECONDS, OscMessage("/c_set", 0, 0))
    score.render(
        path, sample_format="float", output_channels=2, options=Options(verbosity=-1)
    )
    raw = path.read_bytes()
    i = raw.find(b"data")
    n = struct.unpack("<I", raw[i + 4 : i + 8])[0]
    return list(struct.unpack(f"<{n // 4}f", raw[i + 8 : i + 8 + n - n % 4]))


@pytest.mark.parametrize("name", sorted(compile_corpus.CASES))
def test_matches_sclang(name: str, tmp_path: Path) -> None:
    ref = _render((FIXTURES / f"{name}.scsyndef").read_bytes(), tmp_path / "sc.wav")
    got = _render(compile_corpus.compile_case(name), tmp_path / "ns.wav")
    assert len(ref) == len(got)
    diff = max((abs(a - b) for a, b in zip(ref, got) if a == a and b == b), default=0.0)
    assert diff <= compile_corpus.TOLERANCE
    assert max(abs(a) for a in ref) > 0.01, "silent reference: comparison is vacuous"
