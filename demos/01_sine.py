"""
01_sine.py -- Hello sine wave.

Builds a SynthDef with SinOsc -> Pan2 -> Out, boots an embedded scsynth,
sends the SynthDef via /d_recv, creates a synth with /s_new, waits, then
cleans up with /quit.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
  - SC_PLUGIN_PATH set to the SuperCollider plugins directory
"""

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
from nanosynth.ugens import Out, Pan2, SinOsc


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
    world = world_new(
        **_options_to_world_kwargs(Options(verbosity=0, load_synthdefs=False))
    )
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


if __name__ == "__main__":
    main()
