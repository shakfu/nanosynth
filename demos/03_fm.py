"""
03_fm.py -- FM synthesis + melody.

Two SynthDefs:
  1. FM synth with controllable carrier_freq, mod_ratio, mod_index, gate
     (uses Envelope.adsr for amplitude shaping)
  2. FM sweep with XLine-modulated index (self-freeing)

Plays a short melody with the gated FM synth, then fires a self-freeing sweep.

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
from nanosynth.ugens import Out, Pan2, SinOsc, XLine


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
    # -- SynthDef 1: gated FM synth -------------------------------------------
    with SynthDefBuilder(
        carrier_freq=440.0,
        mod_ratio=2.0,
        mod_index=3.0,
        amplitude=0.3,
        gate=1.0,
    ) as builder:
        mod_freq = builder["carrier_freq"] * builder["mod_ratio"]
        modulator = SinOsc.ar(frequency=mod_freq) * builder["mod_index"] * mod_freq
        carrier = SinOsc.ar(frequency=builder["carrier_freq"] + modulator)
        env = EnvGen.kr(
            envelope=Envelope.adsr(
                attack_time=0.01,
                decay_time=0.1,
                sustain=0.7,
                release_time=0.3,
            ),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = carrier * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    fm_def = builder.build(name="fm_synth")
    fm_bytes = fm_def.compile()
    print(f"SynthDef '{fm_def.name}' compiled: {len(fm_bytes)} bytes")

    # -- SynthDef 2: self-freeing FM sweep ------------------------------------
    with SynthDefBuilder(carrier_freq=200.0, mod_ratio=3.0, amplitude=0.25) as builder:
        mod_index = XLine.kr(
            start=10.0,
            stop=0.1,
            duration=4.0,
            done_action=DoneAction.FREE_SYNTH,
        )
        mod_freq = builder["carrier_freq"] * builder["mod_ratio"]
        modulator = SinOsc.ar(frequency=mod_freq) * mod_index * mod_freq
        carrier = SinOsc.ar(frequency=builder["carrier_freq"] + modulator)
        sig = carrier * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    sweep_def = builder.build(name="fm_sweep")
    sweep_bytes = sweep_def.compile()
    print(f"SynthDef '{sweep_def.name}' compiled: {len(sweep_bytes)} bytes")

    # -- Boot and play --------------------------------------------------------
    world = world_new(**_options_kwargs())
    world_open_udp(world, "127.0.0.1", 57110)
    print("Embedded scsynth booted.")

    # Create default group (group 1 inside root group 0)
    send(world, "/g_new", 1, 0, 0)

    send(world, "/d_recv", fm_bytes)
    send(world, "/d_recv", sweep_bytes)
    time.sleep(0.1)

    # Play a short melody with the gated FM synth
    melody = [
        (261.63, 0.3),  # C4
        (293.66, 0.3),  # D4
        (329.63, 0.3),  # E4
        (349.23, 0.3),  # F4
        (392.00, 0.5),  # G4
        (440.00, 0.5),  # A4
        (493.88, 0.5),  # B4
        (523.25, 0.8),  # C5
    ]

    print("Playing FM melody...")
    node_id = 1000
    for freq, dur in melody:
        send(
            world,
            "/s_new",
            "fm_synth",
            node_id,
            0,
            1,
            "carrier_freq",
            freq,
            "mod_ratio",
            2.0,
            "mod_index",
            3.0,
            "amplitude",
            0.25,
        )
        time.sleep(dur)
        # Release the gate to trigger the envelope release
        send(world, "/n_set", node_id, "gate", 0.0)
        time.sleep(0.05)
        node_id += 1

    time.sleep(0.5)

    # Fire the self-freeing FM sweep
    print("Playing FM sweep (4s)...")
    send(world, "/s_new", "fm_sweep", 2000, 0, 1, "carrier_freq", 150.0)
    time.sleep(4.5)

    send(world, "/quit")
    world_wait_for_quit(world, False)
    print("Done.")
    import sys

    sys.stdout.flush()
    os._exit(0)  # skip C++ global destructors (CoreAudio teardown crash)


if __name__ == "__main__":
    main()
