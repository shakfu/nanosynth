"""
03_fx_chain.py -- Effect chain with supernova.

Demonstrates the same Server API working with supernova for a multi-bus
effect chain: percussive source -> comb delay -> reverb.

Identical structure to scsynth/07_delay_reverb.py but running on supernova.

Requires:
  - nanosynth built with embedded supernova (NANOSYNTH_EMBED_SUPERNOVA=ON)
"""

import time

from nanosynth import AddAction, EmbeddedSupernovaProtocol, Options, Server
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


EFFECT_BUS = 16


def main() -> None:
    # -- SynthDef 1: percussive filtered saw -> effect bus --------------------
    with SynthDefBuilder(frequency=440.0, amplitude=0.4) as builder:
        sig = Saw.ar(frequency=builder["frequency"])
        sig = RLPF.ar(source=sig, frequency=2000.0, reciprocal_of_q=0.3)
        env = EnvGen.kr(
            envelope=Envelope.percussive(attack_time=0.003, release_time=0.15),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig * 0.4))
        Out.ar(bus=EFFECT_BUS, source=sig)

    src_def = builder.build(name="perc_src")

    # -- SynthDef 2: stereo comb delay ---------------------------------------
    with SynthDefBuilder(delay_time=0.375, decay_time=3.0, mix=0.5) as builder:
        dry = In.ar(bus=EFFECT_BUS)
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

    # -- SynthDef 3: reverb --------------------------------------------------
    with SynthDefBuilder(room=0.85, damp=0.4, mix=0.3) as builder:
        sig = In.ar(bus=0, channel_count=2)
        left = FreeVerb.ar(
            source=sig[0],
            mix=builder["mix"],
            room_size=builder["room"],
            damping=builder["damp"],
        )
        right = FreeVerb.ar(
            source=sig[1],
            mix=builder["mix"],
            room_size=builder["room"],
            damping=builder["damp"],
        )
        Out.ar(bus=0, source=[left, right])

    verb_def = builder.build(name="reverb")

    print(f"SynthDefs compiled: {src_def.name}, {delay_def.name}, {verb_def.name}")

    # -- Boot supernova and play ----------------------------------------------
    with Server(
        Options(verbosity=0, load_synthdefs=False), protocol=EmbeddedSupernovaProtocol()
    ) as server:
        src_def.send(server)
        delay_def.send(server)
        verb_def.send(server)
        time.sleep(0.1)

        # Execution order: source group first, effects after
        src_group = server.group(target=1, action=AddAction.ADD_TO_HEAD)
        fx_group = server.group(target=int(src_group), action=AddAction.ADD_AFTER)

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
            action=AddAction.ADD_TO_TAIL,
            room=0.8,
            damp=0.5,
            mix=0.25,
        )

        # Play a melody through the effect chain
        melody = [
            (329.63, 0.375),  # E4
            (392.00, 0.375),  # G4
            (440.00, 0.375),  # A4
            (523.25, 0.375),  # C5
            (440.00, 0.375),  # A4
            (392.00, 0.375),  # G4
            (329.63, 0.750),  # E4 (held)
            (293.66, 0.750),  # D4
        ]

        print("Playing melody through delay + reverb...")
        for freq, dur in melody:
            server.synth(
                "perc_src",
                target=int(src_group),
                frequency=freq,
                amplitude=0.5,
            )
            time.sleep(dur)

        print("Letting delay tail ring out (4s)...")
        time.sleep(4.0)

    print("Done.")


if __name__ == "__main__":
    main()
