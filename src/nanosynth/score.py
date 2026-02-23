"""Non-real-time (NRT) score rendering for offline audio synthesis."""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from .osc import OscBundle, OscMessage
from .scsynth import Options, find_ugen_plugins_path

if TYPE_CHECKING:
    from .synthdef import SynthDef


class Score:
    """A sequence of timestamped OSC bundles for offline (NRT) rendering.

    Build a score by adding OSC messages at specific timestamps, then call
    ``render()`` to produce an audio file without real-time audio hardware.

    Example::

        from nanosynth import Score, SynthDefBuilder, SinOsc, Out

        with SynthDefBuilder(freq=440.0) as b:
            Out.ar(bus=0, source=SinOsc.ar(frequency=b["freq"]) * 0.3)
        sd = b.build(name="sine")

        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, "sine", freq=440.0)
        score.add(1.0, OscMessage("/n_free", 1000))
        score.render("output.wav", sample_rate=44100)
    """

    def __init__(self) -> None:
        self._entries: list[tuple[float, list[OscMessage]]] = []

    def add(self, time: float, messages: list[OscMessage] | OscMessage) -> None:
        """Add OSC message(s) at the given time (seconds)."""
        if isinstance(messages, OscMessage):
            messages = [messages]
        self._entries.append((time, list(messages)))

    def add_synthdef(self, time: float, synthdef: SynthDef) -> None:
        """Add a /d_recv command for a SynthDef at the given time."""
        compiled = synthdef.compile()
        self._entries.append((time, [OscMessage("/d_recv", compiled)]))

    def add_synth(
        self,
        time: float,
        name: str,
        node_id: int = -1,
        add_action: int = 0,
        target: int = 0,
        **params: float,
    ) -> None:
        """Add a /s_new command at the given time."""
        args: list[int | float | str] = [name, node_id, add_action, target]
        for key, value in params.items():
            args.append(key)
            args.append(value)
        self._entries.append((time, [OscMessage("/s_new", *args)]))

    def sort(self) -> None:
        """Sort entries by time (in-place, stable)."""
        self._entries.sort(key=lambda e: e[0])

    def duration(self) -> float:
        """Return the timestamp of the last entry, or 0.0 if empty."""
        if not self._entries:
            return 0.0
        return max(t for t, _ in self._entries)

    def to_binary(self) -> bytes:
        """Serialize to SC's binary command file format.

        Format: repeated ``[int32 packet_size][OSC bundle datagram]``.
        The bundle timestamp is the raw time in seconds (no NTP epoch).
        """
        result = bytearray()
        for time, messages in self._entries:
            bundle = OscBundle(timestamp=time, contents=messages)
            datagram = bundle.to_datagram(realtime=False)
            result.extend(struct.pack(">i", len(datagram)))
            result.extend(datagram)
        return bytes(result)

    def render(
        self,
        output_path: str | Path,
        *,
        sample_rate: int = 44100,
        header_format: str = "WAV",
        sample_format: str = "int16",
        input_path: str | Path | None = None,
        output_channels: int = 2,
        input_channels: int = 0,
        options: Options | None = None,
    ) -> None:
        """Render this score to an audio file (non-real-time).

        Writes the binary command file to a temp file, then invokes
        the embedded scsynth NRT renderer.

        Args:
            output_path: Path for the output audio file.
            sample_rate: Output sample rate in Hz.
            header_format: Audio file format ("WAV" or "AIFF").
            sample_format: Sample encoding ("int16", "int24", "float").
            input_path: Optional input audio file for NRT processing.
            output_channels: Number of output channels.
            input_channels: Number of input channels.
            options: Optional Options for engine configuration overrides.
        """
        from . import _scsynth

        # Free all nodes before shutdown to prevent crashes from delay
        # UGens whose buffers are freed during World cleanup while still
        # referenced by running synths.
        entries = list(self._entries)
        end_time = max((t for t, _ in entries), default=0.0)
        entries.append((end_time, [OscMessage("/g_freeAll", 0)]))
        entries.append((end_time, [OscMessage("/c_set", 0, 0)]))

        # Build binary command data
        binary_data = bytearray()
        for time, messages in entries:
            bundle = OscBundle(timestamp=time, contents=messages)
            datagram = bundle.to_datagram(realtime=False)
            binary_data.extend(struct.pack(">i", len(datagram)))
            binary_data.extend(datagram)

        # Resolve options
        opts = options or Options()
        plugins_path = opts.ugen_plugins_path
        if plugins_path is None:
            found = find_ugen_plugins_path()
            if found is not None:
                plugins_path = str(found)

        # Write to a temp file and close it before calling the C++ renderer.
        # On Windows, NamedTemporaryFile with delete=True holds an exclusive
        # lock that prevents the engine from opening the file.
        cmd_fd, cmd_path = tempfile.mkstemp(suffix=".osc")
        try:
            with open(cmd_fd, "wb") as cmd_file:
                cmd_file.write(binary_data)

            _scsynth.world_nrt_render(
                cmd_filename=cmd_path,
                output_filename=str(output_path),
                sample_rate=sample_rate,
                input_filename=str(input_path) if input_path else None,
                header_format=header_format,
                sample_format=sample_format,
                num_output_bus_channels=output_channels,
                num_input_bus_channels=input_channels,
                block_size=opts.block_size,
                num_buffers=opts.buffer_count,
                max_nodes=opts.maximum_node_count,
                max_graph_defs=opts.maximum_synthdef_count,
                realtime_memory_size=opts.memory_size,
                preferred_hardware_buffer_size=8192,
                verbosity=opts.verbosity,
                ugen_plugins_path=plugins_path,
                num_audio_bus_channels=opts.audio_bus_channel_count,
                num_control_bus_channels=opts.control_bus_channel_count,
                max_wire_bufs=opts.wire_buffer_count,
                num_rgens=opts.random_number_generator_count,
            )
        finally:
            Path(cmd_path).unlink(missing_ok=True)
