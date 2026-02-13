"""Parametrized compilation tests for UGen category modules.

Each test builds a minimal SynthDef using the UGen and verifies it compiles
to valid SCgf output.
"""

import pytest

from nanosynth.synthdef import SynthDefBuilder
from nanosynth.ugens import (
    # beq
    BAllPass,
    BBandPass,
    BBandStop,
    BHiCut,
    BHiPass,
    BHiShelf,
    BLowCut,
    BLowPass,
    BLowShelf,
    BPeakEQ,
    # bufio
    BufRd,
    ClearBuf,
    PlayBuf,
    RecordBuf,
    CuspL,
    CuspN,
    FBSineC,
    FBSineL,
    FBSineN,
    GbmanL,
    GbmanN,
    HenonC,
    HenonL,
    HenonN,
    LatoocarfianC,
    LatoocarfianL,
    LatoocarfianN,
    LinCongC,
    LinCongL,
    LinCongN,
    LorenzL,
    QuadC,
    QuadL,
    QuadN,
    StandardL,
    StandardN,
    # convolution
    Convolution,
    Convolution2,
    AllpassC,
    AllpassL,
    AllpassN,
    CombC,
    CombL,
    CombN,
    DelTapRd,
    DelTapWr,
    Delay1,
    Delay2,
    DelayC,
    DelayL,
    DelayN,
    # demand
    Dbrown,
    Dgeom,
    Drand,
    Dseq,
    Dser,
    Dseries,
    Dshuf,
    Duty,
    Dwhite,
    Amplitude,
    Compander,
    Limiter,
    Normalizer,
    # envelopes
    Done,
    FreeSelf,
    Linen,
    Blip,
    FSinOsc,
    Pulse,
    Saw,
    # filters
    APF,
    BPF,
    BRF,
    Decay,
    Decay2,
    DetectSilence,
    FOS,
    Formlet,
    HPF,
    Integrator,
    LPF,
    Lag,
    Lag2,
    Lag3,
    LeakDC,
    Median,
    MoogFF,
    OnePole,
    OneZero,
    RHPF,
    RLPF,
    Ringz,
    SOS,
    Slew,
    Slope,
    TwoPole,
    TwoZero,
    # granular
    GrainBuf,
    GrainIn,
    PitchShift,
    Warp1,
    # info
    BlockSize,
    BufChannels,
    BufDur,
    BufFrames,
    BufRateScale,
    BufSampleRate,
    BufSamples,
    ControlDur,
    ControlRate,
    NodeID,
    NumAudioBuses,
    NumBuffers,
    NumControlBuses,
    NumInputBuses,
    NumOutputBuses,
    NumRunningSynths,
    RadiansPerSample,
    SampleDur,
    SampleRate,
    SubsampleOffset,
    # inout
    In,
    InFeedback,
    LocalOut,
    OffsetOut,
    Out,
    ReplaceOut,
    XOut,
    # lines
    A2K,
    AmpComp,
    AmpCompA,
    DC,
    K2A,
    LinExp,
    Line,
    XLine,
    # noise
    BrownNoise,
    ClipNoise,
    CoinGate,
    Crackle,
    Dust,
    Dust2,
    ExpRand,
    GrayNoise,
    Hasher,
    IRand,
    LFClipNoise,
    LFDClipNoise,
    LFDNoise0,
    LFDNoise1,
    LFDNoise3,
    LFNoise0,
    LFNoise1,
    LFNoise2,
    Logistic,
    PinkNoise,
    Rand,
    TRand,
    WhiteNoise,
    # osc
    Impulse,
    LFCub,
    LFGauss,
    LFPar,
    LFPulse,
    LFSaw,
    LFTri,
    Select,
    SinOsc,
    SyncSaw,
    VarSaw,
    Vibrato,
    Balance2,
    Pan2,
    Pan4,
    PanAz,
    PanB,
    PanB2,
    Rotate2,
    XFade2,
    # physical
    Ball,
    Pluck,
    Spring,
    TBall,
    # reverb
    FreeVerb,
    # safety
    CheckBadValues,
    Sanitize,
    # triggers
    Clip,
    Fold,
    Gate,
    Latch,
    Peak,
    Phasor,
    Schmidt,
    SendTrig,
    Sweep,
    TDelay,
    ToggleFF,
    Trig,
    Trig1,
    Wrap,
)


