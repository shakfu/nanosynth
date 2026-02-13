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

import os
import time

from nanosynth import OscMessage, Options, find_ugen_plugins_path
from nanosynth._scsynth import (
    world_new,
    world_open_udp,
    world_send_packet,
    world_wait_for_quit,
)
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import LFTri, Out, Pan2, SinOsc, XLine


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
    ring_bytes = ring_def.compile()
    print(f"SynthDef '{ring_def.name}' compiled: {len(ring_bytes)} bytes")

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
    am_bytes = am_def.compile()
    print(f"SynthDef '{am_def.name}' compiled: {len(am_bytes)} bytes")

    # -- Boot and play --------------------------------------------------------
    world = world_new(**_options_kwargs())
    world_open_udp(world, "127.0.0.1", 57110)
    print("Embedded scsynth booted.")

    send(world, "/g_new", 1, 0, 0)
    send(world, "/d_recv", ring_bytes)
    send(world, "/d_recv", am_bytes)
    time.sleep(0.1)

    # Ring mod on left, AM on right -- hear the difference
    print("Ring modulation (left) -- sweeping mod freq 2->300 Hz (4s)...")
    send(
        world,
        "/s_new",
        "ring_mod",
        1000,
        0,
        1,
        "carrier_freq",
        440.0,
        "amplitude",
        0.35,
    )
    time.sleep(0.5)

    print("Amplitude modulation (right) -- same sweep...")
    send(
        world, "/s_new", "am_mod", 1001, 0, 1, "carrier_freq", 440.0, "amplitude", 0.35
    )
    time.sleep(4.5)

    send(world, "/quit")
    world_wait_for_quit(world, False)
    print("Done.")
    import sys

    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
