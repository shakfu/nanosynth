"""
06_ringmod.py -- Ring modulation and amplitude modulation.

Two SynthDefs demonstrating different modulation techniques:
  1. Ring modulation: carrier * modulator (bipolar, produces sum and
     difference frequencies)
  2. Amplitude modulation: carrier * (modulator * 0.5 + 0.5) (unipolar,
     retains carrier fundamental with sidebands)

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import LFTri, Out, Pan2, SinOsc, XLine


def main() -> None:
    # -- SynthDef 1: ring modulation with sweeping mod frequency --------------
    with SynthDefBuilder(carrier_freq=440.0, amplitude=0.3) as builder:
        carrier = SinOsc.ar(frequency=builder["carrier_freq"])
        # Sweep modulator frequency from 2 Hz (tremolo) up to 300 Hz (sidebands)
        mod_freq = XLine.kr(
            start=2.0,
            stop=300.0,
            duration=4.0,
            done_action=DoneAction.FREE_SYNTH,
        )
        modulator = LFTri.ar(frequency=mod_freq)
        sig = carrier * modulator * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=-0.4))

    ring_def = builder.build(name="ring_mod")
    print(f"SynthDef '{ring_def.name}' compiled: {len(ring_def.compile())} bytes")

    # -- SynthDef 2: amplitude modulation with sweeping mod frequency ---------
    with SynthDefBuilder(carrier_freq=440.0, amplitude=0.3) as builder:
        carrier = SinOsc.ar(frequency=builder["carrier_freq"])
        mod_freq = XLine.kr(
            start=2.0,
            stop=300.0,
            duration=4.0,
            done_action=DoneAction.FREE_SYNTH,
        )
        # Unipolar modulator: 0..1 instead of -1..1
        modulator = SinOsc.ar(frequency=mod_freq) * 0.5 + 0.5
        sig = carrier * modulator * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=0.4))

    am_def = builder.build(name="am_mod")
    print(f"SynthDef '{am_def.name}' compiled: {len(am_def.compile())} bytes")

    # -- Boot and play --------------------------------------------------------
    with Server(Options(verbosity=0)) as server:
        ring_def.send(server)
        am_def.send(server)
        time.sleep(0.1)

        # Ring mod on left, AM on right -- hear the difference
        print("Ring modulation (left) -- sweeping mod freq 2->300 Hz (4s)...")
        server.synth("ring_mod", carrier_freq=440.0, amplitude=0.35)
        time.sleep(0.5)

        print("Amplitude modulation (right) -- same sweep...")
        server.synth("am_mod", carrier_freq=440.0, amplitude=0.35)
        time.sleep(4.5)

    print("Done.")


if __name__ == "__main__":
    main()
