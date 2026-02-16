"""
06_dense_polyphony.py -- Dense polyphony stress test.

Spawns 64 simultaneous synth voices with complex per-voice processing
(dual oscillators, filter, envelope, panning). This kind of workload
is where supernova's parallel DSP threads provide the most benefit --
each voice is independent and can run on a separate core.

The voices play a slowly shifting tone cluster that evolves over time,
with individual voices fading in and out at different rates.

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
    LFNoise2,
    LPF,
    Out,
    Pan2,
    Saw,
    SinOsc,
)


NUM_VOICES = 64


def main() -> None:
    # -- SynthDef: complex per-voice processing --------------------------------
    # Each voice has: dual oscillators, drifting filter, random panning, envelope
    with SynthDefBuilder(
        frequency=220.0,
        detune=1.0,
        filter_mul=3.0,
        amplitude=0.02,
        attack=1.0,
        sustain_time=4.0,
        release=2.0,
    ) as builder:
        freq = builder["frequency"]
        detune = builder["detune"]

        # Dual detuned oscillators (saw + sine sub)
        sig = Saw.ar(frequency=freq + detune)
        sig = sig + Saw.ar(frequency=freq - detune) * 0.8
        sig = sig + SinOsc.ar(frequency=freq * 0.5) * 0.3

        # Drifting filter -- each voice wanders independently
        lfo = LFNoise2.kr(frequency=0.15)
        cutoff = freq * builder["filter_mul"] + lfo * freq * 2.0
        sig = LPF.ar(source=sig, frequency=cutoff)

        # Random slow panning
        pan = LFNoise1.kr(frequency=0.1)

        # Self-freeing envelope
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=builder["attack"],
                sustain_time=builder["sustain_time"],
                release_time=builder["release"],
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=pan))

    voice_def = builder.build(name="poly_voice")
    print(f"SynthDef '{voice_def.name}' compiled: {len(voice_def.compile())} bytes")

    # -- SynthDef: master reverb -----------------------------------------------
    with SynthDefBuilder(room=0.85, damp=0.4, mix=0.25) as builder:
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

    # -- Pitch material: microtonal cluster around a fundamental ---------------
    fundamental = 130.81  # C3
    # Spread voices across a two-octave range with slight microtonal offsets
    import random

    random.seed(42)
    freqs = [
        fundamental * (2 ** (i / 12.0 + random.uniform(-0.05, 0.05)))
        for i in range(NUM_VOICES)
    ]

    # -- Boot and play ---------------------------------------------------------
    with Server(
        Options(verbosity=0, load_synthdefs=False),
        protocol=EmbeddedSupernovaProtocol(),
    ) as server:
        voice_def.send(server)
        reverb_def.send(server)
        time.sleep(0.1)

        # ParGroup for all voices -- fully parallel
        par = server.par_group(target=1, action=AddAction.ADD_TO_HEAD)

        # Reverb after voices
        server.synth(
            "reverb",
            target=int(par),
            action=AddAction.ADD_AFTER,
            room=0.85,
            damp=0.4,
            mix=0.2,
        )

        print(f"Spawning {NUM_VOICES} voices in ParGroup...")
        for i, freq in enumerate(freqs):
            # Stagger attack and duration for organic feel
            attack = 0.5 + (i % 7) * 0.3
            sustain = 3.0 + (i % 5) * 0.8
            release = 1.5 + (i % 4) * 0.5
            detune = 0.2 + (i % 3) * 0.3

            server.synth(
                "poly_voice",
                target=par,
                frequency=freq,
                detune=detune,
                filter_mul=2.0 + (i % 6) * 0.5,
                amplitude=0.015,
                attack=attack,
                sustain_time=sustain,
                release=release,
            )

            # Stagger spawning slightly
            if i % 8 == 7:
                time.sleep(0.02)

        print(f"All {NUM_VOICES} voices active")
        print("Listening for 10 seconds (voices self-free via envelope)...")
        time.sleep(10.0)

    print("Done.")


if __name__ == "__main__":
    main()
