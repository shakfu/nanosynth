"""Golden-byte tests for the SCgf compiler.

The rest of the suite checks the SCgf binary structurally and for determinism
(``compile() == compile()``); the integration tests prove the bytes are
*correct* by rendering real audio from them via NRT. These tests freeze that
proven-correct output as golden fixtures and assert byte-equality, catching any
future regression in field ordering or encoding that would still parse but
silently change the binary.

To (re)generate the fixtures after an *intentional* format change, run::

    python tests/test_golden_scgf.py
"""

from pathlib import Path

import pytest

from nanosynth.enums import DoneAction
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import SynthDef, SynthDefBuilder
from nanosynth.ugens import LPF, Mix, Out, Pan2, SinOsc, WhiteNoise

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "scgf"


def canonical_synthdefs() -> dict[str, SynthDef]:
    """Build the canonical SynthDefs used as golden fixtures.

    Names are fixed so the compiled bytes are fully deterministic.
    """
    defs: dict[str, SynthDef] = {}

    with SynthDefBuilder(freq=440.0, amp=0.2) as builder:
        sig = SinOsc.ar(frequency=builder["freq"]) * builder["amp"]
        Out.ar(bus=0, source=sig)
    defs["sine"] = builder.build(name="golden_sine")

    with SynthDefBuilder(cutoff=1200.0) as builder:
        sig = LPF.ar(source=WhiteNoise.ar(), frequency=builder["cutoff"])
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=0.0))
    defs["filtered_noise"] = builder.build(name="golden_filtered_noise")

    with SynthDefBuilder(freq=220.0, gate=1.0) as builder:
        env = EnvGen.kr(
            envelope=Envelope.asr(),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = SinOsc.ar(frequency=builder["freq"]) * env * 0.3
        Out.ar(bus=0, source=sig)
    defs["enveloped"] = builder.build(name="golden_enveloped")

    with SynthDefBuilder() as builder:
        sig = Mix.new([SinOsc.ar(frequency=f) for f in (440.0, 550.0, 660.0)])
        Out.ar(bus=0, source=sig * 0.1)
    defs["additive_mix"] = builder.build(name="golden_additive_mix")

    return defs


@pytest.mark.parametrize("key", sorted(canonical_synthdefs()))
def test_scgf_golden_bytes(key: str) -> None:
    sd = canonical_synthdefs()[key]
    golden_path = GOLDEN_DIR / f"{key}.scsyndef"
    assert golden_path.exists(), (
        f"missing golden fixture {golden_path}; "
        f"regenerate with `python {Path(__file__).name}`"
    )
    assert sd.compile() == golden_path.read_bytes(), (
        f"SCgf bytes for {key!r} diverged from the golden fixture. If this is "
        f"an intentional format change, regenerate the fixtures."
    )


def test_golden_set_matches_fixtures_on_disk() -> None:
    # Guard against a fixture being added/removed without updating the other.
    on_disk = {p.stem for p in GOLDEN_DIR.glob("*.scsyndef")}
    assert on_disk == set(canonical_synthdefs())


def _regenerate() -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for key, sd in canonical_synthdefs().items():
        (GOLDEN_DIR / f"{key}.scsyndef").write_bytes(sd.compile())
        print(f"wrote {key}.scsyndef")


if __name__ == "__main__":
    _regenerate()
