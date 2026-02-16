"""
01_sine.py -- Hello sine wave (supernova).

Same sound as scsynth/01_sine.py, but uses supernova (parallel DSP engine)
instead of scsynth.

Requires:
  - nanosynth built with embedded supernova (NANOSYNTH_EMBED_SUPERNOVA=ON)
"""

import time

from nanosynth import EmbeddedSupernovaProtocol, Options, Server
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

    # -- Boot supernova, play, quit -------------------------------------------
    with Server(
        Options(verbosity=0, load_synthdefs=False), protocol=EmbeddedSupernovaProtocol()
    ) as server:
        synthdef.send(server)
        time.sleep(0.1)

        node = server.synth("sine", frequency=440.0, amplitude=0.3)
        print(f"Playing 440 Hz sine (node {node}) for 2 seconds...")
        time.sleep(2.5)

    print("Done.")


if __name__ == "__main__":
    main()
