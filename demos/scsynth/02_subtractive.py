"""
02_subtractive.py -- Filtered saw + resonant noise.

Two self-freeing SynthDefs:
  1. Saw through a sweeping LPF (XLine modulating cutoff)
  2. WhiteNoise through RLPF with LFO-modulated cutoff

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import LFNoise1, LPF, Out, Pan2, RLPF, Saw, WhiteNoise, XLine


def main() -> None:
    # -- SynthDef 1: saw -> sweeping LPF (self-freeing) -----------------------
    with SynthDefBuilder(frequency=110.0, amplitude=0.4) as builder:
        sig = Saw.ar(frequency=builder["frequency"])
        cutoff = XLine.kr(
            start=8000.0,
            stop=200.0,
            duration=3.0,
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = LPF.ar(source=sig, frequency=cutoff)
        sig = sig * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    saw_def = builder.build(name="filtered_saw")
    print(f"SynthDef '{saw_def.name}' compiled: {len(saw_def.compile())} bytes")

    # -- SynthDef 2: noise -> resonant LPF with LFO --------------------------
    with SynthDefBuilder(amplitude=0.15) as builder:
        sig = WhiteNoise.ar()
        lfo = LFNoise1.kr(frequency=4.0)
        # Map LFO from [-1,1] to [200, 4000]
        cutoff = lfo * 1900.0 + 2100.0
        sig = RLPF.ar(source=sig, frequency=cutoff, reciprocal_of_q=0.1)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.5, sustain_time=2.0, release_time=0.5
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    noise_def = builder.build(name="resonant_noise")
    print(f"SynthDef '{noise_def.name}' compiled: {len(noise_def.compile())} bytes")

    # -- Boot and play --------------------------------------------------------
    with Server(Options(verbosity=0)) as server:
        saw_def.send(server)
        noise_def.send(server)
        time.sleep(0.1)

        # Play filtered saw
        print("Playing filtered saw (3s sweep)...")
        server.synth("filtered_saw")
        time.sleep(1.5)

        # Layer resonant noise on top
        print("Layering resonant noise (3s)...")
        server.synth("resonant_noise")
        time.sleep(3.5)

    print("Done.")


if __name__ == "__main__":
    main()
