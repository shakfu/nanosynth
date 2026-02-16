"""
01_sine.py -- Hello sine wave.

Builds a SynthDef with SinOsc -> Pan2 -> Out, boots an embedded scsynth,
sends the SynthDef, creates a synth, waits, then cleans up.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import Out, Pan2, SinOsc


def main() -> None:
    # -- Build SynthDef -------------------------------------------------------
    with SynthDefBuilder(frequency=440.0, amplitude=0.3) as builder:
        sig = SinOsc.ar(frequency=builder["frequency"])
        sig = sig * builder["amplitude"]
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.1, sustain_time=1.8, release_time=0.1
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    synthdef = builder.build(name="sine")
    print(f"SynthDef '{synthdef.name}' compiled: {len(synthdef.compile())} bytes")

    # -- Boot, play, quit -----------------------------------------------------
    with Server(Options(verbosity=0)) as server:
        synthdef.send(server)
        time.sleep(0.1)

        node = server.synth("sine", frequency=440.0, amplitude=0.3)
        print(f"Playing 440 Hz sine (node {node}) for 2 seconds...")
        time.sleep(2.5)

    print("Done.")


if __name__ == "__main__":
    main()