def _compile(build_fn, name="test"):
    """Helper: run build_fn inside a SynthDefBuilder, compile the result."""
    with SynthDefBuilder() as builder:
        build_fn(builder)
    sd = builder.build(name=name)
    data = sd.compile()
    assert data[:4] == b"SCgf"
    return data


# ---------------------------------------------------------------------------
# Oscillators (osc.py)
# ---------------------------------------------------------------------------


class TestOsc:
    def test_sinusc(self):
        _compile(lambda b: Out.ar(bus=0, source=SinOsc.ar()))

    def test_lfsaw(self):
        _compile(lambda b: Out.ar(bus=0, source=LFSaw.ar()))

    def test_lftri(self):
        _compile(lambda b: Out.ar(bus=0, source=LFTri.ar()))

    def test_lfpar(self):
        _compile(lambda b: Out.ar(bus=0, source=LFPar.ar()))

    def test_lfpulse(self):
        _compile(lambda b: Out.ar(bus=0, source=LFPulse.ar()))

    def test_lfcub(self):
        _compile(lambda b: Out.ar(bus=0, source=LFCub.ar()))

    def test_impulse(self):
        _compile(lambda b: Out.ar(bus=0, source=Impulse.ar()))

    def test_varsaw(self):
        _compile(lambda b: Out.ar(bus=0, source=VarSaw.ar()))

    def test_syncsow(self):
        _compile(lambda b: Out.ar(bus=0, source=SyncSaw.ar()))

    def test_select(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=Select.ar(selector=0, sources=[SinOsc.ar(), LFSaw.ar()]),
            )
        )

    def test_vibrato(self):
        _compile(lambda b: Out.ar(bus=0, source=Vibrato.ar()))

    def test_lfgauss(self):
        _compile(lambda b: Out.ar(bus=0, source=LFGauss.ar()))


# ---------------------------------------------------------------------------
# Band-limited oscillators (ffsinosc.py)
# ---------------------------------------------------------------------------


class TestFFSinOsc:
    def test_saw(self):
        _compile(lambda b: Out.ar(bus=0, source=Saw.ar()))

    def test_pulse(self):
        _compile(lambda b: Out.ar(bus=0, source=Pulse.ar()))

    def test_blip(self):
        _compile(lambda b: Out.ar(bus=0, source=Blip.ar()))

    def test_fsinosc(self):
        _compile(lambda b: Out.ar(bus=0, source=FSinOsc.ar()))


# ---------------------------------------------------------------------------
# Noise (noise.py)
# ---------------------------------------------------------------------------


class TestNoise:
    def test_whitenoise(self):
        _compile(lambda b: Out.ar(bus=0, source=WhiteNoise.ar()))

    def test_pinknoise(self):
        _compile(lambda b: Out.ar(bus=0, source=PinkNoise.ar()))

    def test_brownnoise(self):
        _compile(lambda b: Out.ar(bus=0, source=BrownNoise.ar()))

    def test_graynoise(self):
        _compile(lambda b: Out.ar(bus=0, source=GrayNoise.ar()))

    def test_clipnoise(self):
        _compile(lambda b: Out.ar(bus=0, source=ClipNoise.ar()))

    def test_crackle(self):
        _compile(lambda b: Out.ar(bus=0, source=Crackle.ar()))

    def test_dust(self):
        _compile(lambda b: Out.ar(bus=0, source=Dust.ar()))

    def test_dust2(self):
        _compile(lambda b: Out.ar(bus=0, source=Dust2.ar()))

    def test_lfnoise0(self):
        _compile(lambda b: Out.ar(bus=0, source=LFNoise0.ar()))

    def test_lfnoise1(self):
        _compile(lambda b: Out.ar(bus=0, source=LFNoise1.ar()))

    def test_lfnoise2(self):
        _compile(lambda b: Out.ar(bus=0, source=LFNoise2.ar()))

    def test_lfclipnoise(self):
        _compile(lambda b: Out.ar(bus=0, source=LFClipNoise.ar()))

    def test_lfdclipnoise(self):
        _compile(lambda b: Out.ar(bus=0, source=LFDClipNoise.ar()))

    def test_lfdnoise0(self):
        _compile(lambda b: Out.ar(bus=0, source=LFDNoise0.ar()))

    def test_lfdnoise1(self):
        _compile(lambda b: Out.ar(bus=0, source=LFDNoise1.ar()))

    def test_lfdnoise3(self):
        _compile(lambda b: Out.ar(bus=0, source=LFDNoise3.ar()))

    def test_rand(self):
        _compile(lambda b: Out.ar(bus=0, source=SinOsc.ar(frequency=Rand.ir())))

    def test_irand(self):
        _compile(lambda b: Out.ar(bus=0, source=SinOsc.ar(frequency=IRand.ir())))

    def test_exprand(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar(frequency=ExpRand.ir(minimum=200, maximum=800)),
            )
        )

    def test_coingate(self):
        _compile(
            lambda b: Out.ar(
                bus=0, source=CoinGate.ar(probability=0.5, trigger=Impulse.ar())
            )
        )

    def test_trand(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar(
                    frequency=TRand.kr(minimum=200, maximum=800, trigger=Impulse.kr())
                ),
            )
        )

    def test_hasher(self):
        _compile(lambda b: Out.ar(bus=0, source=Hasher.ar(source=SinOsc.ar())))

    def test_logistic(self):
        _compile(lambda b: Out.ar(bus=0, source=Logistic.ar()))


