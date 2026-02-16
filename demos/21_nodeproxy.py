"""
21_nodeproxy.py -- NodeProxy and Ndef live coding.

Demonstrates hot-swappable synth definitions via NodeProxy and Ndef.
The source is swapped multiple times while the monitor stays in place,
producing seamless audio transitions.

Requires:
  - nanosynth built with embedded libscsynth (NANOSYNTH_EMBED_SCSYNTH=ON)
"""

import time

from nanosynth import Options, Server
from nanosynth.proxy import Ndef, NodeProxy
from nanosynth.ugens import LFNoise1, LPF, Saw, SinOsc


def main() -> None:
    with Server(Options(verbosity=0, load_synthdefs=False)) as server:
        time.sleep(0.1)

        # -- NodeProxy: manual usage -------------------------------------------
        print("NodeProxy: sine -> saw -> clear")

        proxy = NodeProxy(server)
        proxy.source = lambda: SinOsc.ar(frequency=440) * 0.2
        proxy.play()
        print("  Playing sine at 440 Hz...")
        time.sleep(2.0)

        # Hot-swap to saw wave
        proxy.source = lambda: Saw.ar(frequency=330) * 0.15
        print("  Swapped to saw at 330 Hz...")
        time.sleep(2.0)

        # Hot-swap to filtered noise
        proxy.source = lambda: LPF.ar(
            source=LFNoise1.ar(frequency=800) * 0.2,
            frequency=600,
        )
        print("  Swapped to filtered noise...")
        time.sleep(2.0)

        proxy.clear()
        print("  Cleared.")
        time.sleep(0.3)

        # -- Ndef: named proxy registry ----------------------------------------
        print("\nNdef: named proxy registry")

        Ndef(server, "pad", lambda: SinOsc.ar(frequency=220) * 0.2)
        Ndef(server, "pad").play()
        print("  Ndef 'pad': sine 220 Hz")
        time.sleep(1.5)

        # Hot-swap via Ndef
        Ndef(server, "pad", lambda: Saw.ar(frequency=165) * 0.15)
        print("  Ndef 'pad': swapped to saw 165 Hz")
        time.sleep(1.5)

        # Second named proxy
        Ndef(server, "high", lambda: SinOsc.ar(frequency=880) * 0.1)
        Ndef(server, "high").play()
        print("  Ndef 'high': sine 880 Hz (layered)")
        time.sleep(2.0)

        # Clear all
        Ndef.clear_all(server)
        print("  Cleared all Ndefs.")
        time.sleep(0.5)

    print("Done.")


if __name__ == "__main__":
    main()
