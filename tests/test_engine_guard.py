"""Test the cross-engine process guard.

scsynth and supernova embed the full SuperCollider core and share
process-global state; creating one kind after the other has run in the same
process segfaults. A C++ guard converts that crash into a clean
``ServerCannotBoot``. This is verified in an isolated subprocess (so it does not
contaminate the test process's engine/env state) and uses NRT to claim the
scsynth side, which needs no audio device -- so the test is headless-safe.
"""

import os
import subprocess
import sys
import textwrap


def _run(script: str) -> subprocess.CompletedProcess:
    # Start from a clean engine-guard env so the subprocess is deterministic
    # regardless of what the parent process already claimed.
    env = {k: v for k, v in os.environ.items() if k != "NANOSYNTH_ACTIVE_ENGINE"}
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


def test_supernova_blocked_after_scsynth_nrt() -> None:
    result = _run(
        """
        import os, tempfile
        from nanosynth import Server, EmbeddedSupernovaProtocol
        from nanosynth.scsynth import Options
        from nanosynth.score import Score
        from nanosynth.osc import OscMessage
        from nanosynth.exceptions import ServerCannotBoot

        # NRT render creates a scsynth World (no audio device needed),
        # claiming the scsynth engine for this process.
        score = Score()
        score.add(0.05, OscMessage("/c_set", 0, 0))
        fd, path = tempfile.mkstemp(suffix=".wav"); os.close(fd)
        score.render(path, sample_rate=44100, options=Options(verbosity=-1))
        os.unlink(path)

        try:
            Server(Options(verbosity=-1), protocol=EmbeddedSupernovaProtocol()).boot()
        except ServerCannotBoot as exc:
            assert "process" in str(exc)
            print("GUARD_OK")
        else:
            print("GUARD_FAIL: supernova booted without error")
        """
    )
    # returncode 0 proves the guard raised cleanly instead of segfaulting.
    assert result.returncode == 0, f"subprocess crashed: {result.stderr}"
    assert "GUARD_OK" in result.stdout, (result.stdout, result.stderr)


def test_same_engine_kind_is_not_blocked() -> None:
    # Two NRT renders (both scsynth) in one process must coexist fine.
    result = _run(
        """
        import os, tempfile
        from nanosynth.scsynth import Options
        from nanosynth.score import Score
        from nanosynth.osc import OscMessage

        for _ in range(2):
            score = Score()
            score.add(0.05, OscMessage("/c_set", 0, 0))
            fd, path = tempfile.mkstemp(suffix=".wav"); os.close(fd)
            score.render(path, sample_rate=44100, options=Options(verbosity=-1))
            os.unlink(path)
        print("SAME_KIND_OK")
        """
    )
    assert result.returncode == 0, f"subprocess crashed: {result.stderr}"
    assert "SAME_KIND_OK" in result.stdout, (result.stdout, result.stderr)
