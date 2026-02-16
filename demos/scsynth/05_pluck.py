"""
05_pluck.py -- Karplus-Strong plucked string.

Uses the Pluck UGen (Karplus-Strong algorithm): a burst of noise is fed
into a tuned delay line with feedback to simulate a plucked string.
Dust generates random trigger impulses, producing an evolving plucked
texture at different pitches.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.synthdef import SynthDefBuilder
from nanosynth.ugens import Dust, Out, Pan2, Pluck, WhiteNoise


def main() -> None:
    # -- SynthDef: plucked string with random triggers ------------------------
    with SynthDefBuilder(
        frequency=440.0, decay=4.0, coef=0.3, density=2.0, amplitude=0.5
    ) as builder:
        trig = Dust.ar(density=builder["density"])
        sig = Pluck.ar(
            source=WhiteNoise.ar(),
            trigger=trig,
            maximum_delay_time=1.0 / 60.0,  # lowest pitch ~60 Hz
            delay_time=1.0 / builder["frequency"],
            decay_time=builder["decay"],
            coefficient=builder["coef"],
        )
        sig = sig * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    synthdef = builder.build(name="pluck")
    print(f"SynthDef '{synthdef.name}' compiled: {len(synthdef.compile())} bytes")

    # -- Boot and play --------------------------------------------------------
    with Server(Options(verbosity=0)) as server:
        synthdef.send(server)
        time.sleep(0.1)

        # Layer several plucked strings at different pitches
        print("Playing layered plucked strings (5s)...")
        nodes = []
        for freq in [196.00, 261.63, 329.63]:
            node = server.synth(
                "pluck",
                frequency=freq,
                decay=3.0,
                coef=0.2,
                density=1.5,
                amplitude=0.35,
            )
            nodes.append(node)
            time.sleep(0.2)

        time.sleep(5.0)

        # Free nodes
        for node in nodes:
            server.free(node)

    print("Done.")


if __name__ == "__main__":
    main()
