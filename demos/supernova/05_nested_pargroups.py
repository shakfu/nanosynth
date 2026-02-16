"""
05_nested_pargroups.py -- Nested parallel groups for hierarchical scheduling.

Supernova supports nested ParGroups: a top-level ParGroup can contain
sub-ParGroups, allowing fine-grained control over which nodes run in
parallel vs. sequentially.

This demo builds a two-level hierarchy:

    ParGroup (top)
      |-- ParGroup "left"   (voices panned left)
      |-- ParGroup "right"  (voices panned right)
      |-- Group "fx"        (sequential: reverb must run after voices)

Each side's voices compute in parallel within their ParGroup, and
both sides compute in parallel with each other. The fx group runs
after both sides (ADD_TO_TAIL ensures ordering).

Requires:
  - nanosynth built with embedded supernova (NANOSYNTH_EMBED_SUPERNOVA=ON)
"""

import time

from nanosynth import AddAction, EmbeddedSupernovaProtocol, Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import (
    BPF,
    FreeVerb,
    In,
    LFNoise2,
    Out,
    Pan2,
    WhiteNoise,
)


def main() -> None:
    # -- SynthDef: filtered noise voice with random drift ---------------------
    with SynthDefBuilder(
        frequency=800.0, bandwidth=0.05, amplitude=0.1, pan=0.0, gate=1.0
    ) as builder:
        noise = WhiteNoise.ar()
        # Narrow bandpass with drifting center frequency
        drift = LFNoise2.kr(frequency=0.3)
        freq = builder["frequency"] + drift * builder["frequency"] * 0.1
        sig = BPF.ar(source=noise, frequency=freq, reciprocal_of_q=builder["bandwidth"])
        sig = sig * 10.0  # compensate for narrow bandwidth

        env = EnvGen.kr(
            envelope=Envelope.adsr(
                attack_time=1.0, decay_time=0.3, sustain=0.8, release_time=2.0
            ),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=builder["pan"]))

    voice_def = builder.build(name="filtered_noise")

    # -- SynthDef: reverb tail ------------------------------------------------
    with SynthDefBuilder(room=0.9, damp=0.3, mix=0.4) as builder:
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

    reverb_def = builder.build(name="reverb")

    # -- Frequency sets for left and right channels ---------------------------
    left_freqs = [300.0, 500.0, 800.0, 1300.0]
    right_freqs = [350.0, 600.0, 950.0, 1500.0]

    with Server(
        Options(verbosity=0, load_synthdefs=False),
        protocol=EmbeddedSupernovaProtocol(),
    ) as server:
        voice_def.send(server)
        reverb_def.send(server)
        time.sleep(0.1)

        # Top-level ParGroup
        top = server.par_group(target=1, action=AddAction.ADD_TO_HEAD)
        print(f"Top ParGroup: {top}")

        # Nested ParGroups for left and right voice banks
        left_par = server.par_group(target=top)
        right_par = server.par_group(target=top)

        # Sequential fx group after the voice ParGroups
        fx_grp = server.group(target=top, action=AddAction.ADD_TO_TAIL)
        server.synth("reverb", target=fx_grp, room=0.9, damp=0.3, mix=0.35)

        print(f"  Left ParGroup:  {left_par} ({len(left_freqs)} voices)")
        print(f"  Right ParGroup: {right_par} ({len(right_freqs)} voices)")
        print(f"  FX Group:       {fx_grp} (reverb)")
        print()

        # Spawn left voices
        left_nodes = []
        for freq in left_freqs:
            node = server.synth(
                "filtered_noise",
                target=left_par,
                frequency=freq,
                bandwidth=0.04,
                amplitude=0.08,
                pan=-0.6,
            )
            left_nodes.append(node)

        # Spawn right voices
        right_nodes = []
        for freq in right_freqs:
            node = server.synth(
                "filtered_noise",
                target=right_par,
                frequency=freq,
                bandwidth=0.04,
                amplitude=0.08,
                pan=0.6,
            )
            right_nodes.append(node)

        all_nodes = left_nodes + right_nodes
        print(f"{len(all_nodes)} voices active in nested ParGroups")
        print("Listening for 6 seconds...")
        time.sleep(6.0)

        # Fade out left side first
        print("Releasing left voices...")
        for node in left_nodes:
            server.set(node, gate=0.0)
        time.sleep(2.0)

        # Then right side
        print("Releasing right voices...")
        for node in right_nodes:
            server.set(node, gate=0.0)
        time.sleep(3.0)

    print("Done.")


if __name__ == "__main__":
    main()
