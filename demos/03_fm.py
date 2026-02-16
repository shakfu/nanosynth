"""
03_fm.py -- FM synthesis + melody.

Two SynthDefs:
  1. FM synth with controllable carrier_freq, mod_ratio, mod_index, gate
     (uses Envelope.adsr for amplitude shaping)
  2. FM sweep with XLine-modulated index (self-freeing)

Plays a short melody with the gated FM synth, then fires a self-freeing sweep.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import Out, Pan2, SinOsc, XLine


def main() -> None:
    # -- SynthDef 1: gated FM synth -------------------------------------------
    with SynthDefBuilder(
        carrier_freq=440.0,
        mod_ratio=2.0,
        mod_index=3.0,
        amplitude=0.3,
        gate=1.0,
    ) as builder:
        mod_freq = builder["carrier_freq"] * builder["mod_ratio"]
        modulator = SinOsc.ar(frequency=mod_freq) * builder["mod_index"] * mod_freq
        carrier = SinOsc.ar(frequency=builder["carrier_freq"] + modulator)
        env = EnvGen.kr(
            envelope=Envelope.adsr(
                attack_time=0.01,
                decay_time=0.1,
                sustain=0.7,
                release_time=0.3,
            ),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = carrier * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    fm_def = builder.build(name="fm_synth")
    print(f"SynthDef '{fm_def.name}' compiled: {len(fm_def.compile())} bytes")

    # -- SynthDef 2: self-freeing FM sweep ------------------------------------
    with SynthDefBuilder(carrier_freq=200.0, mod_ratio=3.0, amplitude=0.25) as builder:
        mod_index = XLine.kr(
            start=10.0,
            stop=0.1,
            duration=4.0,
            done_action=DoneAction.FREE_SYNTH,
        )
        mod_freq = builder["carrier_freq"] * builder["mod_ratio"]
        modulator = SinOsc.ar(frequency=mod_freq) * mod_index * mod_freq
        carrier = SinOsc.ar(frequency=builder["carrier_freq"] + modulator)
        sig = carrier * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    sweep_def = builder.build(name="fm_sweep")
    print(f"SynthDef '{sweep_def.name}' compiled: {len(sweep_def.compile())} bytes")

    # -- Boot and play --------------------------------------------------------
    with Server(Options(verbosity=0)) as server:
        fm_def.send(server)
        sweep_def.send(server)
        time.sleep(0.1)

        # Play a short melody with the gated FM synth
        melody = [
            (261.63, 0.3),  # C4
            (293.66, 0.3),  # D4
            (329.63, 0.3),  # E4
            (349.23, 0.3),  # F4
            (392.00, 0.5),  # G4
            (440.00, 0.5),  # A4
            (493.88, 0.5),  # B4
            (523.25, 0.8),  # C5
        ]

        print("Playing FM melody...")
        for freq, dur in melody:
            node = server.synth(
                "fm_synth",
                carrier_freq=freq,
                mod_ratio=2.0,
                mod_index=3.0,
                amplitude=0.25,
            )
            time.sleep(dur)
            # Release the gate to trigger the envelope release
            node.set(gate=0.0)
            time.sleep(0.05)

        time.sleep(0.5)

        # Fire the self-freeing FM sweep
        print("Playing FM sweep (4s)...")
        server.synth("fm_sweep", carrier_freq=150.0)
        time.sleep(4.5)

    print("Done.")


if __name__ == "__main__":
    main()
