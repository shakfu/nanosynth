"""
10_managed_pargroup.py -- Managed ParGroup context manager.

Demonstrates server.managed_par_group() for automatic cleanup of parallel
node trees. Each chord in the progression is a managed ParGroup -- voices
inside it are freed on context exit, guaranteeing cleanup even on exceptions.

Requires:
  - nanosynth built with embedded supernova (NANOSYNTH_EMBED_SUPERNOVA=ON)
"""

import time

from nanosynth import EmbeddedSupernovaProtocol, Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import LFNoise2, LPF, Out, Saw, SinOsc


def main() -> None:
    # -- SynthDef: gated saw pad with filter drift ------------------------------
    with SynthDefBuilder(
        frequency=220.0, cutoff=1200.0, amplitude=0.25, gate=1.0,
    ) as builder:
        sig = Saw.ar(frequency=builder["frequency"])
        lfo = LFNoise2.kr(frequency=0.3)
        cutoff = builder["cutoff"] + lfo * 400.0
        sig = LPF.ar(source=sig, frequency=cutoff)
        env = EnvGen.kr(
            envelope=Envelope.adsr(
                attack_time=0.8, decay_time=0.3,
                sustain=0.6, release_time=1.5,
            ),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=[sig, sig])

    pad_def = builder.build(name="pad")

    # -- SynthDef: sine bell (self-freeing) -------------------------------------
    with SynthDefBuilder(frequency=880.0, amplitude=0.15) as builder:
        sig = SinOsc.ar(frequency=builder["frequency"])
        env = EnvGen.kr(
            envelope=Envelope.percussive(attack_time=0.005, release_time=0.8),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=[sig, sig])

    bell_def = builder.build(name="bell")

    # -- Chord progression ------------------------------------------------------
    chords = [
        ("Am", [220.00, 261.63, 329.63]),
        ("F", [174.61, 220.00, 261.63]),
        ("C", [261.63, 329.63, 392.00]),
        ("G", [196.00, 246.94, 293.66]),
    ]

    with Server(
        Options(verbosity=0, load_synthdefs=False),
        protocol=EmbeddedSupernovaProtocol(),
    ) as server:
        pad_def.send(server)
        bell_def.send(server)
        time.sleep(0.1)

        print("Playing chord progression with managed_par_group...")

        for chord_name, freqs in chords:
            print(f"  {chord_name}...")

            # Each chord's voices run in a managed ParGroup --
            # supernova can compute the three pad voices in parallel,
            # and cleanup is automatic on context exit
            with server.managed_par_group(target=1) as par:
                nodes = []
                for freq in freqs:
                    node = server.synth(
                        "pad",
                        target=par,
                        frequency=freq,
                        cutoff=1000.0,
                        amplitude=0.15,
                    )
                    nodes.append(node)

                # Accent bell on the root
                bell_def.play(server, frequency=freqs[0] * 2, amplitude=0.1)

                time.sleep(2.5)

                # Brighten filter before releasing
                for node in nodes:
                    server.set(node, cutoff=2000.0)
                time.sleep(0.5)

                # Release gates for ADSR release tails
                for node in nodes:
                    server.set(node, gate=0.0)
                time.sleep(1.5)

            # ParGroup freed here -- any leftover voices cleaned up

        time.sleep(0.5)

    print("Done.")


if __name__ == "__main__":
    main()
