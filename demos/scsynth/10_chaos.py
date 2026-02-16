"""
10_chaos.py -- Chaotic oscillators as sound sources.

Explores three chaotic generators at audio rate:
  1. Henon map -- classic 2D chaotic attractor, harsh and gritty
  2. Lorenz system -- 3-parameter strange attractor, rich texture
  3. FBSine -- feedback sine oscillator, from tonal to noisy

Each is filtered and enveloped. Parameters are swept with XLine/LFNoise1
to explore different regimes of each chaotic system.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import (
    FBSineC,
    HenonC,
    LFNoise1,
    LPF,
    LeakDC,
    LorenzL,
    Out,
    Pan2,
    XLine,
)


def main() -> None:
    # -- SynthDef 1: Henon map ------------------------------------------------
    with SynthDefBuilder(amplitude=0.2) as builder:
        # Sweep the 'a' parameter from stable to chaotic
        a = XLine.kr(
            start=1.0, stop=1.4, duration=4.0, done_action=DoneAction.FREE_SYNTH
        )
        sig = HenonC.ar(frequency=8000.0, a=a, b=0.3)
        sig = LPF.ar(source=sig, frequency=3000.0)
        sig = LeakDC.ar(source=sig)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.3, sustain_time=3.0, release_time=0.7
            ),
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=-0.5))

    henon_def = builder.build(name="henon")
    print(f"SynthDef '{henon_def.name}' compiled: {len(henon_def.compile())} bytes")

    # -- SynthDef 2: Lorenz attractor -----------------------------------------
    with SynthDefBuilder(amplitude=0.15) as builder:
        # Slowly modulate the 'r' parameter (rho) around the chaotic regime
        r = LFNoise1.kr(frequency=0.3) * 10.0 + 28.0
        sig = LorenzL.ar(
            frequency=11025.0,
            s=10.0,
            r=r,
            b=2.667,
            h=0.05,
        )
        sig = LPF.ar(source=sig, frequency=4000.0)
        sig = LeakDC.ar(source=sig)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.5, sustain_time=4.0, release_time=1.0
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=0.0))

    lorenz_def = builder.build(name="lorenz")
    print(f"SynthDef '{lorenz_def.name}' compiled: {len(lorenz_def.compile())} bytes")

    # -- SynthDef 3: FBSine (feedback sine) -----------------------------------
    with SynthDefBuilder(amplitude=0.15) as builder:
        # Sweep feedback amount from tonal to chaotic
        fb = XLine.kr(
            start=0.01, stop=1.5, duration=5.0, done_action=DoneAction.FREE_SYNTH
        )
        sig = FBSineC.ar(
            frequency=8000.0,
            im=1.0,
            fb=fb,
            a=1.1,
            c=0.5,
        )
        sig = LPF.ar(source=sig, frequency=5000.0)
        sig = LeakDC.ar(source=sig)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.3, sustain_time=4.0, release_time=0.7
            ),
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=0.5))

    fbsine_def = builder.build(name="fbsine")
    print(f"SynthDef '{fbsine_def.name}' compiled: {len(fbsine_def.compile())} bytes")

    # -- Boot and play --------------------------------------------------------
    with Server(Options(verbosity=0)) as server:
        henon_def.send(server)
        lorenz_def.send(server)
        fbsine_def.send(server)
        time.sleep(0.1)

        # Play each in sequence
        print("1. Henon map: 'a' sweeping 1.0 -> 1.4 (stable to chaotic)...")
        server.synth("henon", amplitude=0.25)
        time.sleep(5.0)

        print("2. Lorenz attractor: 'r' wandering around 28 (strange attractor)...")
        server.synth("lorenz", amplitude=0.2)
        time.sleep(6.0)

        print("3. FBSine: feedback 0.01 -> 1.5 (tonal to chaotic)...")
        server.synth("fbsine", amplitude=0.2)
        time.sleep(6.0)

    print("Done.")


if __name__ == "__main__":
    main()
