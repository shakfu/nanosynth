"""
08_resonance.py -- Resonant textures with Dust and Ringz.

Sparse random impulses (Dust) excite banks of resonant filters (Ringz)
at different frequencies, creating a shimmering bell/chime texture.
Demonstrates trigger-driven synthesis and resonant filter banks.

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
from nanosynth.ugens import Dust, HPF, LeakDC, Out, Pan2, Ringz


def send(world, *args):
    world_send_packet(world, OscMessage(*args).to_datagram())


def main():
    # -- SynthDef: resonant chime bank ----------------------------------------
    with SynthDefBuilder(density=1.5, decay=2.0, amplitude=0.3) as builder:
        trig = Dust.ar(density=builder["density"])
        decay = builder["decay"]

        # Bank of resonant filters at harmonically-related frequencies
        # (tuned to an E minor chord spread across octaves)
        sig = Ringz.ar(source=trig, frequency=329.63, decay_time=decay) * 0.15
        sig = (
            sig + Ringz.ar(source=trig, frequency=493.88, decay_time=decay * 0.8) * 0.12
        )
        sig = (
            sig + Ringz.ar(source=trig, frequency=659.26, decay_time=decay * 0.7) * 0.10
        )
        sig = (
            sig + Ringz.ar(source=trig, frequency=987.77, decay_time=decay * 0.5) * 0.08
        )
        sig = (
            sig + Ringz.ar(source=trig, frequency=1318.5, decay_time=decay * 0.4) * 0.06
        )
        sig = (
            sig + Ringz.ar(source=trig, frequency=1975.5, decay_time=decay * 0.3) * 0.04
        )

        # Remove DC offset and sub-bass rumble
        sig = LeakDC.ar(source=sig)
        sig = HPF.ar(source=sig, frequency=200.0)

        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=1.0, sustain_time=5.0, release_time=2.0
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    synthdef = builder.build(name="chime_bank")
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

    # Layer two instances panned apart for stereo spread
    print("Playing resonant chime texture (8s)...")
    send(
        world,
        "/s_new",
        "chime_bank",
        1000,
        0,
        1,
        "density",
        1.2,
        "decay",
        2.5,
        "amplitude",
        0.4,
    )
    time.sleep(0.5)
    send(
        world,
        "/s_new",
        "chime_bank",
        1001,
        0,
        1,
        "density",
        0.8,
        "decay",
        3.0,
        "amplitude",
        0.3,
    )
    time.sleep(8.5)

    send(world, "/quit")
    world_wait_for_quit(world, False)
    print("Done.")
    import sys

    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
