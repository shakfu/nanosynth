"""
13_server_pad.py -- Gated pad with managed_synth.

Demonstrates managed_synth() with a gated ADSR envelope. Each chord in
the progression is a managed_synth context -- the node is freed on exit,
guaranteeing cleanup even if an exception occurs mid-performance.

Also demonstrates:
  - Server context manager for boot/quit lifecycle
  - SynthDef.send() / SynthDef.play()
  - server.set() for parameter updates on a running node
  - server.managed_group() for grouping voices

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import LFNoise2, LPF, Out, Saw, SinOsc


def main() -> None:
    # -- SynthDef 1: gated saw pad with filter LFO ----------------------------
    with SynthDefBuilder(
        frequency=220.0,
        cutoff=1200.0,
        amplitude=0.25,
        gate=1.0,
    ) as builder:
        sig = Saw.ar(frequency=builder["frequency"])
        # Slow filter drift
        lfo = LFNoise2.kr(frequency=0.3)
        cutoff = builder["cutoff"] + lfo * 400.0
        sig = LPF.ar(source=sig, frequency=cutoff)
        env = EnvGen.kr(
            envelope=Envelope.adsr(
                attack_time=0.8,
                decay_time=0.3,
                sustain=0.6,
                release_time=1.5,
            ),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=[sig, sig])

    pad_def = builder.build(name="pad")
    print(f"SynthDef '{pad_def.name}' compiled: {len(pad_def.compile())} bytes")
    print(pad_def.dump_ugens())

    # -- SynthDef 2: simple sine bell (self-freeing) --------------------------
    with SynthDefBuilder(frequency=880.0, amplitude=0.15) as builder:
        sig = SinOsc.ar(frequency=builder["frequency"])
        env = EnvGen.kr(
            envelope=Envelope.percussive(attack_time=0.005, release_time=0.8),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=[sig, sig])

    bell_def = builder.build(name="bell")

    # -- Chord progression ----------------------------------------------------
    chords = [
        ("Am", [220.00, 261.63, 329.63]),
        ("F", [174.61, 220.00, 261.63]),
        ("C", [261.63, 329.63, 392.00]),
        ("G", [196.00, 246.94, 293.66]),
    ]

    with Server(Options(verbosity=0, load_synthdefs=False)) as server:
        pad_def.send(server)
        bell_def.send(server)
        time.sleep(0.1)

        print("\nPlaying chord progression with managed_synth...")

        for chord_name, freqs in chords:
            print(f"  {chord_name}...")

            # Create a managed group for this chord's voices
            with server.managed_group(target=1) as group:
                # Spawn one pad voice per note in the chord
                nodes = []
                for freq in freqs:
                    node = server.synth(
                        "pad",
                        target=group,
                        action=0,
                        frequency=freq,
                        cutoff=1000.0,
                        amplitude=0.15,
                    )
                    nodes.append(node)

                # Accent bell on the root
                bell_def.play(server, frequency=freqs[0] * 2, amplitude=0.1)

                # Let the chord sustain
                time.sleep(2.5)

                # Slowly brighten the filter before releasing
                for node in nodes:
                    server.set(node, cutoff=2000.0)
                time.sleep(0.5)

                # Release gates for clean ADSR release tails
                for node in nodes:
                    server.set(node, gate=0.0)
                time.sleep(1.5)

            # Group freed here -- any leftover voices are cleaned up

        # Brief silence before exit
        time.sleep(0.5)

    print("Done.")


if __name__ == "__main__":
    main()
