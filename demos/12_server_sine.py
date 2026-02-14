"""
12_server_sine.py -- Hello sine wave (Server API).

Same sound as 01_sine.py, but uses the high-level Server class and
SynthDef.play() instead of raw _scsynth / OSC calls. Compare the two
scripts to see the boilerplate reduction.

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
    print(synthdef.dump_ugens())

    # -- Boot, play, quit -- all via Server context manager -------------------
    with Server(Options(verbosity=0, load_synthdefs=False)) as server:
        print(f"\n{server!r}")

        # Self-freeing synth: managed_synth guarantees cleanup even if the
        # envelope hasn't finished (e.g. on KeyboardInterrupt).
        with server.managed_synth("sine", frequency=440.0, amplitude=0.3) as node:
            print(f"Playing 440 Hz sine (node {node}) for 2 seconds...")
            synthdef.send(server)
            time.sleep(0.1)
            server.free(node)

            # Re-create via play() shorthand
            node2 = synthdef.play(server, frequency=440.0, amplitude=0.3)
            print(f"Playing again via SynthDef.play() (node {node2})...")
            time.sleep(2.5)

    print("Done.")


if __name__ == "__main__":
    main()
