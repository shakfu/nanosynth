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

from nanosynth import OscMessage, Options, find_ugen_plugins_path
from nanosynth._scsynth import (
    world_new,
    world_open_udp,
    world_send_packet,
    world_wait_for_quit,
)
from nanosynth.synthdef import SynthDefBuilder
from nanosynth.ugens import Dust, Out, Pan2, Pluck, WhiteNoise


def _options_kwargs():
    opts = Options(verbosity=0)
    kwargs = {
        "num_audio_bus_channels": opts.audio_bus_channel_count,
        "num_input_bus_channels": opts.input_bus_channel_count,
        "num_output_bus_channels": opts.output_bus_channel_count,
        "num_control_bus_channels": opts.control_bus_channel_count,
        "block_size": opts.block_size,
        "num_buffers": opts.buffer_count,
        "max_nodes": opts.maximum_node_count,
        "max_graph_defs": opts.maximum_synthdef_count,
        "max_wire_bufs": opts.wire_buffer_count,
        "num_rgens": opts.random_number_generator_count,
        "max_logins": opts.maximum_logins,
        "realtime_memory_size": opts.memory_size,
        "load_graph_defs": 0,
        "memory_locking": False,
        "realtime": True,
        "verbosity": opts.verbosity,
        "rendezvous": False,
        "shared_memory_id": opts.port,
    }
    plugins = find_ugen_plugins_path()
    if plugins:
        kwargs["ugen_plugins_path"] = str(plugins)
    return kwargs


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
    world = world_new(**_options_kwargs())
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
