"""Tests for the nanosynth CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from nanosynth.cli import main

SAMPLE_MODULE = """\
from nanosynth import synthdef
from nanosynth.ugens import Out, SinOsc, WhiteNoise


@synthdef()
def simple(freq=440, amp=0.1):
    Out.ar(bus=0, source=SinOsc.ar(frequency=freq) * amp)


@synthdef()
def noise(amp=0.1):
    Out.ar(bus=0, source=WhiteNoise.ar() * amp)
"""


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


# -- compile command -------------------------------------------------------


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    path = tmp_path / "defs.py"
    path.write_text(SAMPLE_MODULE)
    return path


def _valid_scgf(data: bytes) -> bool:
    return data[:4] == b"SCgf"


def test_compile_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["compile", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--bundle" in captured.out
    assert "--anonymous" in captured.out


def test_compile_per_def(
    sample_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    main(["compile", str(sample_file), "-o", str(out_dir)])

    simple = out_dir / "simple.scsyndef"
    noise = out_dir / "noise.scsyndef"
    assert simple.is_file()
    assert noise.is_file()
    assert _valid_scgf(simple.read_bytes())
    assert _valid_scgf(noise.read_bytes())

    captured = capsys.readouterr()
    assert "simple.scsyndef" in captured.out
    assert "noise.scsyndef" in captured.out


def test_compile_per_def_bytes_match_direct_compile(
    sample_file: Path, tmp_path: Path
) -> None:
    """A per-def file must equal SynthDef.compile() for that def."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    main(["compile", str(sample_file), "-o", str(out_dir), "--name", "simple"])

    module = _import_sample(sample_file)
    expected = module.simple.compile()
    assert (out_dir / "simple.scsyndef").read_bytes() == expected


def test_compile_bundle(
    sample_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = tmp_path / "all.scsyndef"
    main(["compile", str(sample_file), "-b", str(bundle)])

    from nanosynth import compile_synthdefs

    module = _import_sample(sample_file)
    expected = compile_synthdefs(module.simple, module.noise)
    assert bundle.read_bytes() == expected

    captured = capsys.readouterr()
    assert "2 SynthDef" in captured.out


def test_compile_name_filter(sample_file: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    main(["compile", str(sample_file), "-o", str(out_dir), "-n", "noise"])
    assert (out_dir / "noise.scsyndef").is_file()
    assert not (out_dir / "simple.scsyndef").exists()


def test_compile_anonymous(sample_file: Path, tmp_path: Path) -> None:
    bundle = tmp_path / "anon.scsyndef"
    main(["compile", str(sample_file), "-b", str(bundle), "--anonymous"])

    from nanosynth import compile_synthdefs

    module = _import_sample(sample_file)
    expected = compile_synthdefs(module.simple, module.noise, use_anonymous_names=True)
    assert bundle.read_bytes() == expected


def test_compile_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["compile", str(tmp_path / "nope.py")])
    assert exc_info.value.code == 1


def test_compile_not_python(tmp_path: Path) -> None:
    bad = tmp_path / "defs.txt"
    bad.write_text("not python")
    with pytest.raises(SystemExit) as exc_info:
        main(["compile", str(bad)])
    assert exc_info.value.code == 1


def test_compile_no_synthdefs(tmp_path: Path) -> None:
    empty = tmp_path / "empty.py"
    empty.write_text("x = 1\n")
    with pytest.raises(SystemExit) as exc_info:
        main(["compile", str(empty)])
    assert exc_info.value.code == 1


def test_compile_unknown_name(
    sample_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["compile", str(sample_file), "-n", "missing"])
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "not found" in captured.err


def test_compile_bad_output_dir(sample_file: Path, tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["compile", str(sample_file), "-o", str(tmp_path / "nonexistent")])
    assert exc_info.value.code == 1


def _import_sample(path: Path):  # type: ignore[no-untyped-def]
    from nanosynth.cli import _load_module_from_path

    return _load_module_from_path(path.resolve())
