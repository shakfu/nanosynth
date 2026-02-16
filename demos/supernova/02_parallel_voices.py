"""
02_parallel_voices.py -- Parallel voice processing with supernova.

Demonstrates supernova's parallel DSP advantage: many concurrent synth
voices distributed across CPU cores. Creates a dense cluster of detuned
oscillators that would benefit from supernova's multi-threaded audio graph.

Uses ParGroup (parallel group) to hint that voices within it can be
computed concurrently by supernova's DSP thread pool.

Requires:
  - nanosynth built with embedded supernova (NANOSYNTH_EMBED_SUPERNOVA=ON)
"""

import time

from nanosynth import AddAction, EmbeddedSupernovaProtocol, Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import (
    FreeVerb,
    In,
    LFNoise1,
    LPF,
    Out,
    Pan2,
    Saw,
)


NUM_VOICES = 24


def main() -> None:
    # -- SynthDef: detuned saw voice with slow filter drift -------------------
    with SynthDefBuilder(
        frequency=220.0,
        detune=0.5,
        amplitude=0.04,
        pan=0.0,
        gate=1.0,
    ) as builder:
        # Slightly detuned pair of saws
        freq = builder["frequency"]
        detune = builder["detune"]
        sig = Saw.ar(frequency=freq + detune) + Saw.ar(frequency=freq - detune)

        # Slow random filter movement
        lfo = LFNoise1.kr(frequency=0.4)
        cutoff = freq * 4.0 + lfo * freq * 2.0
        sig = LPF.ar(source=sig, frequency=cutoff)

        env = EnvGen.kr(
            envelope=Envelope.adsr(
                attack_time=1.5,
                decay_time=0.5,
                sustain=0.7,
                release_time=2.0,
            ),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=builder["pan"]))

    voice_def = builder.build(name="detune_saw")
    print(f"SynthDef '{voice_def.name}' compiled: {len(voice_def.compile())} bytes")

    # -- SynthDef: simple reverb tail -----------------------------------------
    with SynthDefBuilder(room=0.8, damp=0.5, mix=0.3) as builder:
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

    # -- A chord cluster spread across the stereo field -----------------------
    base_freqs = [
        130.81,  # C3
        164.81,  # E3
        196.00,  # G3
        246.94,  # B3
        293.66,  # D4
        349.23,  # F4
    ]

    # -- Boot supernova and play ----------------------------------------------
    with Server(
        Options(verbosity=0, load_synthdefs=False), protocol=EmbeddedSupernovaProtocol()
    ) as server:
        voice_def.send(server)
        reverb_def.send(server)
        time.sleep(0.1)

        # Create a ParGroup -- supernova distributes its children across
        # DSP threads for parallel computation
        par = server.par_group(target=1, action=AddAction.ADD_TO_HEAD)
        print(f"ParGroup {par} created for parallel voice processing")

        # Reverb after the parallel group
        server.synth(
            "reverb",
            target=int(par),
            action=AddAction.ADD_AFTER,
            room=0.85,
            damp=0.4,
            mix=0.25,
        )

        # Spawn voices: 4 per base frequency, spread across stereo field
        nodes = []
        voices_per_freq = NUM_VOICES // len(base_freqs)
        print(f"\nSpawning {NUM_VOICES} voices ({voices_per_freq} per pitch)...")

        for i, base_freq in enumerate(base_freqs):
            for j in range(voices_per_freq):
                # Spread panning across stereo field
                pan = -0.8 + 1.6 * (i * voices_per_freq + j) / (NUM_VOICES - 1)
                # Slight random detune per voice
                detune = 0.3 + j * 0.4
                node = server.synth(
                    "detune_saw",
                    target=par,
                    frequency=base_freq,
                    detune=detune,
                    amplitude=0.03,
                    pan=pan,
                )
                nodes.append(node)
                time.sleep(0.05)  # stagger entries slightly

        print(f"All {len(nodes)} voices active -- listening for 6 seconds...")
        time.sleep(6.0)

        # Release all voices (gate -> 0 triggers ADSR release)
        print("Releasing voices...")
        for node in nodes:
            server.set(node, gate=0.0)

        # Let release tails ring out
        time.sleep(3.0)

    print("Done.")


if __name__ == "__main__":
    main()
