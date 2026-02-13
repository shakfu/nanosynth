"""
10_chaos.py -- Chaotic oscillators as sound sources.

Explores three chaotic generators at audio rate:
  1. Henon map -- classic 2D chaotic attractor, harsh and gritty
  2. Lorenz system -- 3-parameter strange attractor, rich texture
  3. FBSine -- feedback sine oscillator, from tonal to noisy

Each is filtered and enveloped. Parameters are swept with XLine/LFNoise1
to explore different regimes of each chaotic system.

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
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import (
    FBSineC,
    HenonC,
    LFNoise1,
    LPF,
    LeakDC,
    LorenzL,
    Out,
    Pan2,
    XLine,
)


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
    # -- SynthDef 1: Henon map ------------------------------------------------
    with SynthDefBuilder(amplitude=0.2) as builder:
        # Sweep the 'a' parameter from stable to chaotic
        a = XLine.kr(
            start=1.0, stop=1.4, duration=4.0, done_action=DoneAction.FREE_SYNTH
        )
        sig = HenonC.ar(frequency=8000.0, a=a, b=0.3)
        sig = LPF.ar(source=sig, frequency=3000.0)
        sig = LeakDC.ar(source=sig)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.3, sustain_time=3.0, release_time=0.7
            ),
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=-0.5))

    henon_def = builder.build(name="henon")
    henon_bytes = henon_def.compile()
    print(f"SynthDef '{henon_def.name}' compiled: {len(henon_bytes)} bytes")

    # -- SynthDef 2: Lorenz attractor -----------------------------------------
    with SynthDefBuilder(amplitude=0.15) as builder:
        # Slowly modulate the 'r' parameter (rho) around the chaotic regime
        r = LFNoise1.kr(frequency=0.3) * 10.0 + 28.0
        sig = LorenzL.ar(
            frequency=11025.0,
            s=10.0,
            r=r,
            b=2.667,
            h=0.05,
        )
        sig = LPF.ar(source=sig, frequency=4000.0)
        sig = LeakDC.ar(source=sig)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.5, sustain_time=4.0, release_time=1.0
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=0.0))

    lorenz_def = builder.build(name="lorenz")
    lorenz_bytes = lorenz_def.compile()
    print(f"SynthDef '{lorenz_def.name}' compiled: {len(lorenz_bytes)} bytes")

    # -- SynthDef 3: FBSine (feedback sine) -----------------------------------
    with SynthDefBuilder(amplitude=0.15) as builder:
        # Sweep feedback amount from tonal to chaotic
        fb = XLine.kr(
            start=0.01, stop=1.5, duration=5.0, done_action=DoneAction.FREE_SYNTH
        )
        sig = FBSineC.ar(
            frequency=8000.0,
            im=1.0,
            fb=fb,
            a=1.1,
            c=0.5,
        )
        sig = LPF.ar(source=sig, frequency=5000.0)
        sig = LeakDC.ar(source=sig)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.3, sustain_time=4.0, release_time=0.7
            ),
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=0.5))

    fbsine_def = builder.build(name="fbsine")
    fbsine_bytes = fbsine_def.compile()
    print(f"SynthDef '{fbsine_def.name}' compiled: {len(fbsine_bytes)} bytes")

    # -- Boot and play --------------------------------------------------------
    world = world_new(**_options_kwargs())
    world_open_udp(world, "127.0.0.1", 57110)
    print("Embedded scsynth booted.")

    send(world, "/g_new", 1, 0, 0)
    send(world, "/d_recv", henon_bytes)
    send(world, "/d_recv", lorenz_bytes)
    send(world, "/d_recv", fbsine_bytes)
    time.sleep(0.1)

    # Play each in sequence
    print("1. Henon map: 'a' sweeping 1.0 -> 1.4 (stable to chaotic)...")
    send(world, "/s_new", "henon", 1000, 0, 1, "amplitude", 0.25)
    time.sleep(5.0)

    print("2. Lorenz attractor: 'r' wandering around 28 (strange attractor)...")
    send(world, "/s_new", "lorenz", 1001, 0, 1, "amplitude", 0.2)
    time.sleep(6.0)

    print("3. FBSine: feedback 0.01 -> 1.5 (tonal to chaotic)...")
    send(world, "/s_new", "fbsine", 1002, 0, 1, "amplitude", 0.2)
    time.sleep(6.0)

    send(world, "/quit")
    world_wait_for_quit(world, False)
    print("Done.")
    import sys

    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
