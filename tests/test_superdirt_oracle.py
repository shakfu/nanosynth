"""SuperDirt attached to nanosynth's engine as client 1 (scripts/superdirt_oracle.py).

Opt-in: needs ``NANOSYNTH_TEST_ORACLE=1``, an audio device, and the oracle built
with ``python scripts/superdirt_oracle.py setup``.
"""

import os
import socket
import sys
import time
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
superdirt_oracle = pytest.importorskip("superdirt_oracle")

pytestmark = pytest.mark.skipif(
    not os.environ.get("NANOSYNTH_TEST_ORACLE") or not superdirt_oracle.SCLANG.exists(),
    reason="set NANOSYNTH_TEST_ORACLE=1 and run superdirt_oracle.py setup",
)

np = pytest.importorskip("numpy")


def _play(params: dict, at: float, port: int = 57120) -> None:
    from nanosynth.osc import OscBundle, OscMessage

    args = [x for kv in params.items() for x in kv]
    bundle = OscBundle(timestamp=at, contents=[OscMessage("/dirt/play", *args)])
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(bundle.to_datagram(), ("127.0.0.1", port))


def _onsets(path: Path, threshold: float = 0.05) -> tuple[list[float], int]:
    with wave.open(str(path)) as w:
        rate, ch = w.getframerate(), w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    mono = np.abs(data.reshape(-1, ch)).max(axis=1) / 32768.0
    onsets, last = [], -1.0
    for i in np.flatnonzero(mono > threshold):
        t = i / rate
        if t - last > 0.1:
            onsets.append(t)
        last = t
    return onsets, rate


def test_superdirt_plays_through_nanosynth(tmp_path: Path) -> None:
    from nanosynth import Server

    samples = superdirt_oracle.CACHE / "Dirt-Samples" / "bd"
    server = Server(superdirt_oracle.oracle_options())
    server.boot()
    try:
        own = server.alloc_buffer(1024)
        with superdirt_oracle.superdirt(server, [str(samples)]):
            out = tmp_path / "out.wav"
            server.record(out, num_channels=2)
            start = time.time() + 0.5
            for k in range(4):
                _play(
                    {"s": "bd", "n": 0, "orbit": 0, "cps": 1.0, "delta": 0.25},
                    start + k * 0.25,
                )
            time.sleep(2.0)
            server.stop_recording()
            # nanosynth's buffers stay in client 0's slice, below SuperDirt's.
            assert own < superdirt_oracle.BUFFERS // superdirt_oracle.MAX_LOGINS
    finally:
        server.quit()
    onsets, _ = _onsets(out)
    assert len(onsets) == 4, onsets
    gaps = np.diff(onsets)
    assert np.allclose(gaps, 0.25, atol=0.003), gaps