# ---------------------------------------------------------------------------
# Filters (filters.py)
# ---------------------------------------------------------------------------


class TestFilters:
    def test_lpf(self):
        _compile(lambda b: Out.ar(bus=0, source=LPF.ar(source=WhiteNoise.ar())))

    def test_hpf(self):
        _compile(lambda b: Out.ar(bus=0, source=HPF.ar(source=WhiteNoise.ar())))

    def test_bpf(self):
        _compile(lambda b: Out.ar(bus=0, source=BPF.ar(source=WhiteNoise.ar())))

    def test_brf(self):
        _compile(lambda b: Out.ar(bus=0, source=BRF.ar(source=WhiteNoise.ar())))

    def test_rlpf(self):
        _compile(lambda b: Out.ar(bus=0, source=RLPF.ar(source=WhiteNoise.ar())))

    def test_rhpf(self):
        _compile(lambda b: Out.ar(bus=0, source=RHPF.ar(source=WhiteNoise.ar())))

    def test_apf(self):
        _compile(lambda b: Out.ar(bus=0, source=APF.ar(source=WhiteNoise.ar())))

    def test_decay(self):
        _compile(lambda b: Out.ar(bus=0, source=Decay.ar(source=Impulse.ar())))

    def test_decay2(self):
        _compile(lambda b: Out.ar(bus=0, source=Decay2.ar(source=Impulse.ar())))

    def test_formlet(self):
        _compile(lambda b: Out.ar(bus=0, source=Formlet.ar(source=Impulse.ar())))

    def test_ringz(self):
        _compile(lambda b: Out.ar(bus=0, source=Ringz.ar(source=Impulse.ar())))

    def test_lag(self):
        _compile(
            lambda b: Out.ar(bus=0, source=SinOsc.ar() * Lag.kr(source=LFNoise0.kr()))
        )

    def test_lag2(self):
        _compile(
            lambda b: Out.ar(bus=0, source=SinOsc.ar() * Lag2.kr(source=LFNoise0.kr()))
        )

    def test_lag3(self):
        _compile(
            lambda b: Out.ar(bus=0, source=SinOsc.ar() * Lag3.kr(source=LFNoise0.kr()))
        )

    def test_leakdc(self):
        _compile(lambda b: Out.ar(bus=0, source=LeakDC.ar(source=WhiteNoise.ar())))

    def test_integrator(self):
        _compile(lambda b: Out.ar(bus=0, source=Integrator.ar(source=WhiteNoise.ar())))

    def test_median(self):
        _compile(lambda b: Out.ar(bus=0, source=Median.ar(source=WhiteNoise.ar())))

    def test_moogff(self):
        _compile(lambda b: Out.ar(bus=0, source=MoogFF.ar(source=WhiteNoise.ar())))

    def test_onepole(self):
        _compile(lambda b: Out.ar(bus=0, source=OnePole.ar(source=WhiteNoise.ar())))

    def test_onezero(self):
        _compile(lambda b: Out.ar(bus=0, source=OneZero.ar(source=WhiteNoise.ar())))

    def test_twopole(self):
        _compile(lambda b: Out.ar(bus=0, source=TwoPole.ar(source=WhiteNoise.ar())))

    def test_twozero(self):
        _compile(lambda b: Out.ar(bus=0, source=TwoZero.ar(source=WhiteNoise.ar())))

    def test_slew(self):
        _compile(lambda b: Out.ar(bus=0, source=Slew.ar(source=WhiteNoise.ar())))

    def test_slope(self):
        _compile(lambda b: Out.ar(bus=0, source=Slope.ar(source=SinOsc.ar())))

    def test_detectsilence(self):
        _compile(
            lambda b: (
                DetectSilence.ar(source=WhiteNoise.ar()),
                Out.ar(bus=0, source=WhiteNoise.ar()),
            )
        )

    def test_fos(self):
        _compile(lambda b: Out.ar(bus=0, source=FOS.ar(source=WhiteNoise.ar())))

    def test_sos(self):
        _compile(lambda b: Out.ar(bus=0, source=SOS.ar(source=WhiteNoise.ar())))


