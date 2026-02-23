"""Tests for the nanosynth CLI."""

from __future__ import annotations

import pytest

from nanosynth.cli import main


def test_top_level_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "nanosynth" in captured.out


def test_info_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["info", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--list" in captured.out


def test_no_command_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "nanosynth" in captured.out


def test_info_output(capsys: pytest.CaptureFixture[str]) -> None:
    main(["info"])
    captured = capsys.readouterr()
    output = captured.out
    assert "nanosynth" in output
    assert "Python" in output
    assert "Audio backend:" in output
    assert "UGen plugins:" in output
    assert "Plugin count:" in output
    assert "scsynth embedded:" in output
    assert "supernova embedded:" in output


def test_info_shows_version(capsys: pytest.CaptureFixture[str]) -> None:
    import nanosynth

    main(["info"])
    captured = capsys.readouterr()
    assert nanosynth.__version__ in captured.out


def test_info_list_ugens(capsys: pytest.CaptureFixture[str]) -> None:
    main(["info", "--list"])
    captured = capsys.readouterr()
    output = captured.out
    assert "UGens available" in output
    # Spot-check some well-known UGens
    assert "SinOsc" in output
    assert "Out" in output
    assert "Pan2" in output
    assert "EnvGen" in output


def test_info_list_short_flag(capsys: pytest.CaptureFixture[str]) -> None:
    main(["info", "-l"])
    captured = capsys.readouterr()
    assert "UGens available" in captured.out


def test_info_list_count(capsys: pytest.CaptureFixture[str]) -> None:
    main(["info", "--list"])
    captured = capsys.readouterr()
    # Should have a substantial number of UGens
    first_line = captured.out.strip().split("\n")[0]
    count = int(first_line.split()[0])
    assert count > 300
