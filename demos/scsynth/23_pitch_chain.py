"""
23_pitch_chain.py -- Scale degrees, tuning, and the event derivation chain.

Instead of precomputing frequencies, events carry musical intent: a `degree`
into a `scale`, transposed by `root` and `octave`.  Pbind derives
degree -> note -> midinote -> freq for you.  The same degree sequence played
against different scales is the audible point -- one melody, many modes.

Also covers `db` -> `amp`, the `legato`/`stretch` timing keys, and `Pkey`,
which reads a sibling key of the event being built.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.patterns import Clock, Pbind, Pkey, Pseq
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import LPF, Out, Pan2, Saw


def main() -> None:
    # -- SynthDef: filtered saw voice; cutoff tracks pitch --------------------
    with SynthDefBuilder(
        freq=440.0, amp=0.15, pan=0.0, cutoff=2000.0, gate=1.0
    ) as builder:
        env = EnvGen.kr(
            envelope=Envelope.adsr(
                attack_time=0.01, decay_time=0.15, sustain=0.5, release_time=0.25
            ),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = Saw.ar(frequency=builder["freq"])
        sig = LPF.ar(source=sig, frequency=builder["cutoff"])
        sig = sig * env * builder["amp"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=builder["pan"]))

    voice_def = builder.build(name="voice")

    with Server(Options(verbosity=0, load_synthdefs=False)) as server:
        voice_def.send(server)
        server.sync()

        clock = Clock(bpm=132)
        run = Pseq([0, 1, 2, 3, 4, 5, 6, 7])

        # -- One degree sequence, four scales -------------------------------
        for scale in ("major", "minor", "dorian", "minor_pentatonic"):
            print(f"Scale: {scale}")
            Pbind(
                instrument="voice",
                degree=run,
                scale=scale,
                dur=0.22,
                amp=0.15,
            ).play(clock, server)
            time.sleep(0.22 * 8 + 0.5)

        # -- root and octave transpose the same degrees ----------------------
        print("\nSame degrees, root=0/3/7 (C -> Eb -> G)")
        for root in (0, 3, 7):
            Pbind(
                instrument="voice",
                degree=Pseq([0, 2, 4, 2]),
                scale="minor",
                root=root,
                dur=0.25,
                amp=0.15,
            ).play(clock, server)
            time.sleep(0.25 * 4 + 0.2)

        print("Same degrees, octave=3/4/5/6")
        for octave in (3, 4, 5, 6):
            Pbind(
                instrument="voice",
                degree=Pseq([0, 4]),
                octave=octave,
                dur=0.25,
                amp=0.15,
            ).play(clock, server)
            time.sleep(0.25 * 2 + 0.1)

        # -- db -> amp: a decibel ramp is a smooth fade ----------------------
        print("\ndb -> amp: -3 dB per step")
        Pbind(
            instrument="voice",
            degree=Pseq([7] * 8),
            db=Pseq([-3.0 * i for i in range(8)]),
            dur=0.25,
        ).play(clock, server)
        time.sleep(0.25 * 8 + 0.5)

        # -- legato: same notes, same spacing, different note lengths --------
        print("\nlegato 0.2 (staccato) then 1.6 (overlapping)")
        for legato in (0.2, 1.6):
            Pbind(
                instrument="voice",
                degree=Pseq([0, 2, 4, 6]),
                dur=0.4,
                legato=legato,
                amp=0.15,
            ).play(clock, server)
            time.sleep(0.4 * 4 + 0.6)

        # -- stretch: scales dur and sustain together ------------------------
        print("stretch 1.0 then 0.5 (same pattern, twice as fast)")
        for stretch in (1.0, 0.5):
            Pbind(
                instrument="voice",
                degree=Pseq([0, 1, 2, 3, 4, 5, 6, 7]),
                dur=0.25,
                stretch=stretch,
                amp=0.15,
            ).play(clock, server)
            time.sleep(0.25 * 8 * stretch + 0.4)

        # -- Pkey: brightness follows pitch ----------------------------------
        print("\nPkey: cutoff derived from the freq the pitch chain produced")
        Pbind(
            instrument="voice",
            degree=Pseq([0, 2, 4, 7, 9, 11, 14]),
            # Bound to a non-chain key, so it resolves after derivation and
            # sees the final freq.
            cutoff=Pkey("freq", lambda f: f * 6.0),
            pan=Pkey("freq", lambda f: min(1.0, (f - 260.0) / 500.0)),
            dur=0.3,
            amp=0.15,
        ).play(clock, server)
        time.sleep(0.3 * 7 + 0.8)

        clock.stop()
        time.sleep(0.3)

    print("Done.")


if __name__ == "__main__":
    main()
