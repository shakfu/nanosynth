"""
07_demand_sequencer.py -- Demand-rate sequencing with parallel voices.

Two server-side sequencers (Dseq bass, Drand melody) placed in a ParGroup
so supernova can schedule them across CPU cores. No host-side scheduling
needed -- all timing is driven by Duty/Impulse on the server.

Requires:
  - nanosynth built with embedded supernova (NANOSYNTH_EMBED_SUPERNOVA=ON)
"""

import time

from nanosynth import AddAction, EmbeddedSupernovaProtocol, Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import (
    Decay2,
    Drand,
    Dseq,
    Duty,
    Impulse,
    LPF,
    Out,
    Pan2,
    Saw,
    SinOsc,
)


def main() -> None:
    # -- SynthDef: deterministic bass (Dseq) ------------------------------------
    with SynthDefBuilder(amplitude=0.3) as builder:
        freq = Duty.kr(
            duration=0.5,
            level=Dseq.dr(
                repeats=4,
                sequence=[82.41, 98.00, 110.00, 123.47],
            ),
        )
        sig = Saw.ar(frequency=freq)
        sig = LPF.ar(source=sig, frequency=400.0)

        tick = Impulse.kr(frequency=2.0)
        amp_env = Decay2.kr(source=tick, attack_time=0.01, decay_time=0.4)

        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.01,
                sustain_time=7.9,
                release_time=0.1,
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * amp_env * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=-0.3))

    bass_def = builder.build(name="bass_seq")

    # -- SynthDef: random melody (Drand) ----------------------------------------
    with SynthDefBuilder(amplitude=0.2) as builder:
        freq = Duty.kr(
            duration=0.25,
            level=Drand.dr(
                repeats=32,
                sequence=[440.0, 523.25, 587.33, 659.26, 783.99],
            ),
        )
        sig = SinOsc.ar(frequency=freq)

        tick = Impulse.kr(frequency=4.0)
        amp_env = Decay2.kr(source=tick, attack_time=0.005, decay_time=0.15)

        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.01,
                sustain_time=7.9,
                release_time=0.1,
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * amp_env * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=0.3))

    melody_def = builder.build(name="melody_seq")

    # -- Boot and play ----------------------------------------------------------
    with Server(
        Options(verbosity=0, load_synthdefs=False),
        protocol=EmbeddedSupernovaProtocol(),
    ) as server:
        bass_def.send(server)
        melody_def.send(server)
        time.sleep(0.1)

        # ParGroup: bass and melody are independent, run in parallel
        par = server.par_group(target=1, action=AddAction.ADD_TO_HEAD)
        print(f"ParGroup {par}: bass + melody sequencers in parallel")

        server.synth("bass_seq", target=par, amplitude=0.35)
        server.synth("melody_seq", target=par, amplitude=0.25)

        print("  Bass (left): Dseq deterministic pattern")
        print("  Melody (right): Drand random pentatonic")
        print("Playing for 8 seconds...")
        time.sleep(9.0)

    print("Done.")


if __name__ == "__main__":
    main()
