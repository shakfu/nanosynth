"""
14_spectral.py -- FFT spectral processing.

Demonstrates phase vocoder UGens:
  1. Spectral gate -- PV_MagAbove removes bins below a threshold,
     creating a sparse, crystalline version of the input
  2. Spectral freeze -- PV_MagFreeze captures a spectral snapshot and
     sustains it as a drone, then unfreezes
  3. Spectral scramble -- PV_BinScramble randomizes bin positions on
     each trigger for a glitchy, granular texture

Each section processes a rich input signal (detuned saws) through
FFT -> PV processing -> IFFT.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import (
    FFT,
    IFFT,
    Dust,
    LPF,
    Out,
    Pan2,
    PV_BinScramble,
    PV_MagAbove,
    PV_MagFreeze,
    Saw,
)


def main() -> None:
    # -- SynthDef 1: spectral gate (PV_MagAbove) ------------------------------
    with SynthDefBuilder(frequency=220.0, threshold=5.0, amplitude=0.3) as builder:
        sig = Saw.ar(frequency=builder["frequency"])
        sig = sig + Saw.ar(frequency=builder["frequency"] * 1.003) * 0.5
        chain = FFT.kr(source=sig)
        chain = PV_MagAbove.kr(pv_chain=chain, threshold=builder["threshold"])
        sig = IFFT.ar(pv_chain=chain)
        sig = LPF.ar(source=sig, frequency=6000.0)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.5, sustain_time=4.0, release_time=1.0
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    gate_def = builder.build(name="spectral_gate")
    print(f"SynthDef '{gate_def.name}' compiled: {len(gate_def.compile())} bytes")

    # -- SynthDef 2: spectral freeze (PV_MagFreeze) ---------------------------
    with SynthDefBuilder(frequency=330.0, freeze=0.0, amplitude=0.3) as builder:
        sig = Saw.ar(frequency=builder["frequency"])
        sig = sig + Saw.ar(frequency=builder["frequency"] * 0.5) * 0.3
        chain = FFT.kr(source=sig)
        chain = PV_MagFreeze.kr(pv_chain=chain, freeze=builder["freeze"])
        sig = IFFT.ar(pv_chain=chain)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.3, sustain_time=7.0, release_time=1.0
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    freeze_def = builder.build(name="spectral_freeze")
    print(f"SynthDef '{freeze_def.name}' compiled: {len(freeze_def.compile())} bytes")

    # -- SynthDef 3: spectral scramble (PV_BinScramble) -----------------------
    with SynthDefBuilder(frequency=440.0, wipe=0.5, amplitude=0.25) as builder:
        sig = Saw.ar(frequency=builder["frequency"])
        chain = FFT.kr(source=sig)
        # Retriggered scramble: Dust triggers randomize bin order
        chain = PV_BinScramble.kr(
            pv_chain=chain,
            wipe=builder["wipe"],
            width=0.4,
            trigger=Dust.kr(density=4.0),
        )
        sig = IFFT.ar(pv_chain=chain)
        sig = LPF.ar(source=sig, frequency=8000.0)
        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.3, sustain_time=4.0, release_time=0.7
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    scramble_def = builder.build(name="spectral_scramble")
    print(
        f"SynthDef '{scramble_def.name}' compiled: {len(scramble_def.compile())} bytes"
    )

    # -- Boot and play --------------------------------------------------------
    with Server(Options(verbosity=0, load_synthdefs=False)) as server:
        gate_def.send(server)
        freeze_def.send(server)
        scramble_def.send(server)
        time.sleep(0.1)

        print("\n1. Spectral gate: only loud bins pass through...")
        gate_def.play(server, frequency=220.0, threshold=5.0, amplitude=0.3)
        time.sleep(6.0)

        print("2. Spectral freeze: capturing spectrum then freezing...")
        node = freeze_def.play(server, frequency=330.0, freeze=0.0, amplitude=0.25)
        time.sleep(2.0)
        print("   ...frozen!")
        server.set(node, freeze=1.0)
        time.sleep(3.0)
        print("   ...unfrozen!")
        server.set(node, freeze=0.0)
        time.sleep(3.5)

        print("3. Spectral scramble: randomizing bin positions...")
        scramble_def.play(server, frequency=440.0, wipe=0.6, amplitude=0.25)
        time.sleep(5.5)

        time.sleep(0.5)

    print("Done.")


if __name__ == "__main__":
    main()
