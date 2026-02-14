"""
11_stereo_pad.py -- Lush detuned stereo pad with MoogFF filter.

Builds a thick stereo pad by layering detuned Pulse oscillators with
varying widths, run through a MoogFF (Moog-style ladder filter) with
an LFO-modulated cutoff. Demonstrates:
  - Detuning for stereo width
  - Pulse width as a timbral control
  - MoogFF resonant filter
  - Slow LFO modulation at control rate
  - Multi-voice layering within a single SynthDef

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
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import LFNoise2, MoogFF, Out, Pulse


def send(world, *args):
    world_send_packet(world, OscMessage(*args).to_datagram())


def main():
    # -- SynthDef: detuned stereo pad with MoogFF -----------------------------
    with SynthDefBuilder(
        frequency=220.0,
        detune=0.8,
        cutoff=1200.0,
        resonance=2.5,
        amplitude=0.3,
        gate=1.0,
    ) as builder:
        freq = builder["frequency"]
        det = builder["detune"]

        # Left channel: two detuned pulse oscillators
        left = Pulse.ar(frequency=freq - det, width=0.3) * 0.5
        left = left + Pulse.ar(frequency=freq - det * 2.0, width=0.5) * 0.5

        # Right channel: two detuned pulse oscillators (opposite detune)
        right = Pulse.ar(frequency=freq + det, width=0.3) * 0.5
        right = right + Pulse.ar(frequency=freq + det * 2.0, width=0.5) * 0.5

        # Slowly wandering cutoff modulation
        lfo = LFNoise2.kr(frequency=0.2)
        cutoff = builder["cutoff"] + lfo * 600.0

        # MoogFF ladder filter on each channel
        left = MoogFF.ar(source=left, frequency=cutoff, gain=builder["resonance"])
        right = MoogFF.ar(source=right, frequency=cutoff, gain=builder["resonance"])

        # ADSR envelope with gate control
        env = EnvGen.kr(
            envelope=Envelope.adsr(
                attack_time=1.5,
                decay_time=0.5,
                sustain=0.8,
                release_time=2.0,
            ),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        left = left * env * builder["amplitude"]
        right = right * env * builder["amplitude"]
        Out.ar(bus=0, source=[left, right])

    synthdef = builder.build(name="stereo_pad")
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

    # Play a chord progression: Am -> F -> C -> G
    chords = [
        (220.00, "Am"),  # A3
        (174.61, "F"),  # F3
        (261.63, "C"),  # C4
        (196.00, "G"),  # G3
    ]

    print("Playing pad chord progression...")
    node_id = 1000
    for freq, name in chords:
        print(f"  {name} ({freq:.0f} Hz)...")
        send(
            world,
            "/s_new",
            "stereo_pad",
            node_id,
            0,
            1,
            "frequency",
            freq,
            "detune",
            0.7,
            "cutoff",
            1000.0,
            "resonance",
            2.0,
            "amplitude",
            0.25,
        )
        time.sleep(3.0)
        # Release the gate
        send(world, "/n_set", node_id, "gate", 0.0)
        time.sleep(1.0)
        node_id += 1

    # Let the last release tail finish
    time.sleep(2.0)

    send(world, "/quit")
    world_wait_for_quit(world, False)
    print("Done.")
    import sys

    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
