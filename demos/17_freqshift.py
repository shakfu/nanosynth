"""
17_freqshift.py -- Frequency shifting and Hilbert transforms.

Bode frequency shifting moves all partials by a fixed Hz amount (unlike
pitch shifting which scales them). This breaks harmonic relationships,
producing bell-like or metallic timbres from harmonic inputs.

Sections:
  1. Slow sweep -- a saw wave with FreqShift sweeping 0 -> 100 Hz,
     gradually detuning the harmonic series into inharmonicity
  2. Barberpole phaser -- two frequency-shifted copies of a signal
     mixed with the original, shifted by +/- small amounts, creating
     an endlessly rising/falling phaser effect
  3. Ring mod territory -- larger shift amounts approaching ring
     modulation (FreqShift at high offset is single-sideband ring mod)

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import (
    FreqShift,
    LFNoise1,
    LPF,
    Line,
    Out,
    Pan2,
    Saw,
    SinOsc,
)


def main() -> None:
    # -- SynthDef 1: slow frequency shift sweep -------------------------------
    with SynthDefBuilder(frequency=220.0, amplitude=0.3) as builder:
        sig = Saw.ar(frequency=builder["frequency"])
        # Sweep shift amount from 0 (harmonic) to 100 Hz (inharmonic)
        shift = Line.kr(start=0.0, stop=100.0, duration=6.0)
        sig = FreqShift.ar(source=sig, frequency=shift)
        sig = LPF.ar(source=sig, frequency=6000.0)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.3, sustain_time=5.5, release_time=1.0
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    sweep_def = builder.build(name="freqshift_sweep")
    print(f"SynthDef '{sweep_def.name}' compiled: {len(sweep_def.compile())} bytes")

    # -- SynthDef 2: barberpole phaser ----------------------------------------
    with SynthDefBuilder(frequency=330.0, rate=0.5, amplitude=0.25) as builder:
        sig = Saw.ar(frequency=builder["frequency"])
        sig = sig + Saw.ar(frequency=builder["frequency"] * 0.501) * 0.5

        # Two opposite shifts create an endlessly rising/falling effect
        shift_amount = builder["rate"]
        up = FreqShift.ar(source=sig, frequency=shift_amount)
        down = FreqShift.ar(source=sig, frequency=shift_amount * -1.0)

        # Mix original + shifted for phaser-like interference
        mixed = sig * 0.5 + up * 0.3 + down * 0.3
        mixed = LPF.ar(source=mixed, frequency=5000.0)

        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.5, sustain_time=5.0, release_time=1.0
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        mixed = mixed * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=mixed))

    phaser_def = builder.build(name="barberpole")
    print(f"SynthDef '{phaser_def.name}' compiled: {len(phaser_def.compile())} bytes")

    # -- SynthDef 3: single-sideband ring modulation --------------------------
    with SynthDefBuilder(frequency=440.0, amplitude=0.2) as builder:
        sig = SinOsc.ar(frequency=builder["frequency"])
        # LFO-modulated shift for evolving metallic texture
        shift = LFNoise1.kr(frequency=0.3) * 200.0 + 300.0
        sig = FreqShift.ar(source=sig, frequency=shift)
        sig = LPF.ar(source=sig, frequency=8000.0)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.3, sustain_time=4.0, release_time=1.0
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    ringmod_def = builder.build(name="ssb_ringmod")
    print(f"SynthDef '{ringmod_def.name}' compiled: {len(ringmod_def.compile())} bytes")

    # -- Boot and play --------------------------------------------------------
    with Server(Options(verbosity=0, load_synthdefs=False)) as server:
        sweep_def.send(server)
        phaser_def.send(server)
        ringmod_def.send(server)
        time.sleep(0.1)

        print("\n1. Frequency shift sweep: 0 -> 100 Hz (harmonic to inharmonic)...")
        sweep_def.play(server, frequency=220.0, amplitude=0.3)
        time.sleep(7.5)

        print("2. Barberpole phaser: endless rising/falling...")
        phaser_def.play(server, frequency=330.0, rate=0.5, amplitude=0.25)
        time.sleep(7.0)

        print("3. Single-sideband ring mod: wandering metallic texture...")
        ringmod_def.play(server, frequency=440.0, amplitude=0.25)
        time.sleep(6.0)

        time.sleep(0.5)

    print("Done.")


if __name__ == "__main__":
    main()
