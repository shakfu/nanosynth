"""
04_additive.py -- Additive synthesis.

Builds a tone by summing sine partials with decreasing amplitudes.
An LFO slowly modulates the balance between odd and even harmonics,
creating a timbral shift from hollow (odd-only, like a square wave)
to bright (all harmonics).

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
from nanosynth.ugens import LFTri, Out, Pan2, SinOsc


def send(world, *args):
    world_send_packet(world, OscMessage(*args).to_datagram())


def main():
    # -- SynthDef: additive with LFO-morphing harmonics -----------------------
    with SynthDefBuilder(frequency=200.0, amplitude=0.3) as builder:
        freq = builder["frequency"]

        # LFO: 0..1 controls even-harmonic level (odd harmonics always present)
        even_mix = LFTri.kr(frequency=0.15) * 0.5 + 0.5

        # Odd harmonics (1, 3, 5, 7)
        sig = SinOsc.ar(frequency=freq) * 1.0
        sig = sig + SinOsc.ar(frequency=freq * 3.0) * 0.33
        sig = sig + SinOsc.ar(frequency=freq * 5.0) * 0.2
        sig = sig + SinOsc.ar(frequency=freq * 7.0) * 0.14

        # Even harmonics (2, 4, 6) scaled by LFO
        sig = sig + SinOsc.ar(frequency=freq * 2.0) * 0.5 * even_mix
        sig = sig + SinOsc.ar(frequency=freq * 4.0) * 0.25 * even_mix
        sig = sig + SinOsc.ar(frequency=freq * 6.0) * 0.17 * even_mix

        sig = sig * 0.2  # normalize headroom
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.5, sustain_time=5.0, release_time=1.0
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    synthdef = builder.build(name="additive")
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

    print("Playing additive synthesis with morphing harmonics (6.5s)...")
    send(world, "/s_new", "additive", 1000, 0, 1, "frequency", 150.0, "amplitude", 0.4)
    time.sleep(7.0)

    send(world, "/quit")
    world_wait_for_quit(world, False)
    print("Done.")
    import sys

    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
