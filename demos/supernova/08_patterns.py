"""
08_patterns.py -- Pattern sequencing on supernova.

Uses Pbind/Pseq/Prand with a Clock and Player, identical to the scsynth
pattern demo. Demonstrates that the pattern system works unchanged on
supernova -- patterns schedule from the host, so the engine backend is
transparent to the sequencing layer.

Requires:
  - nanosynth built with embedded supernova (NANOSYNTH_EMBED_SUPERNOVA=ON)
"""

import time

from nanosynth import EmbeddedSupernovaProtocol, Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.patterns import Clock, Pbind, Prand, Pseq, Pwhite, Rest
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import LPF, Out, Saw, SinOsc


def main() -> None:
    # -- SynthDef: gated sine ---------------------------------------------------
    with SynthDefBuilder(freq=440.0, amp=0.1, gate=1.0) as builder:
        sig = SinOsc.ar(frequency=builder["freq"])
        env = EnvGen.kr(
            envelope=Envelope.adsr(
                attack_time=0.01, decay_time=0.1,
                sustain=0.6, release_time=0.3,
            ),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amp"]
        Out.ar(bus=0, source=[sig, sig])

    sine_def = builder.build(name="default")

    # -- SynthDef: filtered saw bass --------------------------------------------
    with SynthDefBuilder(freq=110.0, amp=0.15, gate=1.0) as builder:
        sig = Saw.ar(frequency=builder["freq"])
        sig = LPF.ar(source=sig, frequency=builder["freq"] * 3.0)
        env = EnvGen.kr(
            envelope=Envelope.adsr(
                attack_time=0.005, decay_time=0.2,
                sustain=0.4, release_time=0.2,
            ),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amp"]
        Out.ar(bus=0, source=[sig, sig])

    bass_def = builder.build(name="bass")

    # -- Frequencies ------------------------------------------------------------
    c4, d4, e4, f4 = 261.63, 293.66, 329.63, 349.23
    g4, a4, b4, c5 = 392.00, 440.00, 493.88, 523.25

    # -- Boot and play ----------------------------------------------------------
    with Server(
        Options(verbosity=0, load_synthdefs=False),
        protocol=EmbeddedSupernovaProtocol(),
    ) as server:
        sine_def.send(server)
        bass_def.send(server)
        time.sleep(0.1)

        clock = Clock(bpm=140)

        # Pattern 1: ascending scale
        print("Pattern 1: ascending C major scale...")
        melody = Pbind(
            instrument="default",
            freq=Pseq([c4, d4, e4, f4, g4, a4, b4, c5]),
            dur=Pseq([0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0]),
            amp=0.2,
        )
        melody.play(clock, server)
        time.sleep(4.0)

        # Pattern 2: random melody over bass
        print("Pattern 2: random melody with bass...")
        bass_line = Pbind(
            instrument="bass",
            freq=Pseq([c4 / 2, f4 / 2, g4 / 2, c4 / 2], repeats=2),
            dur=1.0,
            amp=0.2,
        )
        rand_melody = Pbind(
            instrument="default",
            freq=Prand([c4, e4, g4, a4, c5], repeats=16),
            dur=Pseq(
                [0.25, 0.25, 0.5, 0.25, 0.25, 0.5, Rest(0.5), 0.5],
                repeats=2,
            ),
            amp=Pwhite(0.1, 0.25, repeats=16),
        )
        bass_player = bass_line.play(clock, server)
        melody_player = rand_melody.play(clock, server)
        time.sleep(5.0)

        bass_player.stop()
        melody_player.stop()
        clock.stop()
        time.sleep(0.5)

    print("Done.")


if __name__ == "__main__":
    main()
