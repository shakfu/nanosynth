# Dirt parameter mapping

Maps each classic Dirt `/dirt/play` field to nanosynth UGens, as the spec for a native `/dirt/play` receiver. Assessed 2026-10-14 against [codeberg.org/uzu/dirt](https://codeberg.org/uzu/dirt) at `123b399` (2026-06-21). File and function names below refer to that repo.

Superseded as the reference (2026-10-15). The target users (Tidal, Strudel, vortex) write for SuperDirt, whose levels, filters, interpolation and effects differ from Dirt's. The reference is now nanodirt `docs/dev/superdirt-parameter-mapping.md`. This document remains the record of classic Dirt's behaviour.

## Fields with no effect in Dirt

`dirt.h` (`DIRT_FIELDS`) declares 32 fields. Four do not change the sound:

- `offset`, `velocity`, `kriole`: stored in `play_dispatch` (`libdirt.c`), never read by `audio.c`.

- `orbit`: used only for RMS metering, compiled out by default (`SEND_RMS`). Dirt has no per-orbit effects; the delay is one global line.

## Per-sound chain

Order, from `playback_effects` (`audio.c`):

source -> vowel -> lpf -> hpf -> bpf or notch -> coarse -> shape -> crush -> envelope -> 16-sample fades -> pan -> out, plus delay send.

SuperDirt uses a different order. Dirt parity requires this one.

## Mapping

Abbreviations: F = sample frames, SR = engine sample rate, R = `CUTOFFRATIO` = 30000.

| Field | Dirt behaviour | nanosynth mapping | Parity |
|-|-|-|-|
| `s`, `n` | `s` is a folder under the sample root. Its `.wav` files are sorted (`alphasort`); file `abs(floor(n)) % count` plays. A name with a path component is used as given. Loading is lazy, so the first hit plays late. | Resolve in Python and preload with `read_buffer`. Select the SynthDef by sample channel count (1 or 2), since `BufRd` fixes its channel count at build time. | exact |
| `speed` | 0 drops the event. Negative plays the segment backwards. | `Phasor.ar(0, rate * BufRateScale.kr(b), start, end)` into `BufRd.ar(..., interpolation=2)` (linear, as in Dirt). Reverse: negative rate, starting at `end`. | exact |
| `accelerate` | Per sample, `speed += accelerate/SR`, applied to `abs(speed)`. | `rate = dir * (abs(speed) + accelerate * Sweep.ar(0, 1))`. | exact |
| `unit` | `r`: plain rate. `s`: rate = F/speed/SR, so the sample lasts `speed` seconds. `c`: rate = F*speed*cps/SR. `accelerate` is rescaled the same way. | Convert in Python before `/s_new`. `cps` is used only here. | exact |
| `begin`, `end` | Fractions of the sample. Reverse swaps them to `1-end`, `1-begin`. `end` applies only when 0 < `end` < 1. `begin < 0` means "continue from where the cut sound left off". | Compute start and end frames in Python. For `begin < 0`, Python can compute the cut sound's position from its start time, rate and accel. Deferred. | exact, except `begin < 0` |
| `loop` | Total play count. At segment end, position resets to `start`. | `Phasor` wraps by itself. Python computes total duration from `loop`, segment length and rate (closed form; quadratic when accelerating). | exact |
| `gain` | Level = `(gain/2)^4`. `gain=1` gives 0.0625. | Same formula, as a multiplier. | exact |
| `pan` | Sample channel `i` goes to `c = i + pan`, equal-power between output channels `floor(c)` and `floor(c)+1`, wrapping. With more than 2 outputs, `pan` is first multiplied by the channel count (`-DSCALEPAN` in the Makefile). A stereo sample at `pan=0.5` on 2 outputs plays straight through. | `PanAz.ar(N, ch_i, pos=2*(i+pan)/N, width=2, orientation=0)` for every N, including 2. The wrap matters for stereo samples, so `Pan2` is only right for mono samples. | exact if the `PanAz` convention matches (unverified) |
| `vowel` | `a/e/i/o/u` select a 10-pole all-pole IIR with fixed coefficients (`formant_filter`). A deliberate bug shares one filter state across all channels. | Factor each polynomial offline into 5 `SOS` stages: `a0 = c0` on the first, `b1 = 2*Re(p)`, `b2 = -abs(p)^2`. For `a`: max pole radius 0.9942 (stable), formants 793, 1156, 2899, 3900, 4950 Hz at 44.1k. Coefficients do not scale with SR, in Dirt or here. | exact for mono. Stereo differs: the shared state is not reproduced |
| `cutoff`, `resonance` | 4-pole ladder (musicdsp style) with cubic soft saturation (`effect_vcf`). Active only if 0 < `resonance` < 1 and `cutoff` < R*SR/44100. `cutoff` alone, with `resonance = 0`, does nothing. | `MoogFF.ar(sig, freq, gain=4*resonance)`. Measured -3 dB corner over `cutoff`: 0.82 at 500 Hz, 0.86 at 1 kHz, 1.13 at 4 kHz. `freq = cutoff` is within about 15%; a fitted curve would do better. | approximate (different ladder model) |
| `hcutoff`, `hresonance` | The same ladder, output as `in - lowpass` (`effect_hpf`). Same activation rule. | `sig - MoogFF.ar(...)`. | approximate |
| `bandf`, `bandq` | 2-pole resonator (`effect_bpf`). Requires `bandq > 0`. Negative `bandf` gives a notch (`in - bpf`). | `BPF.ar(sig, 0.234*abs(bandf), rq=1/bandq)`, or `sig - BPF` for the notch. Measured: centre 0.232 x `bandf` (theory 44100/(R*2*pi) = 0.2340), unity peak gain, effective Q = `bandq` (1.01 and 4.1 measured). | close |
| `coarse` | n > 0: sample-and-hold every n samples. n < 0: mean of each n-sample block, held. | n > 0: `Latch.ar(sig, Impulse.ar(SampleRate.ir/n))`. n < 0: `Latch.ar(RunningSum.ar(sig, abs(n))/abs(n), same trigger)`. | close (trigger phase may differ by one sample) |
| `shape` | `k = 2s/(1-s)`, `s = min(abs(shape), 0.99)`; `y = (1+k)*x/(1+k*abs(x))`. | Arithmetic on the signal; compute `k` in Python. | exact |
| `crush` | Positive: `r = 2^(bits-1)`, `y = trunc(r*x)/r`, rounding toward zero. Negative: the same on `abs(x)^0.125`, then raised to the 8th power, sign restored. | `x.sign() * (abs(x) * r).floor_() / r`. Not SC's `trunc` binary op, which floors toward minus infinity. `Decimator` is sc3-plugins; avoid. | exact |
| `attack`, `hold`, `release` | Active only if `attack >= 0` and `release >= 0` (default -1, off). Attack `1.0524*(1-e^(-3t/a))`, release `1.0524*e^(-3t/r) - 0.0524`. The sound keeps running at zero level until the sample ends. | `Envelope([0,1,1,0], [a,h,r], curves=-3)`. SC's curve formula at c=-3 reduces to exactly Dirt's expressions. Free at the earlier of envelope end and sample end. | exact |
| (none) | 16-sample linear fade at segment start and end (`ROUNDOFF`, `effect_roundoff`). | Fold into the free envelope: 16/SR fade in and out. | exact |
| `cut` | On start, playing sounds in the same group get a 16-sample fade-out. Negative `cut` restricts this to the same sample (`cut`). | One `Group` per positive `cut` value, or per (cut, sample) for negative values. In one bundle, send `/n_set <group> gate 0` before `/s_new` into that group: scsynth sets the group's children, and the new node does not exist yet. A gated 16-sample release frees each node. No node tracking needed. | exact |
| `delay` | Post-pan send level, clamped to at most 1. | Extra `Out.ar(delay_bus, sig*delay)` in SynthDef variants that use delay. | exact |
| `delaytime`, `delayfeedback` | Global and sticky: the last event that sets them wins. Time is a fraction of a 44100-sample line, so `delaytime*44100/SR` seconds. Feedback clamped to +/-0.9999. Dirt updates these at receive time (`init_sound`), not play time. | One global FX synth: `CombN(x, 44100/SR, D, sign(fb)*D*ln(0.001)/ln(abs(fb)))`, which gives `y = x(t-D) + fb*y(t-D)`, Dirt's recurrence. Update with timestamped `/n_set`. | exact, except the receive-time update (a quirk; not worth copying) |
| `orbit`, `velocity`, `offset`, `kriole` | No effect. | Ignore. | exact |

## Master stage

From `playback_finalize`:

- **Delay return**: added to the dry mix before compression.

- **`dirty` compressor (default)**: peak gain rider. Gain drops instantly to `1/abs(peak)` and recovers linearly at 50/s. Output then scales by `g_gain/5`. No core UGen matches it per sample; a `LocalIn` loop adds a block of delay. `Normalizer` is nearest but uses lookahead. Approximate.

- **`clean`**: RMS follower plus `tanh`. Map to `Amplitude` or an RMS follower, gain, then `.tanh`. Approximate.

- **`none`**: multiply by `g_gain`. Exact.

- **NaN and Inf guard** (`playback_sanitize`): `Sanitize` plus a clamp.

## SynthDef strategy

Cached variants over one monolithic SynthDef. A monolithic SynthDef with bypass flags makes every voice compute every effect, at up to 128 voices (`DEFAULT_POLYPHONY`).

The variant key is the event's active set: `(nch, vowel, lpf, hpf, bpf|notch, coarse+/-, shape, crush+/-, env, delay)`. Build each variant on first use and cache it; only realized combinations are built. To avoid first-use latency, pre-build common variants, or send `/d_recv` with the `/s_new` as its completion message.

SuperDirt instead chains one synth per effect on a private bus. That needs no codegen but uses more nodes per event.

## Timing

Forward each incoming bundle timetag unchanged into the bundle sent to scsynth. Dirt schedules from the same timetag (`dirt_play_handler`, `server.c`).

## Open points

- `PanAz` orientation and position convention, against Dirt's channel layout.

- Ladder filter frequency: measured at `resonance` 0.01 with a 1e-3 impulse. At high resonance, or with the cubic saturation driven, the two models diverge further.

- Compressor parity is approximate only.

- `begin < 0` (cut-continue) is deferred.

## Method

Filter figures come from a numpy port of `effect_vcf`, `effect_bpf` and the vowel coefficients at SR = 44100. The port takes the FFT of a 1e-3 impulse response (2^15 points) and reads the -3 dB points. For the vowel filter it takes the roots of the denominator polynomial. No nanosynth code was run.

```python
import numpy as np
SR=44100.0; R=30000.0; N=1<<15
def vcf(x, cutoff, res):
    f=2*cutoff/R*44100/SR; k=3.6*f-1.6*f*f-1; p=(k+1)*.5; sc=np.exp((1-p)*1.386249); r=res*sc
    y1=y2=y3=y4=ox=o1=o2=o3=0.0; out=np.zeros_like(x)
    for i,v in enumerate(x):
        xx=v-r*y4; xp,y1p,y2p,y3p=xx*p,y1*p,y2*p,y3*p
        y1=xp+ox-k*y1; y2=y1p+o1-k*y2; y3=y2p+o2-k*y3; y4=y3p+o3-k*y4
        y4=y4-y4**3/6; ox,o1,o2,o3=xp,y1p,y2p,y3p; out[i]=y4
    return out
def bpf(x, bandf, q):
    f=abs(bandf/R*44100/SR); k=f/q; p=2-f*f; sc=1/(1+k)
    y1=y2=ox=0.0; out=np.zeros_like(x)
    for i,v in enumerate(x):
        y3=sc*(p*y2-y1+k*(v-ox+y2)); ox=v; y1=y2; y2=y3; out[i]=y3
    return out
imp=np.zeros(N); imp[0]=1e-3   # small: keeps the cubic saturation linear
fr=np.fft.rfftfreq(N,1/SR)
for c in (500,1000,4000):
    H=np.abs(np.fft.rfft(vcf(imp,c,0.01)))/1e-3; H/=H[1]
    print(f"vcf cutoff={c}: -3dB at {fr[np.argmax(H<0.7071)]:.0f} Hz")
for c,q in ((1000,1),(1000,4),(4000,4)):
    H=np.abs(np.fft.rfft(bpf(imp,c,q)))/1e-3; i=np.argmax(H)
    m=H>H[i]/np.sqrt(2); lo,hi=fr[m][0],fr[m][-1]
    print(f"bpf bandf={c} q={q}: peak {fr[i]:.0f} Hz, gain {H[i]:.3f}, Q_eff {fr[i]/(hi-lo):.2f}")
c=[3.11044e-06,8.943665402,-36.83889529,92.01697887,-154.337906,181.6233289,
   -151.8651235,89.09614114,-35.10298511,8.388101016,-0.923313471]  # vowel 'a'
poles=np.roots(np.r_[1,-np.array(c[1:])])
print("max |pole|", np.abs(poles).max())
print("formants Hz", np.sort(np.angle(poles[poles.imag>=0])*SR/2/np.pi))
```
