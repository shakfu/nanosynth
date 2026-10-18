"""LocalIn's first block outputs its default (patches/sc-localin-first-block.patch).

Upstream marks the bus touched at block -1, so at NRT start (block 0) LocalIn
copied its uninitialized bus. A fresh process reads zeroed pages; a process
that rendered before reads stale samples.
"""

import struct
from pathlib import Path

from nanosynth.osc import OscMessage
from nanosynth.score import Score
from nanosynth.scsynth import Options
from nanosynth.synthdef import SynthDefBuilder
from nanosynth.ugens import LocalIn, LocalOut, Out, SinOsc


def _render(sd, path: Path, seconds: float = 0.05) -> list[float]:  # type: ignore[no-untyped-def]
    score = Score()
    score.add_synthdef(0.0, sd)
    score.add_synth(0.0, sd.effective_name)
    score.add(seconds, OscMessage("/c_set", 0, 0))
    score.render(
        path, sample_format="float", output_channels=1, options=Options(verbosity=-1)
    )
    raw = path.read_bytes()
    i = raw.find(b"data")
    n = struct.unpack("<I", raw[i + 4 : i + 8])[0]
    return list(struct.unpack(f"<{n // 4}f", raw[i + 8 : i + 8 + n - n % 4]))


def test_first_block_is_default(tmp_path: Path) -> None:
    # Leave nonzero samples in the RT pool.
    with SynthDefBuilder() as b:
        sig = SinOsc.ar(frequency=1000) * 1000 + LocalIn.ar(channel_count=1, default=0)
        LocalOut.ar(source=sig)
        Out.ar(bus=0, source=sig)
    for k in range(3):
        _render(b.build(name="dirty"), tmp_path / f"dirty{k}.wav")

    with SynthDefBuilder() as b:
        fb = LocalIn.ar(channel_count=1, default=0.25)
        LocalOut.ar(source=fb * 0)
        Out.ar(bus=0, source=fb)
    out = _render(b.build(name="clean"), tmp_path / "clean.wav")
    assert out[:64] == [0.25] * 64
    assert all(x == 0 for x in out[64:128])
