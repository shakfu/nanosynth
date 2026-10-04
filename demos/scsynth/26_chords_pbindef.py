"""
26_chords_pbindef.py -- Chords, PmonoArtic, Pbindef, and offline patterns.

A list value makes one event a chord: `degree=[0, 2, 4]` starts three synths,
each run through the pitch chain separately.  `PmonoArtic` is a `Pmono` that
re-attacks wherever `legato < 1`.  `Pbindef` rebinds one key of a running
pattern while the others keep their position.  Finally the chord progression
is rendered offline with `Score.from_pattern` to build/26_chords.wav, through
the same event code the realtime player uses.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time
from pathlib import Path

from nanosynth import Options, Score, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.patterns import Clock, Pbind, Pbindef, PmonoArtic, Pseq
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import LPF, Lag, Out, Pan2, Saw

BPM = 100
BEAT = 60.0 / BPM


def build_synthdefs():
    with SynthDefBuilder(freq=440.0, amp=0.08, gate=1.0) as builder:
        env = EnvGen.kr(
            envelope=Envelope.asr(attack_time=0.02, release_time=0.4),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = LPF.ar(source=Saw.ar(frequency=builder["freq"]), frequency=1800.0)
        Out.ar(bus=0, source=Pan2.ar(source=sig * env * builder["amp"]))
    pad = builder.build(name="pad")

    with SynthDefBuilder(freq=220.0, amp=0.15, gate=1.0) as builder:
        env = EnvGen.kr(
            envelope=Envelope.asr(attack_time=0.01, release_time=0.1),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        freq = Lag.kr(source=builder["freq"], lag_time=0.08)
        sig = LPF.ar(source=Saw.ar(frequency=freq), frequency=freq * 4.0)
        Out.ar(bus=0, source=Pan2.ar(source=sig * env * builder["amp"]))
    lead = builder.build(name="lead")
    return pad, lead


# I - vi - IV - V in C major, as scale-degree triads.
PROGRESSION = Pseq([[0, 2, 4], [5, 7, 9], [3, 5, 7], [4, 6, 8]])


def main() -> None:
    pad, lead = build_synthdefs()

    with Server(Options(verbosity=0, load_synthdefs=False)) as server:
        pad.send(server)
        lead.send(server)
        server.sync()
        clock = Clock(bpm=BPM)

        print("Chords: one event, three synths (I - vi - IV - V)")
        Pbind(instrument="pad", degree=PROGRESSION, octave=4, dur=2.0).play(
            clock, server
        )
        time.sleep(8 * BEAT + 0.8)

        print("PmonoArtic: legato 1 glides, legato 0.5 re-attacks")
        PmonoArtic(
            "lead",
            degree=Pseq([0, 1, 2, 4, 4, 2, 1, 0]),
            legato=Pseq([1.0, 1.0, 1.0, 0.5, 0.5, 1.0, 1.0, 0.5]),
            dur=0.5,
        ).play(clock, server)
        time.sleep(4 * BEAT + 0.6)

        print("Pbindef: halve dur mid-phrase; the degree sequence keeps going")
        Pbindef.clear()
        Pbindef(
            "arp",
            instrument="lead",
            degree=Pseq([0, 2, 4, 7, 4, 2], float("inf")),
            octave=5,
            dur=0.5,
            legato=0.4,
        )
        player = Pbindef("arp").play(clock, server)
        time.sleep(3 * BEAT)
        Pbindef("arp", dur=0.25)
        print("  dur -> 0.25")
        time.sleep(3 * BEAT)
        Pbindef("arp", scale="minor")
        print("  scale -> minor")
        time.sleep(3 * BEAT)
        player.stop()
        clock.stop()
        time.sleep(0.5)

    print("\nRendering the progression offline (Score.from_pattern)...")
    out_dir = Path("build")
    out_dir.mkdir(exist_ok=True)
    score = Score.from_pattern(
        Pbind(instrument="pad", degree=PROGRESSION, octave=4, dur=2.0),
        duration=8 * BEAT,
        bpm=BPM,
        synthdefs=[pad],
    )
    score.render(out_dir / "26_chords.wav")
    print(f"  wrote {out_dir / '26_chords.wav'}")


if __name__ == "__main__":
    main()
