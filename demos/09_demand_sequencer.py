"""
09_demand_sequencer.py -- Demand-rate pattern sequencing.

Uses demand UGens (Dseq, Drand) to sequence pitch and rhythm entirely
server-side, without any host scheduling. Two voices:
  1. A bass line using Dseq (deterministic repeating pattern)
  2. A melodic voice using Drand (random note selection from a scale)

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
    Decay2,
    Drand,
    Dseq,
    Duty,
    Impulse,
    LPF,
    Out,
    Pan2,
    Saw,
    SinOsc,
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
    # -- SynthDef 1: deterministic bass sequence (Dseq) -----------------------
    with SynthDefBuilder(amplitude=0.3) as builder:
        # E1 - G1 - A1 - B1 bass pattern, 4 repeats
        freq = Duty.kr(
            duration=0.5,
            level=Dseq.dr(
                repeats=4,
                sequence=[82.41, 98.00, 110.00, 123.47],
            ),
        )
        sig = Saw.ar(frequency=freq)
        sig = LPF.ar(source=sig, frequency=400.0)

        # Retriggered amplitude envelope synced to the step clock
        tick = Impulse.kr(frequency=2.0)  # 0.5s period
        amp_env = Decay2.kr(source=tick, attack_time=0.01, decay_time=0.4)

        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.01, sustain_time=7.9, release_time=0.1
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * amp_env * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=-0.3))

    bass_def = builder.build(name="bass_seq")
    bass_bytes = bass_def.compile()
    print(f"SynthDef '{bass_def.name}' compiled: {len(bass_bytes)} bytes")

    # -- SynthDef 2: random melodic voice (Drand) -----------------------------
    with SynthDefBuilder(amplitude=0.2) as builder:
        # Random notes from A minor pentatonic, faster rate
        freq = Duty.kr(
            duration=0.25,
            level=Drand.dr(
                repeats=32,
                sequence=[
                    440.0,
                    523.25,
                    587.33,
                    659.26,
                    783.99,  # A4-G5 pentatonic
                ],
            ),
        )
        sig = SinOsc.ar(frequency=freq)

        # Snappy per-note envelope
        tick = Impulse.kr(frequency=4.0)  # 0.25s period
        amp_env = Decay2.kr(source=tick, attack_time=0.005, decay_time=0.15)

        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.01, sustain_time=7.9, release_time=0.1
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * amp_env * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=0.3))

    melody_def = builder.build(name="melody_seq")
    melody_bytes = melody_def.compile()
    print(f"SynthDef '{melody_def.name}' compiled: {len(melody_bytes)} bytes")

    # -- Boot and play --------------------------------------------------------
    world = world_new(**_options_kwargs())
    world_open_udp(world, "127.0.0.1", 57110)
    print("Embedded scsynth booted.")

    send(world, "/g_new", 1, 0, 0)
    send(world, "/d_recv", bass_bytes)
    send(world, "/d_recv", melody_bytes)
    time.sleep(0.1)

    print("Playing demand-rate sequencer (8s)...")
    print("  Bass (left): Dseq deterministic pattern")
    print("  Melody (right): Drand random pentatonic")
    send(world, "/s_new", "bass_seq", 1000, 0, 1, "amplitude", 0.35)
    send(world, "/s_new", "melody_seq", 1001, 0, 1, "amplitude", 0.25)
    time.sleep(9.0)

    send(world, "/quit")
    world_wait_for_quit(world, False)
    print("Done.")
    import sys

    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
