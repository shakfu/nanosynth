"""
05_pluck.py -- Karplus-Strong plucked string.

Uses the Pluck UGen (Karplus-Strong algorithm): a burst of noise is fed
into a tuned delay line with feedback to simulate a plucked string.
Dust generates random trigger impulses, producing an evolving plucked
texture at different pitches.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import os
import time

from nanosynth import OscMessage, Options
from nanosynth.scsynth import _options_to_world_kwargs
from nanosynth._scsynth import (
    world_new,
    world_open_udp,
    world_send_packet,
    world_wait_for_quit,
)
from nanosynth.synthdef import SynthDefBuilder
from nanosynth.ugens import Dust, Out, Pan2, Pluck, WhiteNoise


def send(world, *args):
    world_send_packet(world, OscMessage(*args).to_datagram())


def main():
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
    synthdef_bytes = synthdef.compile()
    print(f"SynthDef '{synthdef.name}' compiled: {len(synthdef_bytes)} bytes")

    # -- Boot and play --------------------------------------------------------
    world = world_new(
        **_options_to_world_kwargs(Options(verbosity=0, load_synthdefs=False))
    )
    world_open_udp(world, "127.0.0.1", 57110)
    print("Embedded scsynth booted.")

    send(world, "/g_new", 1, 0, 0)
    send(world, "/d_recv", synthdef_bytes)
    time.sleep(0.1)

    # Layer several plucked strings at different pitches
    notes = [
        (196.00, -0.3, 1000),  # G3, panned left
        (261.63, 0.0, 1001),  # C4, center
        (329.63, 0.3, 1002),  # E4, panned right
    ]
    print("Playing layered plucked strings (5s)...")
    for freq, pan, node_id in notes:
        send(
            world,
            "/s_new",
            "pluck",
            node_id,
            0,
            1,
            "frequency",
            freq,
            "decay",
            3.0,
            "coef",
            0.2,
            "density",
            1.5,
            "amplitude",
            0.35,
        )
        time.sleep(0.2)

    time.sleep(5.0)

    # Free nodes and quit
    for _, _, node_id in notes:
        send(world, "/n_free", node_id)
    time.sleep(0.1)

    send(world, "/quit")
    world_wait_for_quit(world, False)
    print("Done.")
    import sys

    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
