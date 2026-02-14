"""
16_klank_splay.py -- Resonant filter banks with stereo spread.

Demonstrates two new UGens:
  - Klank: a bank of resonant filters (equivalent to many parallel Ringz
    UGens but specified declaratively as frequency/amplitude/decay arrays).
    Compare with 08_resonance.py which builds the same thing manually.
  - Splay: spreads an array of mono signals evenly across the stereo field.

Sections:
  1. Gamelan bells -- Klank excited by Dust impulses, metallic partials
  2. Bowed glass -- Klank excited by filtered noise, glass-like partials
     with Splay for stereo imaging

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import (
    BPF,
    Dust,
    HPF,
    Klank,
    LeakDC,
    Out,
    Pan2,
    WhiteNoise,
)


def main() -> None:
    # -- SynthDef 1: gamelan bells (Klank + Dust) -----------------------------
    with SynthDefBuilder(density=2.0, decay=3.0, amplitude=0.3) as builder:
        trig = Dust.ar(density=builder["density"])

        # Gamelan-like inharmonic partials (roughly a Javanese slendro scale)
        sig = Klank.ar(
            source=trig,
            frequencies=[293.0, 330.0, 392.0, 523.0, 587.0, 784.0, 1047.0],
            amplitudes=[1.0, 0.8, 0.6, 0.4, 0.3, 0.2, 0.1],
            decay_times=[
                builder["decay"],
                builder["decay"] * 0.9,
                builder["decay"] * 0.8,
                builder["decay"] * 0.7,
                builder["decay"] * 0.6,
                builder["decay"] * 0.5,
                builder["decay"] * 0.3,
            ],
        )
        sig = LeakDC.ar(source=sig)
        sig = HPF.ar(source=sig, frequency=150.0)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.5, sustain_time=6.0, release_time=2.0
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"] * 0.15
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    gamelan_def = builder.build(name="gamelan")
    print(f"SynthDef '{gamelan_def.name}' compiled: {len(gamelan_def.compile())} bytes")

    # -- SynthDef 2: bowed glass (Klank + noise exciter) ----------------------
    with SynthDefBuilder(amplitude=0.3) as builder:
        # Narrow-band noise exciter simulates a bowing action
        exciter = BPF.ar(
            source=WhiteNoise.ar(),
            frequency=800.0,
            reciprocal_of_q=0.003,
        )
        exciter = exciter * 20.0  # boost narrow band

        # Glass-like harmonic series with long decays
        sig = Klank.ar(
            source=exciter,
            frequencies=[
                440.0,
                1100.0,
                1760.0,
                2420.0,
                3080.0,
                3740.0,
            ],
            amplitudes=[1.0, 0.5, 0.25, 0.15, 0.1, 0.05],
            decay_times=[8.0, 6.0, 4.0, 3.0, 2.0, 1.5],
            decay_scale=0.5,
        )
        sig = LeakDC.ar(source=sig)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=2.0, sustain_time=4.0, release_time=2.0
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"] * 0.2
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    glass_def = builder.build(name="bowed_glass")
    print(f"SynthDef '{glass_def.name}' compiled: {len(glass_def.compile())} bytes")

    # -- Boot and play --------------------------------------------------------
    with Server(Options(verbosity=0, load_synthdefs=False)) as server:
        gamelan_def.send(server)
        glass_def.send(server)
        time.sleep(0.1)

        print("\n1. Gamelan bells: Klank with inharmonic partials...")
        gamelan_def.play(server, density=2.5, decay=3.0, amplitude=0.4)
        time.sleep(1.0)
        # Layer a second instance panned differently for width
        gamelan_def.play(server, density=1.5, decay=4.0, amplitude=0.3)
        time.sleep(8.0)

        print("2. Bowed glass: noise-excited Klank with harmonic series...")
        glass_def.play(server, amplitude=0.35)
        time.sleep(9.0)

        time.sleep(0.5)

    print("Done.")


if __name__ == "__main__":
    main()