# ---------------------------------------------------------------------------
# Lines (lines.py)
# ---------------------------------------------------------------------------


class TestLines:
    def test_line(self):
        _compile(
            lambda b: Out.ar(bus=0, source=SinOsc.ar() * Line.kr(stop=0, duration=1))
        )

    def test_xline(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar() * XLine.kr(start=1, stop=0.001, duration=1),
            )
        )

    def test_dc(self):
        _compile(lambda b: Out.ar(bus=0, source=DC.ar(source=0.5)))

    def test_k2a(self):
        _compile(lambda b: Out.ar(bus=0, source=K2A.ar(source=DC.kr(source=0.5))))

    def test_a2k(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar(frequency=A2K.kr(source=SinOsc.ar()) * 200 + 400),
            )
        )

    def test_linexp(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar(
                    frequency=LinExp.kr(
                        source=SinOsc.kr(frequency=0.5),
                        input_minimum=-1,
                        input_maximum=1,
                        output_minimum=200,
                        output_maximum=800,
                    )
                ),
            )
        )

    def test_ampcomp(self):
        _compile(
            lambda b: Out.ar(bus=0, source=SinOsc.ar() * AmpComp.kr(frequency=440))
        )

    def test_ampcompa(self):
        _compile(
            lambda b: Out.ar(bus=0, source=SinOsc.ar() * AmpCompA.kr(frequency=440))
        )


# ---------------------------------------------------------------------------
# Delay (delay.py)
# ---------------------------------------------------------------------------


class TestDelay:
    def test_delay1(self):
        _compile(lambda b: Out.ar(bus=0, source=Delay1.ar(source=Impulse.ar())))

    def test_delay2(self):
        _compile(lambda b: Out.ar(bus=0, source=Delay2.ar(source=Impulse.ar())))

    def test_delayn(self):
        _compile(lambda b: Out.ar(bus=0, source=DelayN.ar(source=WhiteNoise.ar())))

    def test_delayl(self):
        _compile(lambda b: Out.ar(bus=0, source=DelayL.ar(source=WhiteNoise.ar())))

    def test_delayc(self):
        _compile(lambda b: Out.ar(bus=0, source=DelayC.ar(source=WhiteNoise.ar())))

    def test_combn(self):
        _compile(lambda b: Out.ar(bus=0, source=CombN.ar(source=WhiteNoise.ar())))

    def test_combl(self):
        _compile(lambda b: Out.ar(bus=0, source=CombL.ar(source=WhiteNoise.ar())))

    def test_combc(self):
        _compile(lambda b: Out.ar(bus=0, source=CombC.ar(source=WhiteNoise.ar())))

    def test_allpassn(self):
        _compile(lambda b: Out.ar(bus=0, source=AllpassN.ar(source=WhiteNoise.ar())))

    def test_allpassl(self):
        _compile(lambda b: Out.ar(bus=0, source=AllpassL.ar(source=WhiteNoise.ar())))

    def test_allpassc(self):
        _compile(lambda b: Out.ar(bus=0, source=AllpassC.ar(source=WhiteNoise.ar())))

    def test_deltapwr_deltaprd(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=DelTapRd.ar(
                    buffer_id=0,
                    phase=DelTapWr.ar(buffer_id=0, source=WhiteNoise.ar()),
                    delay_time=0.1,
                ),
            )
        )


# ---------------------------------------------------------------------------
# Triggers (triggers.py)
# ---------------------------------------------------------------------------


