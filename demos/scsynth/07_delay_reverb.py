"""
07_delay_reverb.py -- Delay lines and reverb.

Demonstrates effect processing with three SynthDefs:
  1. A short percussive source (filtered saw impulse)
  2. Ping-pong style comb delay feedback
  3. FreeVerb for lush tail

The source feeds into the comb delay, which feeds into reverb,
showing how to chain effects via audio buses.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import AddAction, Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import (
    AllpassC,
    CombC,
    FreeVerb,
    In,
    Out,
    Pan2,
    RLPF,
    Saw,
)


# First private audio bus (after hardware I/O buses)
EFFECT_BUS = 16


def main() -> None:
    # -- SynthDef 1: percussive source -> effect bus --------------------------
    with SynthDefBuilder(frequency=440.0, amplitude=0.4) as builder:
        sig = Saw.ar(frequency=builder["frequency"])
        sig = RLPF.ar(source=sig, frequency=2000.0, reciprocal_of_q=0.3)
        env = EnvGen.kr(
            envelope=Envelope.percussive(attack_time=0.003, release_time=0.15),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        # Write to both hardware out (dry) and effect bus
        Out.ar(bus=0, source=Pan2.ar(source=sig * 0.4))
        Out.ar(bus=EFFECT_BUS, source=sig)

    src_def = builder.build(name="perc_src")
    print(f"SynthDef '{src_def.name}' compiled: {len(src_def.compile())} bytes")

    # -- SynthDef 2: comb delay effect (reads effect bus) ---------------------
    with SynthDefBuilder(delay_time=0.375, decay_time=3.0, mix=0.5) as builder:
        dry = In.ar(bus=EFFECT_BUS)
        # Two comb delays at slightly different times for stereo width
        left = CombC.ar(
            source=dry,
            maximum_delay_time=1.0,
            delay_time=builder["delay_time"],
            decay_time=builder["decay_time"],
        )
        right = CombC.ar(
            source=dry,
            maximum_delay_time=1.0,
            delay_time=builder["delay_time"] * 0.75,
            decay_time=builder["decay_time"],
        )
        # Allpass diffusion
        left = AllpassC.ar(
            source=left,
            maximum_delay_time=0.05,
            delay_time=0.031,
            decay_time=1.0,
        )
        right = AllpassC.ar(
            source=right,
            maximum_delay_time=0.05,
            delay_time=0.043,
            decay_time=1.0,
        )
        wet = builder["mix"]
        Out.ar(bus=0, source=[left * wet, right * wet])

    delay_def = builder.build(name="comb_delay")
    print(f"SynthDef '{delay_def.name}' compiled: {len(delay_def.compile())} bytes")

    # -- SynthDef 3: reverb tail (reads hardware out, adds reverb) ------------
    with SynthDefBuilder(room=0.85, damp=0.4, mix=0.3) as builder:
        sig = In.ar(bus=0, channel_count=2)
        left = sig[0]
        right = sig[1]
        left = FreeVerb.ar(
            source=left,
            mix=builder["mix"],
            room_size=builder["room"],
            damping=builder["damp"],
        )
        right = FreeVerb.ar(
            source=right,
            mix=builder["mix"],
            room_size=builder["room"],
            damping=builder["damp"],
        )
        Out.ar(bus=0, source=[left, right])

    verb_def = builder.build(name="reverb")
    print(f"SynthDef '{verb_def.name}' compiled: {len(verb_def.compile())} bytes")

    # -- Boot and play --------------------------------------------------------
    with Server(Options(verbosity=0)) as server:
        src_def.send(server)
        delay_def.send(server)
        verb_def.send(server)
        time.sleep(0.1)

        # Create source and effect groups with correct execution order
        src_group = server.group(target=1, action=AddAction.ADD_TO_HEAD)
        fx_group = server.group(target=int(src_group), action=AddAction.ADD_AFTER)

        # Start persistent effect synths in the effect group
        server.synth(
            "comb_delay",
            target=int(fx_group),
            delay_time=0.375,
            decay_time=4.0,
            mix=0.4,
        )
        server.synth(
            "reverb",
            target=int(fx_group),
            action=AddAction.ADD_AFTER,  # after fx group, not inside it
            room=0.8,
            damp=0.5,
            mix=0.25,
        )

        # Fire percussive notes in the source group
        melody = [
            (329.63, 0.375),  # E4
            (392.00, 0.375),  # G4
            (440.00, 0.375),  # A4
            (523.25, 0.375),  # C5
            (440.00, 0.375),  # A4
            (392.00, 0.375),  # G4
            (329.63, 0.750),  # E4 (held longer)
            (293.66, 0.750),  # D4
        ]

        print("Playing percussive melody through delay + reverb...")
        for freq, dur in melody:
            server.synth(
                "perc_src",
                target=int(src_group),
                frequency=freq,
                amplitude=0.5,
            )
            time.sleep(dur)

        # Let the delay tail ring out
        print("Letting delay tail ring out (4s)...")
        time.sleep(4.0)

    print("Done.")


if __name__ == "__main__":
    main()
