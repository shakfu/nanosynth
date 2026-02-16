"""
20_patterns.py -- Pattern-based sequencing.

Demonstrates the pattern system: Pseq, Prand, Pbind, Clock, and Player.
Plays a short melodic sequence using patterns instead of manual time.sleep()
loops, then a randomized variation.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.patterns import Clock, Pbind, Prand, Pseq, Pwhite, Rest
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import LPF, Out, Saw, SinOsc


def main() -> None:
    # -- SynthDef: simple gated sine with percussive envelope ------------------
    with SynthDefBuilder(freq=440.0, amp=0.1, pan=0.0, gate=1.0) as builder:
        sig = SinOsc.ar(frequency=builder["freq"])
        env = EnvGen.kr(
            envelope=Envelope.adsr(
                attack_time=0.01,
                decay_time=0.1,
                sustain=0.6,
                release_time=0.3,
            ),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amp"]
        Out.ar(bus=0, source=[sig, sig])

    sine_def = builder.build(name="default")

    # -- SynthDef: filtered saw for bass ---------------------------------------
    with SynthDefBuilder(freq=110.0, amp=0.15, gate=1.0) as builder:
        sig = Saw.ar(frequency=builder["freq"])
        sig = LPF.ar(source=sig, frequency=builder["freq"] * 3.0)
        env = EnvGen.kr(
            envelope=Envelope.adsr(
                attack_time=0.005,
                decay_time=0.2,
                sustain=0.4,
                release_time=0.2,
            ),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amp"]
        Out.ar(bus=0, source=[sig, sig])

    bass_def = builder.build(name="bass")

    # -- C major scale frequencies ---------------------------------------------
    c4 = 261.63
    d4 = 293.66
    e4 = 329.63
    f4 = 349.23
    g4 = 392.00
    a4 = 440.00
    b4 = 493.88
    c5 = 523.25

    with Server(Options(verbosity=0, load_synthdefs=False)) as server:
        sine_def.send(server)
        bass_def.send(server)
        time.sleep(0.1)

        clock = Clock(bpm=140)

        # -- Pattern 1: ascending melody with rests ----------------------------
        print("Pattern 1: ascending C major scale with rests...")
        melody = Pbind(
            instrument="default",
            freq=Pseq([c4, d4, e4, f4, g4, a4, b4, c5]),
            dur=Pseq([0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0]),
            amp=0.2,
        )
        melody.play(clock, server)
        time.sleep(4.0)

        # -- Pattern 2: randomized melody over bass ----------------------------
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
            dur=Pseq([0.25, 0.25, 0.5, 0.25, 0.25, 0.5, Rest(0.5), 0.5], repeats=2),
            amp=Pwhite(0.1, 0.25, repeats=16),
        )
        bass_player = bass_line.play(clock, server)
        melody_player = rand_melody.play(clock, server)
        time.sleep(5.0)

        # -- Cleanup -----------------------------------------------------------
        bass_player.stop()
        melody_player.stop()
        clock.stop()
        time.sleep(0.5)

    print("Done.")


if __name__ == "__main__":
    main()
