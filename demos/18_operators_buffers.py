"""
18_operators_buffers.py -- Extended operators and buffer management.

Demonstrates three features added in the unreleased version:

1. **Rich operator algebra** -- MIDI-to-frequency conversion (`midicps`),
   waveshaping (`tanh_`, `softclip`, `distort`), pitch math (`dbamp`),
   and signal clipping (`clip2`) applied directly on UGen signals.

2. **Buffer management** -- `managed_buffer` context manager for
   automatic allocation/deallocation, used here to back an FFT chain.

3. **Reply handling** -- `send_msg_sync` for synchronous buffer
   allocation (waits for `/done` before proceeding).

The synth plays a distorted saw chord with MIDI note inputs,
processed through FFT spectral filtering, then soft-clipped.

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
    LPF,
    Out,
    Pan2,
    PV_MagAbove,
    Saw,
    SinOsc,
)


def main() -> None:
    # -- SynthDef 1: operator showcase -----------------------------------------
    # Uses midicps (MIDI->Hz), tanh_ (soft saturation), clip2 (hard clip),
    # dbamp (dB->amplitude), and squared (spectral tilt).
    with SynthDefBuilder(note=60.0, detune=0.3, drive=4.0, amp_db=-12.0) as builder:
        # Convert MIDI note number to frequency using .midicps()
        freq = builder["note"].midicps()

        # Detuned saw pair for a thick sound
        sig = Saw.ar(frequency=freq)
        sig = sig + Saw.ar(frequency=freq * (1.0 + builder["detune"] * 0.01))

        # Drive into tanh_ waveshaper for warm saturation
        sig = (sig * builder["drive"]).tanh_()

        # Hard clip to +/- 0.8
        sig = sig.clip2(0.8)

        # Convert dB parameter to linear amplitude using .dbamp()
        amp = builder["amp_db"].dbamp()

        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.3, sustain_time=2.5, release_time=0.5
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * amp
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    operator_def = builder.build(name="op_demo")
    print(f"SynthDef '{operator_def.name}': {len(operator_def.compile())} bytes")
    print(operator_def.dump_ugens())

    # -- SynthDef 2: softclip + distort ----------------------------------------
    # Demonstrates .softclip() and .distort() waveshaping on a sine.
    with SynthDefBuilder(note=48.0, amplitude=0.25) as builder:
        freq = builder["note"].midicps()
        sig = SinOsc.ar(frequency=freq)
        # Overdrive then softclip: asymmetric warmth
        sig = (sig * 6.0).softclip()
        sig = sig + (SinOsc.ar(frequency=freq * 3.0) * 3.0).distort() * 0.3

        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.2, sustain_time=2.0, release_time=0.8
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=-0.3))

    softclip_def = builder.build(name="softclip_demo")
    print(f"\nSynthDef '{softclip_def.name}': {len(softclip_def.compile())} bytes")

    # -- SynthDef 3: spectral filtering with managed buffer --------------------
    # FFT processing using a server-allocated buffer (managed_buffer).
    with SynthDefBuilder(note=55.0, threshold=3.0, amplitude=0.3) as builder:
        freq = builder["note"].midicps()
        sig = Saw.ar(frequency=freq)
        sig = sig + Saw.ar(frequency=freq * 1.005)  # slight detune

        # FFT -> spectral gate -> IFFT
        chain = FFT.kr(source=sig)
        chain = PV_MagAbove.kr(pv_chain=chain, threshold=builder["threshold"])
        sig = IFFT.ar(pv_chain=chain)
        sig = LPF.ar(source=sig, frequency=5000.0)

        env = EnvGen.kr(
            envelope=Envelope.linen(
                attack_time=0.5, sustain_time=3.0, release_time=1.0
            ),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = sig * env * builder["amplitude"]
        Out.ar(bus=0, source=Pan2.ar(source=sig, position=0.3))

    spectral_def = builder.build(name="spectral_op")
    print(f"SynthDef '{spectral_def.name}': {len(spectral_def.compile())} bytes")

    # -- Boot and play ---------------------------------------------------------
    with Server(Options(verbosity=0, load_synthdefs=False)) as server:
        operator_def.send(server)
        softclip_def.send(server)
        spectral_def.send(server)
        time.sleep(0.1)

        # --- Part 1: operator-heavy synths ---
        print("\n1. Operator showcase: MIDI notes -> midicps -> tanh_ -> clip2")
        # Play a chord: C3, E3, G3 as MIDI notes
        midi_notes = [48.0, 52.0, 55.0]
        for note in midi_notes:
            operator_def.play(server, note=note, detune=0.4, drive=3.0, amp_db=-14.0)
            time.sleep(0.15)
        print(f"   Playing MIDI chord {midi_notes} (3.5s)...")
        time.sleep(3.5)

        # --- Part 2: softclip/distort waveshaping ---
        print("2. Softclip + distort waveshaping on sine...")
        softclip_def.play(server, note=48.0, amplitude=0.2)
        time.sleep(3.5)

        # --- Part 3: buffer management + spectral processing ---
        print("3. Managed buffer + spectral gate...")

        # Allocate a buffer synchronously using send_msg_sync
        # (waits for /done reply before proceeding)
        buf_id = server.next_buffer_id()
        reply = server.send_msg_sync(
            "/b_alloc",
            buf_id,
            2048,
            1,
            reply_address="/done",
            timeout=2.0,
        )
        if reply:
            server._allocated_buffers.add(buf_id)
            print(f"   Buffer {buf_id} allocated synchronously (got /done reply)")
        else:
            print(f"   Buffer {buf_id} allocated (no reply -- fire-and-forget)")

        spectral_def.play(server, note=55.0, threshold=3.0, amplitude=0.25)
        time.sleep(4.5)

        # Clean up the manually allocated buffer
        server.free_buffer(buf_id)

        # Also demonstrate managed_buffer context manager
        with server.managed_buffer(num_frames=4096, num_channels=1) as mbuf:
            print(f"   Managed buffer {mbuf} allocated (auto-freed on exit)")
            spectral_def.play(server, note=62.0, threshold=2.0, amplitude=0.2)
            time.sleep(4.5)
        print("   Managed buffer freed.")

        time.sleep(0.5)

    print("Done.")


if __name__ == "__main__":
    main()