class TestTriggers:
    def test_trig(self):
        _compile(lambda b: Out.ar(bus=0, source=Trig.ar(source=Dust.ar())))

    def test_trig1(self):
        _compile(lambda b: Out.ar(bus=0, source=Trig1.ar(source=Dust.ar())))

    def test_latch(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar(
                    frequency=Latch.ar(source=WhiteNoise.ar(), trigger=Impulse.ar())
                    * 400
                    + 500
                ),
            )
        )

    def test_gate(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=Gate.ar(source=WhiteNoise.ar(), trigger=LFPulse.ar()),
            )
        )

    def test_toggleff(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar() * ToggleFF.ar(trigger=Dust.ar()),
            )
        )

    def test_sweep(self):
        _compile(lambda b: Out.ar(bus=0, source=Sweep.ar(trigger=0, rate=1)))

    def test_phasor(self):
        _compile(lambda b: Out.ar(bus=0, source=Phasor.ar()))

    def test_clip(self):
        _compile(lambda b: Out.ar(bus=0, source=Clip.ar(source=SinOsc.ar())))

    def test_fold(self):
        _compile(lambda b: Out.ar(bus=0, source=Fold.ar(source=SinOsc.ar())))

    def test_wrap(self):
        _compile(lambda b: Out.ar(bus=0, source=Wrap.ar(source=SinOsc.ar())))

    def test_schmidt(self):
        _compile(
            lambda b: Out.ar(
                bus=0, source=Schmidt.ar(source=SinOsc.ar(), minimum=-0.5, maximum=0.5)
            )
        )

    def test_peak(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=Peak.ar(source=SinOsc.ar(), trigger=Impulse.kr()),
            )
        )

    def test_sendtrig(self):
        _compile(
            lambda b: (
                SendTrig.kr(trigger=Impulse.kr(), id_=0, value=0),
                Out.ar(bus=0, source=SinOsc.ar()),
            )
        )

    def test_tdelay(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar() * TDelay.ar(source=Impulse.ar(), duration=0.1),
            )
        )


# ---------------------------------------------------------------------------
# Dynamics (dynamics.py)
# ---------------------------------------------------------------------------


class TestDynamics:
    def test_amplitude(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar() * Amplitude.kr(source=SinOsc.ar()),
            )
        )

    def test_compander(self):
        def build(b):
            sig = WhiteNoise.ar()
            Out.ar(bus=0, source=Compander.ar(source=sig, control=sig))

        _compile(build)

    def test_limiter(self):
        _compile(lambda b: Out.ar(bus=0, source=Limiter.ar(source=WhiteNoise.ar())))

    def test_normalizer(self):
        _compile(lambda b: Out.ar(bus=0, source=Normalizer.ar(source=WhiteNoise.ar())))


# ---------------------------------------------------------------------------
# Info (info.py)
# ---------------------------------------------------------------------------


class TestInfo:
    @pytest.mark.parametrize(
        "ugen_cls",
        [
            SampleRate,
            SampleDur,
            ControlRate,
            ControlDur,
            BlockSize,
            RadiansPerSample,
            SubsampleOffset,
            NumOutputBuses,
            NumInputBuses,
            NumAudioBuses,
            NumControlBuses,
            NumBuffers,
            NumRunningSynths,
            NodeID,
        ],
    )
    def test_info_ugen(self, ugen_cls):
        _compile(
            lambda b: Out.ar(bus=0, source=SinOsc.ar(frequency=ugen_cls.ir() + 440))
        )

    @pytest.mark.parametrize(
        "ugen_cls",
        [BufSampleRate, BufRateScale, BufFrames, BufSamples, BufDur, BufChannels],
    )
    def test_buf_info_ugen(self, ugen_cls):
        _compile(
            lambda b: Out.ar(
                bus=0, source=SinOsc.ar(frequency=ugen_cls.ir(buffer_id=0) + 440)
            )
        )


# ---------------------------------------------------------------------------
# Panning (panning.py)
# ---------------------------------------------------------------------------


