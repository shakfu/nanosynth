"""
25_pmono_pdef.py -- Pmono glides, Pdef hot-swaps, Pfin/Pfindur bound.

`Pmono` holds one synth for the whole pattern and retunes it per event.  With
a lagged frequency that is audibly a single gliding line -- portamento a
stream of separate synths cannot produce.  The demo plays the same notes as a
`Pbind` first, so the difference is obvious.

`Pdef` is a named registry whose contents can be replaced while a player is
running: the part changes at the next event without a gap.  `Pfin` and
`Pfindur` bound a pattern by event count and by total duration.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.patterns import Clock, Pbind, Pdef, Pfin, Pfindur, Pmono, Pn, Pseq
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import LPF, Lag, Out, Pan2, Saw

BPM = 120
BEAT = 60.0 / BPM


def main() -> None:
    # -- SynthDef: lagged pitch, so /n_set glides instead of jumping ---------
    with SynthDefBuilder(freq=110.0, amp=0.18, lag=0.12, gate=1.0) as builder:
        env = EnvGen.kr(
            envelope=Envelope.asr(attack_time=0.02, release_time=0.3),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        # Lag is what turns a per-event /n_set into a portamento.
        freq = Lag.kr(source=builder["freq"], lag_time=builder["lag"])
        sig = LPF.ar(source=Saw.ar(frequency=freq), frequency=freq * 5.0)
        Out.ar(bus=0, source=Pan2.ar(source=sig * env * builder["amp"]))

    glide_def = builder.build(name="glide")

    # -- SynthDef: plain plucked voice for the Pdef section ------------------
    with SynthDefBuilder(freq=440.0, amp=0.14, gate=1.0) as builder:
        env = EnvGen.kr(
            envelope=Envelope.percussive(attack_time=0.005, release_time=0.35),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = LPF.ar(source=Saw.ar(frequency=builder["freq"]), frequency=2500.0)
        Out.ar(bus=0, source=Pan2.ar(source=sig * env * builder["amp"]))

    pluck_def = builder.build(name="pluck")

    line = Pseq([0, 3, 5, 7, 10, 7, 5, 3])

    with Server(Options(verbosity=0, load_synthdefs=False)) as server:
        glide_def.send(server)
        pluck_def.send(server)
        server.sync()

        clock = Clock(bpm=BPM)

        # -- Pbind vs Pmono, same notes --------------------------------------
        print("Pbind: one synth per note -- eight separate attacks")
        Pbind(
            instrument="glide",
            degree=line,
            octave=3,
            scale="minor",
            dur=0.35,
            amp=0.18,
        ).play(clock, server)
        time.sleep(0.35 * 8 + 0.8)

        print("Pmono: one synth retuned per note -- a single gliding line")
        Pmono(
            "glide",
            degree=line,
            octave=3,
            scale="minor",
            dur=0.35,
            amp=0.18,
        ).play(clock, server)
        time.sleep(0.35 * 8 + 1.0)

        print("Pmono with a longer lag -- slower portamento")
        Pmono(
            "glide",
            degree=line,
            octave=3,
            scale="minor",
            dur=0.35,
            lag=0.3,
            amp=0.18,
        ).play(clock, server)
        time.sleep(0.35 * 8 + 1.0)

        # -- Pdef: replace a running part ------------------------------------
        print("\nPdef: swapping a running part without stopping playback")
        Pdef.clear()
        Pdef(
            "riff",
            Pn(
                Pbind(
                    instrument="pluck",
                    degree=Pseq([0, 2, 4, 2]),
                    dur=0.25,
                    amp=0.14,
                )
            ),
        )
        player = Pdef("riff").play(clock, server)
        print("  original riff (degrees 0 2 4 2)")
        time.sleep(2.0)

        Pdef(
            "riff",
            Pn(
                Pbind(
                    instrument="pluck",
                    degree=Pseq([7, 9, 11, 9, 7, 4]),
                    dur=0.25,
                    amp=0.14,
                )
            ),
        )
        print("  swapped -> higher riff, no gap")
        time.sleep(2.0)

        Pdef(
            "riff",
            Pn(
                Pbind(
                    instrument="pluck",
                    degree=Pseq([0, 7]),
                    octave=Pseq([4, 5]),
                    scale="minor_pentatonic",
                    dur=0.5,
                    amp=0.14,
                )
            ),
        )
        print("  swapped again -> sparse pentatonic")
        time.sleep(2.5)
        player.stop()
        time.sleep(0.4)

        # -- Pfin / Pfindur ---------------------------------------------------
        print("\nPfin(5): exactly five events from an endless pattern")
        Pfin(
            5,
            Pn(Pbind(instrument="pluck", degree=Pseq([0, 2, 4]), dur=0.3, amp=0.14)),
        ).play(clock, server)
        time.sleep(0.3 * 5 + 0.8)

        print("Pfindur(4 beats): bounded by duration, last note clipped to fit")
        Pfindur(
            4.0,
            Pn(
                Pbind(
                    instrument="pluck",
                    degree=Pseq([0, 2, 4, 5, 7]),
                    dur=0.75,
                    amp=0.14,
                )
            ),
        ).play(clock, server)
        time.sleep(4.0 * BEAT + 1.0)

        clock.stop()
        time.sleep(0.4)

    print("Done.")


if __name__ == "__main__":
    main()
