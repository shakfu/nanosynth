"""
04_parallel_fx.py -- Parallel effect chains with ParGroup.

Supernova's key advantage over scsynth: independent signal paths can
run on separate CPU cores. This demo creates three self-contained
effect chains (each with its own source + delay + reverb), places
them in a ParGroup, and lets supernova schedule them across threads.

With scsynth, all three chains would execute sequentially on one core.
With supernova, each chain can run on its own core -- the ParGroup
tells the scheduler that its children have no data dependencies.

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
    LFNoise1,
    LPF,
    Out,
    Saw,
    SinOsc,
)


# Each chain uses its own private bus so there are no data dependencies
CHAIN_BUSES = [16, 18, 20]  # stereo pairs: 16-17, 18-19, 20-21


def main() -> None:
    # -- SynthDef: pitched drone source writing to a private bus ---------------
    with SynthDefBuilder(
        frequency=220.0, amplitude=0.3, out_bus=0, gate=1.0
    ) as builder:
        freq = builder["frequency"]
        # Two detuned saws + sub sine
        sig = Saw.ar(frequency=freq * 1.002) + Saw.ar(frequency=freq * 0.998)
        sig = sig + SinOsc.ar(frequency=freq * 0.5) * 0.4
        # Drifting filter
        lfo = LFNoise1.kr(frequency=0.2)
        sig = LPF.ar(source=sig, frequency=freq * 3.0 + lfo * freq)
        env = EnvGen.kr(
            envelope=Envelope.adsr(
                attack_time=2.0, decay_time=0.5, sustain=0.7, release_time=3.0
            ),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=builder["out_bus"], source=[sig, sig])

    drone_def = builder.build(name="drone_src")

    # -- SynthDef: stereo comb delay reading/writing a private bus -------------
    with SynthDefBuilder(bus=0, delay_time=0.3, decay_time=2.0, mix=0.4) as builder:
        sig = In.ar(bus=builder["bus"], channel_count=2)
        left = CombC.ar(
            source=sig[0],
            maximum_delay_time=1.0,
            delay_time=builder["delay_time"],
            decay_time=builder["decay_time"],
        )
        right = CombC.ar(
            source=sig[1],
            maximum_delay_time=1.0,
            delay_time=builder["delay_time"] * 0.75,
            decay_time=builder["decay_time"],
        )
        left = AllpassC.ar(
            source=left,
            maximum_delay_time=0.1,
            delay_time=0.037,
            decay_time=0.8,
        )
        right = AllpassC.ar(
            source=right,
            maximum_delay_time=0.1,
            delay_time=0.053,
            decay_time=0.8,
        )
        wet = builder["mix"]
        Out.ar(bus=builder["bus"], source=[left * wet, right * wet])

    delay_def = builder.build(name="chain_delay")

    # -- SynthDef: per-chain reverb that reads private bus, writes to main -----
    with SynthDefBuilder(bus=0, pan=0.0, room=0.8, damp=0.5, mix=0.3) as builder:
        sig = In.ar(bus=builder["bus"], channel_count=2)
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

    reverb_def = builder.build(name="chain_reverb")

    # -- Chain configurations (pitch, delay, pan) ------------------------------
    chains = [
        {"freq": 110.00, "delay": 0.375, "pan": -0.7, "label": "A (low)"},
        {"freq": 164.81, "delay": 0.250, "pan": 0.0, "label": "B (mid)"},
        {"freq": 246.94, "delay": 0.500, "pan": 0.7, "label": "C (high)"},
    ]

    # -- Boot and play ---------------------------------------------------------
    with Server(
        Options(verbosity=0, load_synthdefs=False),
        protocol=EmbeddedSupernovaProtocol(),
    ) as server:
        drone_def.send(server)
        delay_def.send(server)
        reverb_def.send(server)
        time.sleep(0.1)

        # ParGroup at head -- its children (the three chain groups)
        # have no data dependencies, so supernova runs them in parallel
        par = server.par_group(target=1, action=AddAction.ADD_TO_HEAD)
        print(f"ParGroup {par}: three independent effect chains")

        drone_nodes = []
        for i, (bus, chain) in enumerate(zip(CHAIN_BUSES, chains)):
            # Each chain is a sequential Group inside the ParGroup
            grp = server.group(target=par)

            # Source -> private bus
            node = server.synth(
                "drone_src",
                target=grp,
                frequency=chain["freq"],
                amplitude=0.15,
                out_bus=bus,
            )
            drone_nodes.append(node)

            # Delay on private bus
            server.synth(
                "chain_delay",
                target=grp,
                action=AddAction.ADD_TO_TAIL,
                bus=bus,
                delay_time=chain["delay"],
                decay_time=3.0,
                mix=0.35,
            )

            # Reverb: reads private bus, writes to main out
            server.synth(
                "chain_reverb",
                target=grp,
                action=AddAction.ADD_TO_TAIL,
                bus=bus,
                pan=chain["pan"],
                room=0.85,
                damp=0.4,
                mix=0.3,
            )

            print(
                f"  Chain {chain['label']}: {chain['freq']} Hz, "
                f"delay {chain['delay']}s, bus {bus}"
            )

        print("\nThree parallel chains active -- listening for 8 seconds...")
        time.sleep(8.0)

        # Release all drones
        print("Releasing...")
        for node in drone_nodes:
            server.set(node, gate=0.0)
        time.sleep(4.0)

    print("Done.")


if __name__ == "__main__":
    main()