class TestPanning:
    def test_pan2(self):
        _compile(lambda b: Out.ar(bus=0, source=Pan2.ar(source=SinOsc.ar())))

    def test_pan4(self):
        _compile(lambda b: Out.ar(bus=0, source=Pan4.ar(source=SinOsc.ar())))

    def test_panaz(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=PanAz.ar(source=SinOsc.ar(), channel_count=4),
            )
        )

    def test_panb(self):
        _compile(lambda b: Out.ar(bus=0, source=PanB.ar(source=SinOsc.ar())))

    def test_panb2(self):
        _compile(lambda b: Out.ar(bus=0, source=PanB2.ar(source=SinOsc.ar())))

    def test_balance2(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=Balance2.ar(left=SinOsc.ar(), right=SinOsc.ar(frequency=443)),
            )
        )

    def test_rotate2(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=Rotate2.ar(x=SinOsc.ar(), y=SinOsc.ar(frequency=443)),
            )
        )

    def test_xfade2(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=XFade2.ar(in_a=SinOsc.ar(), in_b=WhiteNoise.ar()),
            )
        )


# ---------------------------------------------------------------------------
# IO (inout.py)
# ---------------------------------------------------------------------------


class TestInOut:
    def test_in_ar(self):
        _compile(lambda b: Out.ar(bus=0, source=In.ar(bus=8, channel_count=2)))

    def test_infeedback(self):
        _compile(lambda b: Out.ar(bus=0, source=InFeedback.ar(bus=0, channel_count=1)))

    def test_replaceout(self):
        _compile(lambda b: ReplaceOut.ar(bus=0, source=SinOsc.ar()))

    def test_offsetout(self):
        _compile(lambda b: OffsetOut.ar(bus=0, source=SinOsc.ar()))

    def test_xout(self):
        _compile(lambda b: XOut.ar(bus=0, crossfade=0.5, source=SinOsc.ar()))

    def test_localout(self):
        _compile(
            lambda b: (
                LocalOut.ar(source=[SinOsc.ar()]),
                Out.ar(bus=0, source=SinOsc.ar()),
            )
        )


# ---------------------------------------------------------------------------
# Chaos (chaos.py)
# ---------------------------------------------------------------------------


class TestChaos:
    @pytest.mark.parametrize(
        "ugen_cls",
        [
            CuspL,
            CuspN,
            FBSineC,
            FBSineL,
            FBSineN,
            GbmanL,
            GbmanN,
            HenonC,
            HenonL,
            HenonN,
            LatoocarfianC,
            LatoocarfianL,
            LatoocarfianN,
            LinCongC,
            LinCongL,
            LinCongN,
            LorenzL,
            QuadC,
            QuadL,
            QuadN,
            StandardL,
            StandardN,
        ],
    )
    def test_chaos_compiles(self, ugen_cls):
        _compile(lambda b: Out.ar(bus=0, source=ugen_cls.ar()))


# ---------------------------------------------------------------------------
# Physical (physical.py)
# ---------------------------------------------------------------------------


class TestPhysical:
    def test_pluck(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=Pluck.ar(
                    source=WhiteNoise.ar(),
                    trigger=Impulse.ar(frequency=2),
                ),
            )
        )

    def test_ball(self):
        _compile(lambda b: Out.ar(bus=0, source=Ball.ar(source=SinOsc.ar())))

    def test_spring(self):
        _compile(lambda b: Out.ar(bus=0, source=Spring.ar(source=SinOsc.ar())))

    def test_tball(self):
        _compile(lambda b: Out.ar(bus=0, source=TBall.ar(source=SinOsc.ar())))


# ---------------------------------------------------------------------------
# BEQ (beq.py)
# ---------------------------------------------------------------------------


class TestBEQ:
    @pytest.mark.parametrize(
        "ugen_cls",
        [
            BAllPass,
            BBandPass,
            BBandStop,
            BHiCut,
            BHiPass,
            BHiShelf,
            BLowCut,
            BLowPass,
            BLowShelf,
            BPeakEQ,
        ],
    )
    def test_beq_compiles(self, ugen_cls):
        _compile(lambda b: Out.ar(bus=0, source=ugen_cls.ar(source=WhiteNoise.ar())))


# ---------------------------------------------------------------------------
# Convolution (convolution.py)
# ---------------------------------------------------------------------------


class TestConvolution:
    def test_convolution(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=Convolution.ar(source=SinOsc.ar(), kernel=WhiteNoise.ar()),
            )
        )

    def test_convolution2(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=Convolution2.ar(
                    source=SinOsc.ar(),
                    kernel=0,
                    trigger=0,
                ),
            )
        )


# ---------------------------------------------------------------------------
# Safety (safety.py)
# ---------------------------------------------------------------------------


