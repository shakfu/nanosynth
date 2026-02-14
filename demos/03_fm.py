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
from nanosynth.ugens import Out, Pan2, SinOsc, XLine


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
    world = world_new(
        **_options_to_world_kwargs(Options(verbosity=0, load_synthdefs=False))
    )
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
