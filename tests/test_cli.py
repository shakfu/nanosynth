"""Tests for the nanosynth CLI."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from nanosynth.cli import main


def test_top_level_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "nanosynth" in captured.out


def test_render_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["render", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "score" in captured.out.lower()


def test_render_missing_script(capsys: pytest.CaptureFixture[str]) -> None:
    """render without a script argument should fail."""
    with pytest.raises(SystemExit) as exc_info:
        main(["render", "-o", "out.wav"])
    assert exc_info.value.code != 0


def test_render_script_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["render", "nonexistent_script.py", "-o", "out.wav"])
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "not found" in captured.err


def test_render_script_no_score(tmp_path: Path) -> None:
    script = tmp_path / "no_score.py"
    script.write_text("x = 42\n")
    with pytest.raises(SystemExit) as exc_info:
        main(["render", str(script), "-o", str(tmp_path / "out.wav")])
    assert exc_info.value.code == 1


def test_render_script_wrong_type(tmp_path: Path) -> None:
    script = tmp_path / "wrong_type.py"
    script.write_text("score = 'not a Score'\n")
    with pytest.raises(SystemExit) as exc_info:
        main(["render", str(script), "-o", str(tmp_path / "out.wav")])
    assert exc_info.value.code == 1


def test_render_invalid_format() -> None:
    """--format with an invalid choice should be rejected by argparse."""
    with pytest.raises(SystemExit) as exc_info:
        main(["render", "script.py", "-o", "out.wav", "--format", "MP3"])
    assert exc_info.value.code != 0


def test_render_invalid_sample_format() -> None:
    """--sample-format with an invalid choice should be rejected by argparse."""
    with pytest.raises(SystemExit) as exc_info:
        main(["render", "script.py", "-o", "out.wav", "--sample-format", "float64"])
    assert exc_info.value.code != 0


def test_render_success(tmp_path: Path) -> None:
    """Full render through the CLI with a real Score."""
    script = tmp_path / "render_score.py"
    output = tmp_path / "output.wav"
    script.write_text(
        textwrap.dedent("""\
        from nanosynth import Score, SynthDefBuilder, SinOsc, Out, OscMessage

        with SynthDefBuilder(freq=440.0) as b:
            Out.ar(bus=0, source=SinOsc.ar(frequency=b["freq"]) * 0.3)
        sd = b.build(name="sine")

        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, "sine", freq=440.0)
        score.add(0.5, OscMessage("/n_free", 1000))
    """)
    )
    main(["render", str(script), "-o", str(output)])
    assert output.exists()
    assert output.stat().st_size > 0


def test_no_command_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """Running with no subcommand prints help and exits 0."""
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "nanosynth" in captured.out
