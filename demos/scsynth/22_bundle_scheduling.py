"""
22_bundle_scheduling.py -- Timestamped OSC bundles and scheduling latency.

The audible point: send the same 16-click rhythm twice while a background
thread hogs the GIL.  Sent as immediate messages, the clicks wobble because
each one lands whenever Python got round to it.  Sent inside `server.at()`,
they are stamped ahead of time and the engine places them exactly -- the
rhythm stays rigid no matter what Python is doing.

Also shows `send_bundle()`, the lower-level form, applying several parameter
changes atomically on one control block.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import threading
import time

from nanosynth import Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.osc import OscMessage
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import LPF, Out, Pan2, Saw, SinOsc

CLICKS = 16
INTERVAL = 0.15  # seconds between clicks


def _burn_cpu(stop: threading.Event) -> None:
    """Compete for the GIL, the way a real program's other work would."""
    while not stop.is_set():
        sum(i * i for i in range(20000))


def main() -> None:
    # -- SynthDef: short click ------------------------------------------------
    with SynthDefBuilder(freq=1200.0, amp=0.3) as builder:
        env = EnvGen.kr(
            envelope=Envelope.percussive(attack_time=0.001, release_time=0.08),
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = SinOsc.ar(frequency=builder["freq"]) * env * builder["amp"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    click_def = builder.build(name="click")

    # -- SynthDef: sustained tone whose params are swept ----------------------
    with SynthDefBuilder(freq=110.0, cutoff=400.0, amp=0.2, gate=1.0) as builder:
        env = EnvGen.kr(
            envelope=Envelope.asr(attack_time=0.05, release_time=0.3),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        sig = Saw.ar(frequency=builder["freq"])
        sig = LPF.ar(source=sig, frequency=builder["cutoff"])
        sig = sig * env * builder["amp"]
        Out.ar(bus=0, source=Pan2.ar(source=sig))

    tone_def = builder.build(name="bundle_tone")

    with Server(Options(verbosity=0, load_synthdefs=False)) as server:
        click_def.send(server)
        tone_def.send(server)
        server.sync()

        stop = threading.Event()
        hog = threading.Thread(target=_burn_cpu, args=(stop,), daemon=True)
        hog.start()

        try:
            # -- A: immediate messages, at the mercy of the scheduler ----------
            print("A: 16 clicks sent as immediate messages (under GIL load)")
            print("   -- listen for the wobble in the rhythm")
            target = time.monotonic()
            for _ in range(CLICKS):
                target += INTERVAL
                delay = target - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                # Whenever this thread happens to wake is when the note starts.
                server.synth("click", freq=1200.0, amp=0.3)
            time.sleep(0.5)

            # -- B: timestamped bundles, placed by the engine ------------------
            print("\nB: the same 16 clicks sent as timestamped bundles")
            print("   -- same GIL load, but the rhythm is rigid")
            onset = time.time() + 0.3  # a little lead-in
            for index in range(CLICKS):
                # All 16 are sent right now; the engine holds each until its
                # stamped moment, so Python's timing stops mattering.
                with server.at(onset + index * INTERVAL):
                    server.synth("click", freq=1600.0, amp=0.3)
            time.sleep(CLICKS * INTERVAL + 0.8)

        finally:
            stop.set()
            hog.join(timeout=1.0)

        # -- C: send_bundle -- several changes on one control block ------------
        print("\nC: send_bundle() applies a chord change atomically")
        voices = [
            server.synth("bundle_tone", freq=f, cutoff=400.0, amp=0.15)
            for f in (110.0, 165.0, 220.0)
        ]
        time.sleep(1.5)

        # One bundle: all three voices move together, on the same sample.
        # Sent as separate messages they could straddle a control block and
        # briefly sound a chord nobody asked for.
        server.send_bundle(
            [
                OscMessage("/n_set", int(voices[0]), "freq", 98.0, "cutoff", 1800.0),
                OscMessage("/n_set", int(voices[1]), "freq", 147.0, "cutoff", 1800.0),
                OscMessage("/n_set", int(voices[2]), "freq", 196.0, "cutoff", 1800.0),
            ]
        )
        print("   chord moved, filter opened -- all in one bundle")
        time.sleep(1.5)

        # Release them together, half a second from now.
        release_at = time.time() + 0.5
        with server.at(release_at):
            for voice in voices:
                server.set(voice, gate=0.0)
        print("   scheduled a synchronised release 0.5s ahead")
        time.sleep(1.5)

    print("Done.")


if __name__ == "__main__":
    main()
