"""
01_sine.py -- Hello sine wave.

Builds a SynthDef with SinOsc -> Pan2 -> Out, boots an embedded scsynth,
sends the SynthDef via /d_recv, creates a synth with /s_new, waits, then
cleans up with /quit.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
  - SC_PLUGIN_PATH set to the SuperCollider plugins directory
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
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import Out, Pan2, SinOsc


def _options_kwargs():
    """Build world_new kwargs from default Options."""
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
    """Send an OSC message to the embedded world."""
    world_send_packet(world, OscMessage(*args).to_datagram())


def main():
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
    synthdef_bytes = synthdef.compile()
    print(f"SynthDef '{synthdef.name}' compiled: {len(synthdef_bytes)} bytes")

    # -- Boot embedded scsynth ------------------------------------------------
    world = world_new(**_options_kwargs())
    world_open_udp(world, "127.0.0.1", 57110)
    print("Embedded scsynth booted.")

    # Create default group (group 1 inside root group 0)
    send(world, "/g_new", 1, 0, 0)

    # -- Send SynthDef and create synth ---------------------------------------
    send(world, "/d_recv", synthdef_bytes)
    time.sleep(0.1)

    send(world, "/s_new", "sine", 1000, 0, 1, "frequency", 440.0, "amplitude", 0.3)
    print("Playing 440 Hz sine for 2 seconds...")
    time.sleep(2.5)

    # -- Cleanup --------------------------------------------------------------
    send(world, "/quit")
    world_wait_for_quit(world, False)
    print("Done.")
    import sys

    sys.stdout.flush()
    os._exit(0)  # skip C++ global destructors (CoreAudio teardown crash)


if __name__ == "__main__":
    main()
