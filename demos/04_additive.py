"""
04_additive.py -- Additive synthesis.

Builds a tone by summing sine partials with decreasing amplitudes.
An LFO slowly modulates the balance between odd and even harmonics,
creating a timbral shift from hollow (odd-only, like a square wave)
to bright (all harmonics).

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import LFTri, Out, Pan2, SinOsc


def main() -> None:
    # -- SynthDef: additive with LFO-morphing harmonics -----------------------
    with SynthDefBuilder(frequency=200.0, amplitude=0.3) as builder:
        freq = builder["frequency"]

        # LFO: 0..1 controls even-harmonic level (odd harmonics always present)
        even_mix = LFTri.kr(frequency=0.15) * 0.5 + 0.5

        # Odd harmonics (1, 3, 5, 7)
        sig = SinOsc.ar(frequency=freq) * 1.0
        sig = sig + SinOsc.ar(frequency=freq * 3.0) * 0.33
        sig = sig + SinOsc.ar(frequency=freq * 5.0) * 0.2
        sig = sig + SinOsc.ar(frequency=freq * 7.0) * 0.14

        # Even harmonics (2, 4, 6) scaled by LFO
        sig = sig + SinOsc.ar(frequency=freq * 2.0) * 0.5 * even_mix
        sig = sig + SinOsc.ar(frequency=freq * 4.0) * 0.25 * even_mix
        sig = sig + SinOsc.ar(frequency=freq * 6.0) * 0.17 * even_mix

        sig = sig * 0.2  # normalize headroom
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.5, sustain_time=5.0, release_time=1.0
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    synthdef = builder.build(name="additive")
    print(f"SynthDef '{synthdef.name}' compiled: {len(synthdef.compile())} bytes")

    # -- Boot and play --------------------------------------------------------
    with Server(Options(verbosity=0)) as server:
        synthdef.send(server)
        time.sleep(0.1)

        print("Playing additive synthesis with morphing harmonics (6.5s)...")
        server.synth("additive", frequency=150.0, amplitude=0.4)
        time.sleep(7.0)

    print("Done.")


if __name__ == "__main__":
    main()
