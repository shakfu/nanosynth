"""
19_nrt_render.py -- Offline (NRT) rendering to WAV and AIFF.

Renders a short sequence of sine tones to build/nrt_demo.wav and
build/nrt_demo.aiff without using real-time audio hardware. Useful for
batch processing, CI pipelines, and environments without audio devices.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

from pathlib import Path

from nanosynth import OscMessage, Score, SynthDefBuilder
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction
from nanosynth.ugens import Out, Pan2, SinOsc


def build_synthdef():
    """Build a simple sine SynthDef with a percussive envelope."""
    with SynthDefBuilder(freq=440.0, amp=0.3, pan=0.0) as builder:
        sig = SinOsc.ar(frequency=builder["freq"]) * builder["amp"]
        env = EnvGen.kr(
            envelope=Envelope.percussive(attack_time=0.01, release_time=0.4),
            done_action=DoneAction.FREE_SYNTH,
        )
        Out.ar(bus=0, source=Pan2.ar(source=sig * env, position=builder["pan"]))
    return builder.build(name="nrt_sine")


def build_score(synthdef):
    """Build a Score with a short melodic sequence."""
    score = Score()

    # Load the SynthDef at time 0
    score.add_synthdef(0.0, synthdef)

    # C major arpeggio with panning
    notes = [
        (0.0, 261.63, 0.4, -0.5),  # C4
        (0.3, 329.63, 0.35, -0.25),  # E4
        (0.6, 392.00, 0.3, 0.0),  # G4
        (0.9, 523.25, 0.3, 0.25),  # C5
        (1.2, 659.26, 0.25, 0.5),  # E5
        (1.5, 783.99, 0.2, 0.75),  # G5
        (1.8, 1046.50, 0.2, 0.0),  # C6
    ]

    for time, freq, amp, pan in notes:
        score.add_synth(time, "nrt_sine", freq=freq, amp=amp, pan=pan)

    # End marker -- ensures the score runs long enough for the last note
    score.add(2.5, OscMessage("/c_set", 0, 0))
    return score


def main() -> None:
    outdir = Path("build")
    outdir.mkdir(exist_ok=True)

    synthdef = build_synthdef()
    print(f"SynthDef '{synthdef.name}' compiled: {len(synthdef.compile())} bytes")
    print(synthdef.dump_ugens())

    score = build_score(synthdef)
    print(f"\nScore: {len(score._entries)} entries, {score.duration():.1f}s duration")

    # -- Render WAV -----------------------------------------------------------
    wav_path = outdir / "nrt_demo.wav"
    print(f"\nRendering {wav_path} (44100 Hz, int16, stereo)...")
    score.render(
        wav_path,
        sample_rate=44100,
        header_format="WAV",
        sample_format="int16",
        output_channels=2,
    )
    size = wav_path.stat().st_size
    print(f"  -> {wav_path} ({size:,} bytes)")

    # -- Render AIFF ----------------------------------------------------------
    aiff_path = outdir / "nrt_demo.aiff"
    print(f"\nRendering {aiff_path} (48000 Hz, int24, stereo)...")
    score.render(
        aiff_path,
        sample_rate=48000,
        header_format="AIFF",
        sample_format="int24",
        output_channels=2,
    )
    size = aiff_path.stat().st_size
    print(f"  -> {aiff_path} ({size:,} bytes)")

    print("\nDone. Files written to build/")


if __name__ == "__main__":
    main()
