"""
24_parallel_quant.py -- Ppar, Ptpar, and quantized starts.

`Ppar` merges several event patterns into one time-ordered stream, so a bass,
a lead and a hat part run as one player.  Coincident events across voices get
a delta of 0, which puts them in the same OSC bundle -- they start on the same
sample, not merely in the same tick.

`Ptpar` staggers entries by a beat offset.  `quant` snaps a start to the next
bar, which is what lets you launch a part by hand mid-bar and still have it
land on the downbeat.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.patterns import Clock, Pbind, Pn, Ppar, Pseq, Ptpar, Rest
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import HPF, LPF, Out, Pan2, Saw, SinOsc, WhiteNoise

BPM = 120
BEAT = 60.0 / BPM
BAR = 4 * BEAT


def _build_defs() -> list:
    defs = []

    # Bass: filtered saw.
    with SynthDefBuilder(freq=110.0, amp=0.2, gate=1.0) as builder:
        env = EnvGen.kr(
            envelope=Envelope.adsr(
                attack_time=0.005, decay_time=0.2, sustain=0.4, release_time=0.15
            ),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = LPF.ar(source=Saw.ar(frequency=builder["freq"]), frequency=600.0)
        Out.ar(bus=0, source=Pan2.ar(source=sig * env * builder["amp"]))
    defs.append(builder.build(name="p_bass"))

    # Lead: sine.
    with SynthDefBuilder(freq=440.0, amp=0.12, pan=0.0, gate=1.0) as builder:
        env = EnvGen.kr(
            envelope=Envelope.adsr(
                attack_time=0.01, decay_time=0.1, sustain=0.5, release_time=0.25
            ),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = SinOsc.ar(frequency=builder["freq"]) * env * builder["amp"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=builder["pan"]))
    defs.append(builder.build(name="p_lead"))

    # Hat: filtered noise burst.
    with SynthDefBuilder(amp=0.08, freq=8000.0) as builder:
        env = EnvGen.kr(
            envelope=Envelope.percussive(attack_time=0.001, release_time=0.05),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = HPF.ar(source=WhiteNoise.ar(), frequency=builder["freq"])
        Out.ar(bus=0, source=Pan2.ar(source=sig * env * builder["amp"]))
    defs.append(builder.build(name="p_hat"))

    return defs


def main() -> None:
    with Server(Options(verbosity=0, load_synthdefs=False)) as server:
        for synthdef in _build_defs():
            synthdef.send(server)
        server.sync()

        clock = Clock(bpm=BPM)

        bass = Pbind(
            instrument="p_bass",
            degree=Pseq([0, 0, 3, 5]),
            octave=3,
            dur=1.0,
            amp=0.2,
        )
        lead = Pbind(
            instrument="p_lead",
            degree=Pseq([7, 9, 11, 9, 7, 4, Rest(0.5), 2]),
            dur=0.5,
            amp=0.12,
        )
        hats = Pbind(instrument="p_hat", dur=0.25, amp=0.06)

        # -- Ppar: three voices as one player -------------------------------
        print("Ppar: bass + lead + hats merged into one stream (2 passes)")
        player = Ppar(
            [Pn(bass, 2), Pn(lead, 2), Pn(hats, 2)],
        ).play(clock, server)
        time.sleep(BAR * 4 + 0.8)
        player.stop()
        time.sleep(0.4)

        # -- Ptpar: staggered entries ---------------------------------------
        print("\nPtpar: bass enters, lead 2 beats later, hats 2 beats after that")
        player = Ptpar(
            [
                (0.0, Pn(bass, 3)),
                (2.0, Pn(lead, 2)),
                (4.0, Pn(hats, 8)),
            ]
        ).play(clock, server)
        time.sleep(BAR * 3 + 1.0)
        player.stop()
        time.sleep(0.4)

        # -- Quantization: launch mid-bar, start on the downbeat -------------
        print("\nQuantization: a 4-beat grid, parts launched at random moments")
        clock.reset_grid()
        hat_player = Pn(hats, 16).play(clock, server, quant=4)
        print("  hats queued for the next bar")

        # Launch the others at deliberately awkward moments -- they still
        # arrive on the downbeat because they share the clock's grid.
        time.sleep(BEAT * 1.3)
        bass_player = Pn(bass, 4).play(clock, server, quant=4)
        print("  bass launched 1.3 beats in -> waits for the next bar")

        time.sleep(BEAT * 2.7)
        lead_player = Pn(lead, 2).play(clock, server, quant=4)
        print("  lead launched 4.0 beats in -> waits for the bar after that")

        time.sleep(BAR * 4)

        # -- offset: land half a beat late, deliberately ---------------------
        print("  offbeat hats via quant=1, offset=0.5")
        off_player = Pn(
            Pbind(instrument="p_hat", dur=1.0, amp=0.08, freq=5000.0), 8
        ).play(clock, server, quant=1, offset=0.5)
        time.sleep(BAR * 2)

        for player in (hat_player, bass_player, lead_player, off_player):
            player.stop()
        clock.stop()
        time.sleep(0.5)

    print("Done.")


if __name__ == "__main__":
    main()