class TestSafety:
    def test_checkbadvalues(self):
        _compile(
            lambda b: (
                CheckBadValues.ar(source=SinOsc.ar()),
                Out.ar(bus=0, source=SinOsc.ar()),
            )
        )

    def test_sanitize(self):
        _compile(lambda b: Out.ar(bus=0, source=Sanitize.ar(source=SinOsc.ar())))


# ---------------------------------------------------------------------------
# Reverb (reverb.py)
# ---------------------------------------------------------------------------


class TestReverb:
    def test_freeverb(self):
        _compile(lambda b: Out.ar(bus=0, source=FreeVerb.ar(source=WhiteNoise.ar())))


# ---------------------------------------------------------------------------
# Granular (granular.py)
# ---------------------------------------------------------------------------


class TestGranular:
    def test_pitchshift(self):
        _compile(lambda b: Out.ar(bus=0, source=PitchShift.ar(source=SinOsc.ar())))

    def test_grainbuf(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=GrainBuf.ar(
                    trigger=Impulse.kr(frequency=10),
                    buffer_id=0,
                    channel_count=1,
                ),
            )
        )

    def test_grainin(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=GrainIn.ar(
                    trigger=Impulse.kr(frequency=10),
                    source=SinOsc.ar(),
                    channel_count=1,
                ),
            )
        )

    def test_warp1(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=Warp1.ar(buffer_id=0, channel_count=1),
            )
        )


# ---------------------------------------------------------------------------
# Envelopes (envelopes.py in ugens/)
# ---------------------------------------------------------------------------


class TestUGenEnvelopes:
    def test_done(self):
        _compile(
            lambda b: (
                FreeSelf.kr(trigger=Done.kr(source=Line.kr())),
                Out.ar(bus=0, source=SinOsc.ar()),
            )
        )

    def test_linen(self):
        _compile(lambda b: Out.ar(bus=0, source=SinOsc.ar() * Linen.kr()))

    def test_freeself(self):
        _compile(
            lambda b: (
                FreeSelf.kr(trigger=Impulse.kr(frequency=0)),
                Out.ar(bus=0, source=SinOsc.ar()),
            )
        )


# ---------------------------------------------------------------------------
# Demand (demand.py)
# ---------------------------------------------------------------------------


class TestDemand:
    def test_duty_dseq(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar(
                    frequency=Duty.kr(
                        duration=0.5, level=Dseq.dr(repeats=1, sequence=[440, 550, 660])
                    )
                ),
            )
        )

    def test_dser(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar(
                    frequency=Duty.kr(
                        duration=0.2, level=Dser.dr(repeats=5, sequence=[440, 550])
                    )
                ),
            )
        )

    def test_drand(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar(
                    frequency=Duty.kr(
                        duration=0.2,
                        level=Drand.dr(repeats=5, sequence=[440, 550, 660]),
                    )
                ),
            )
        )

    def test_dseries(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar(frequency=Duty.kr(duration=0.1, level=Dseries.dr())),
            )
        )

    def test_dgeom(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar(frequency=Duty.kr(duration=0.1, level=Dgeom.dr())),
            )
        )

    def test_dbrown(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar(frequency=Duty.kr(duration=0.1, level=Dbrown.dr())),
            )
        )

    def test_dwhite(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar(frequency=Duty.kr(duration=0.1, level=Dwhite.dr())),
            )
        )

    def test_dshuf(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=SinOsc.ar(
                    frequency=Duty.kr(
                        duration=0.2,
                        level=Dshuf.dr(repeats=1, sequence=[440, 550, 660]),
                    )
                ),
            )
        )


# ---------------------------------------------------------------------------
# BufIO (bufio.py)
# ---------------------------------------------------------------------------


class TestBufIO:
    def test_playbuf(self):
        _compile(
            lambda b: Out.ar(bus=0, source=PlayBuf.ar(buffer_id=0, channel_count=1))
        )

    def test_bufrd(self):
        _compile(
            lambda b: Out.ar(
                bus=0,
                source=BufRd.ar(buffer_id=0, phase=Phasor.ar(), channel_count=1),
            )
        )

    def test_recordbuf(self):
        _compile(
            lambda b: (
                RecordBuf.ar(buffer_id=0, source=SinOsc.ar()),
                Out.ar(bus=0, source=SinOsc.ar()),
            )
        )

    def test_clearbuf(self):
        _compile(
            lambda b: (
                ClearBuf.ir(buffer_id=0),
                Out.ar(bus=0, source=SinOsc.ar()),
            )
        )
