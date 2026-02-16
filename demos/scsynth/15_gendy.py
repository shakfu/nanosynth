"""
15_gendy.py -- Stochastic synthesis with Gendy.

Iannis Xenakis' Dynamic Stochastic Synthesis generates waveforms by
randomly walking the breakpoints of a waveform. The three Gendy variants
produce different characters:
  1. Gendy1 -- raw stochastic oscillator, frequency swept via XLine
  2. Gendy2 -- adds a/c parameters for Lehmer random number shaping,
     producing more structured timbral variation
  3. Gendy3 -- same parameter set as Gendy1 but produces a different
     internal distribution, yielding a distinct stochastic character

Each is filtered and enveloped to tame the extremes while preserving
the organic, living quality of the sound.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import (
    Gendy1,
    Gendy2,
    Gendy3,
    LPF,
    LeakDC,
    Out,
    Pan2,
    XLine,
)


def main() -> None:
    # -- SynthDef 1: Gendy1 -- raw stochastic oscillator ----------------------
    with SynthDefBuilder(amplitude=0.2) as builder:
        # Sweep base frequency from low growl to mid range
        freq = XLine.kr(start=80.0, stop=440.0, duration=5.0)
        sig = Gendy1.ar(
            amplitude_distribution=1,  # linear distribution for amp walks
            duration_distribution=1,  # linear distribution for dur walks
            amplitude_scale=0.5,
            duration_scale=0.5,
            min_frequency=freq,
            max_frequency=freq * 2.0,
            init_cps=12,
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
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=-0.5))

    gendy1_def = builder.build(name="gendy1")
    print(f"SynthDef '{gendy1_def.name}' compiled: {len(gendy1_def.compile())} bytes")

    # -- SynthDef 2: Gendy2 -- Lehmer-shaped stochastic -----------------------
    with SynthDefBuilder(amplitude=0.2) as builder:
        sig = Gendy2.ar(
            amplitude_distribution=3,  # Cauchy distribution -- wilder jumps
            duration_distribution=3,
            amplitude_scale=0.4,
            duration_scale=0.4,
            min_frequency=200.0,
            max_frequency=400.0,
            init_cps=16,
            a=1.17,  # Lehmer parameters
            c=0.31,
        )
        sig = LPF.ar(source=sig, frequency=3000.0)
        sig = LeakDC.ar(source=sig)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.8, sustain_time=4.0, release_time=1.0
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=0.0))

    gendy2_def = builder.build(name="gendy2")
    print(f"SynthDef '{gendy2_def.name}' compiled: {len(gendy2_def.compile())} bytes")

    # -- SynthDef 3: Gendy3 -- distinct stochastic character ------------------
    # Gendy3 uses a single frequency (no min/max), different from Gendy1/2.
    with SynthDefBuilder(amplitude=0.2) as builder:
        sig = Gendy3.ar(
            amplitude_distribution=2,  # quadratic distribution
            duration_distribution=2,
            amplitude_scale=0.3,
            duration_scale=0.3,
            frequency=220.0,
            init_cps=20,
        )
        sig = LPF.ar(source=sig, frequency=5000.0)
        sig = LeakDC.ar(source=sig)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.5, sustain_time=4.0, release_time=1.5
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=0.5))

    gendy3_def = builder.build(name="gendy3")
    print(f"SynthDef '{gendy3_def.name}' compiled: {len(gendy3_def.compile())} bytes")

    # -- Boot and play --------------------------------------------------------
    with Server(Options(verbosity=0, load_synthdefs=False)) as server:
        gendy1_def.send(server)
        gendy2_def.send(server)
        gendy3_def.send(server)
        time.sleep(0.1)

        print("\n1. Gendy1: raw stochastic sweep (80 -> 440 Hz)...")
        gendy1_def.play(server, amplitude=0.25)
        time.sleep(6.0)

        print("2. Gendy2: Lehmer-shaped, Cauchy distribution...")
        gendy2_def.play(server, amplitude=0.2)
        time.sleep(6.5)

        print("3. Gendy3: quadratic distribution, 220 Hz...")
        gendy3_def.play(server, amplitude=0.25)
        time.sleep(6.5)

        time.sleep(0.5)

    print("Done.")


if __name__ == "__main__":
    main()
