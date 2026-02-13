"""
02_subtractive.py -- Filtered saw + resonant noise.

Two self-freeing SynthDefs:
  1. Saw through a sweeping LPF (XLine modulating cutoff)
  2. WhiteNoise through RLPF with LFO-modulated cutoff

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
from nanosynth.ugens import LFNoise1, LPF, Out, Pan2, RLPF, Saw, WhiteNoise, XLine


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
    # -- SynthDef 1: saw -> sweeping LPF (self-freeing) -----------------------
    with SynthDefBuilder(frequency=110.0, amplitude=0.4) as builder:
        sig = Saw.ar(frequency=builder["frequency"])
        cutoff = XLine.kr(
            start=8000.0,
            stop=200.0,
            duration=3.0,
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = LPF.ar(source=sig, frequency=cutoff)
        sig = sig * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    saw_def = builder.build(name="filtered_saw")
    saw_bytes = saw_def.compile()
    print(f"SynthDef '{saw_def.name}' compiled: {len(saw_bytes)} bytes")

    # -- SynthDef 2: noise -> resonant LPF with LFO --------------------------
    with SynthDefBuilder(amplitude=0.15) as builder:
        sig = WhiteNoise.ar()
        lfo = LFNoise1.kr(frequency=4.0)
        # Map LFO from [-1,1] to [200, 4000]
        cutoff = lfo * 1900.0 + 2100.0
        sig = RLPF.ar(source=sig, frequency=cutoff, reciprocal_of_q=0.1)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.5, sustain_time=2.0, release_time=0.5
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    noise_def = builder.build(name="resonant_noise")
    noise_bytes = noise_def.compile()
    print(f"SynthDef '{noise_def.name}' compiled: {len(noise_bytes)} bytes")

    # -- Boot and play --------------------------------------------------------
    world = world_new(**_options_kwargs())
    world_open_udp(world, "127.0.0.1", 57110)
    print("Embedded scsynth booted.")

    # Create default group (group 1 inside root group 0)
    send(world, "/g_new", 1, 0, 0)

    send(world, "/d_recv", saw_bytes)
    send(world, "/d_recv", noise_bytes)
    time.sleep(0.1)

    # Play filtered saw
    print("Playing filtered saw (3s sweep)...")
    send(world, "/s_new", "filtered_saw", 1000, 0, 1)
    time.sleep(1.5)

    # Layer resonant noise on top
    print("Layering resonant noise (3s)...")
    send(world, "/s_new", "resonant_noise", 1001, 0, 1)
    time.sleep(3.5)

    send(world, "/quit")
    world_wait_for_quit(world, False)
    print("Done.")
    import sys

    sys.stdout.flush()
    os._exit(0)  # skip C++ global destructors (CoreAudio teardown crash)


if __name__ == "__main__":
    main()
