# UGens

340+ UGen classes organized by category. Each UGen is declared with the `@ugen` decorator and supports one or more calculation rates (`.ar`, `.kr`, `.ir`, `.dr`).

| Category | Module | Description |
|---|---|---|
| [Oscillators](osc.md) | `ugens.osc` | `SinOsc`, `Saw`, `Pulse`, `Blip`, `LFSaw`, `LFPulse`, `VarSaw`, `Impulse`, etc. |
| [Filters](filters.md) | `ugens.filters` | `LPF`, `HPF`, `BPF`, `RLPF`, `MoogFF`, `Lag`, `Ringz`, `Median`, `LeakDC`, etc. |
| [BEQ Filters](beq.md) | `ugens.beq` | `BLowPass`, `BHiPass`, `BBandPass`, `BPeakEQ`, `BLowShelf`, `BHiShelf`, etc. |
| [Noise & Random](noise.md) | `ugens.noise` | `WhiteNoise`, `PinkNoise`, `Dust`, `LFNoise0/1/2`, `Rand`, `TRand`, etc. |
| [Delays](delay.md) | `ugens.delay` | `DelayN/L/C`, `CombN/L/C`, `AllpassN/L/C`, `BufDelayN/L/C`, etc. |
| [Envelopes](envelopes.md) | `ugens.envelopes` | `EnvGen`, `Linen`, `Done`, `Free`, `FreeSelf`, etc. |
| [Panning](panning.md) | `ugens.panning` | `Pan2`, `Pan4`, `PanAz`, `Balance2`, `Splay`, `XFade2`, etc. |
| [Demand](demand.md) | `ugens.demand` | `Dseq`, `Drand`, `Dseries`, `Demand`, `Duty`, `DemandEnvGen`, etc. |
| [Dynamics](dynamics.md) | `ugens.dynamics` | `Compander`, `Limiter`, `Normalizer`, `Amplitude` |
| [Chaos](chaos.md) | `ugens.chaos` | `LorenzL`, `HenonN/L/C`, `GbmanN/L`, `LatoocarfianN/L/C`, etc. |
| [Granular](granular.md) | `ugens.granular` | `GrainBuf`, `GrainIn`, `PitchShift`, `Warp1` |
| [Buffer I/O](bufio.md) | `ugens.bufio` | `PlayBuf`, `RecordBuf`, `BufRd`, `BufWr`, `LocalBuf`, etc. |
| [Disk I/O](diskio.md) | `ugens.diskio` | `DiskIn`, `DiskOut`, `VDiskIn` |
| [Physical Modeling](physical.md) | `ugens.physical` | `Pluck`, `Ball`, `TBall`, `Spring` |
| [Reverb](reverb.md) | `ugens.reverb` | `FreeVerb` |
| [Convolution](convolution.md) | `ugens.convolution` | `Convolution`, `Convolution2`, `Convolution2L`, `Convolution3` |
| [Phase Vocoder](pv.md) | `ugens.pv` | `FFT`, `IFFT`, `PV_BrickWall`, `PV_MagFreeze`, `PV_BinShift`, etc. |
| [Machine Listening](ml.md) | `ugens.ml` | `BeatTrack`, `Loudness`, `MFCC`, `Onsets`, `Pitch`, etc. |
| [Stochastic](gendyn.md) | `ugens.gendyn` | `Gendy1`, `Gendy2`, `Gendy3` |
| [Hilbert](hilbert.md) | `ugens.hilbert` | `FreqShift`, `Hilbert`, `HilbertFIR` |
| [I/O](inout.md) | `ugens.inout` | `In`, `Out`, `InFeedback`, `LocalIn`, `LocalOut`, `ReplaceOut`, `XOut` |
| [Lines](lines.md) | `ugens.lines` | `Line`, `XLine`, `LinExp`, `LinLin`, `DC`, `K2A`, `A2K`, etc. |
| [Triggers](triggers.md) | `ugens.triggers` | `Trig`, `Latch`, `Gate`, `Sweep`, `Phasor`, `Poll`, `SendReply`, etc. |
| [Mouse/Keyboard](mac.md) | `ugens.mac` | `KeyState`, `MouseButton`, `MouseX`, `MouseY` |
| [Info](info.md) | `ugens.info` | `SampleRate`, `BlockSize`, `ControlRate`, `BufFrames`, `BufDur`, etc. |
| [Utility](basic.md) | `ugens.basic` | `MulAdd`, `Sum3`, `Sum4`, `Mix` |
| [Safety](safety.md) | `ugens.safety` | `CheckBadValues`, `Sanitize` |
| [Band-limited](ffsinosc.md) | `ugens.ffsinosc` | `FSinOsc`, `Klank`, `LFGauss`, `Osc`, `OscN`, `COsc`, `VOsc`, `VOsc3` |
