// sclang half of the compilation corpus (scripts/compile_corpus.py).
// Each case must mean the same as the Python case of the same name; every
// argument is passed explicitly so defaults do not enter the comparison.
// sclang binary operators have no precedence (strictly left to right), so
// every product inside a sum is parenthesized.
//
//   sclang -l sclang_conf.yaml scripts/compile_corpus.scd OUT_DIR/
(
var dir = thisProcess.argv[0] ?? { "./" };
var cases = [
	\arith -> {
		var s = SinOsc.ar(220, 0);
		Out.ar(0, [s * 0.5 + 0.1, (s - 0.2) / 2 * SinOsc.kr(3, 0)])
	},
	\unary -> {
		var s = SinOsc.ar(220, 0);
		Out.ar(0, [
			(s.abs * 0.3) + (s.neg * 0.2) + (s.squared * 0.1) + (s.cubed * 0.1),
			(s.abs.sqrt * 0.2) + ((s * 3).tanh * 0.2) + (s.distort * 0.2) + ((s * 2).softclip * 0.2)
				+ ((s + 2).reciprocal * 0.1) + (s.sign * 0.05)
		])
	},
	\binary -> {
		var s = SinOsc.ar(220, 0), t = SinOsc.ar(3.7, 0) * 0.8;
		Out.ar(0, [
			(s.min(t) * 0.2) + (s.max(t) * 0.2) + ((s.abs ** 1.5) * 0.2) + (s % 0.3)
				+ (s.round(0.25) * 0.2) + (s.trunc(0.25) * 0.1),
			(s.atan2(t) * 0.1) + (s.hypot(t) * 0.2) + (s.thresh(0.3) * 0.2) + (s.clip2(0.5) * 0.2)
				+ ((s * 2).fold2(0.7) * 0.2) + ((s * 2).wrap2(0.6) * 0.1) + (s.ring1(t) * 0.1)
				+ (s.amclip(t) * 0.1) + (s.scaleneg(0.5) * 0.1) + (s.absdif(t) * 0.1)
				+ (s.sqrsum(t) * 0.05) + (s.difsqr(t) * 0.05) + (s.excess(0.3) * 0.1)
		])
	},
	\compare -> {
		var s = SinOsc.ar(220, 0), t = SinOsc.ar(3.7, 0) * 0.8;
		Out.ar(0, [((s > t) * 0.2) + ((s < 0.1) * 0.2), ((s >= t) * 0.1) + ((s <= 0.0) * 0.1)])
	},
	\folding -> {
		var s = SinOsc.ar(2 * 110, 0), t = SinOsc.ar(3.7, 0);
		Out.ar(0, [(s * 1) + 0, (s * (2 + 3) * 0.1) + (s * 0) + (t * 0.1)])
	},
	\conversions -> {
		var f = (SinOsc.kr(1, 0) * 12 + 60).midicps;
		var a = (SinOsc.kr(2, 0) * -10 - 10).dbamp;
		Out.ar(0, [SinOsc.ar(f, 0) * 0.2, SinOsc.ar(330, 0) * a * -6.dbamp])
	},
	\multichannel -> {
		Out.ar(0, Mix.new(Pan2.ar(SinOsc.ar([220, 330], 0), [-0.5, 0.5], 0.3)))
	},
	\mix_sizes -> {
		Out.ar(0, [
			(Mix.new(SinOsc.ar([100, 200, 300], 0)) * 0.1) + (Mix.new(SinOsc.ar([110, 220, 330, 440], 0)) * 0.1),
			(Mix.new(SinOsc.ar((1..9) * 100, 0)) * 0.05) + (Mix.new(SinOsc.ar([150, 250, 350, 450, 550], 0)) * 0.05)
		])
	},
	\env_perc -> {
		Out.ar(0, EnvGen.ar(Env.perc(0.01, 0.1, 1, -4), 1, 1, 0, 1, 0) * SinOsc.ar(440, 0))
	},
	\env_adsr_release -> {
		var gate = Line.kr(1, -1, 0.2, doneAction: 0) > 0;
		Out.ar(0, EnvGen.ar(Env.adsr(0.01, 0.03, 0.5, 0.05, 1, -4, 0), gate, 1, 0, 1, 0) * SinOsc.ar(440, 0))
	},
	\env_curves -> {
		var e1 = Env([0, 1, 0.3, 0.8, 0], [0.03, 0.04, 0.05, 0.06], [\sin, \welch, -3, \step]);
		var e2 = Env([0.01, 1, 0.01], [0.05, 0.1], \exp);
		Out.ar(0, [EnvGen.ar(e1, 1, 1, 0, 1, 0), EnvGen.ar(e2, 1, 1, 0, 1, 0)])
	},
	\env_scaled -> {
		Out.ar(0, [
			EnvGen.ar(Env.linen(0.02, 0.05, 0.03, 0.8, \lin), 1, 0.5, 0.1, 1.5, 0),
			EnvGen.ar(Env.triangle(0.1, 0.9), 1, 1, 0, 0.5, 0)
		])
	},
	\controls -> { |freq = 330, amp = 0.25|
		Out.ar(0, SinOsc.ar(freq, 0) * amp)
	},
	\demand -> {
		var trig = Impulse.ar(100, 0);
		Out.ar(0, [
			Demand.ar(trig, 0, Dseq([0.1, 0.2, Dseq([0.3, 0.4], 2)], inf)),
			Demand.ar(trig, 0, Dseries(0, 0.01, inf))
		])
	},
	\duty_positive_control -> {
		Out.ar(0, Duty.ar(0.005, 0, Dseq([0.1, 0.2, 0.3], inf), 0))
	},
	\fft -> {
		var chain = FFT(LocalBuf(2048, 1), SinOsc.ar(440, 0) + SinOsc.ar(3000, 0), 0.5, 0, 1, 0);
		Out.ar(0, IFFT(PV_BrickWall(chain, 0.2), 0, 0) * 0.3)
	},
	\feedback -> {
		var sig = SinOsc.ar(220, 0) * 0.1 + (LocalIn.ar(1, 0) * 0.5);
		LocalOut.ar(sig);
		Out.ar(0, sig)
	},
	\delays -> {
		var imp = Impulse.ar(20, 0);
		Out.ar(0, [
			CombN.ar(imp, 0.05, 0.013, 0.2) + AllpassN.ar(imp, 0.05, 0.007, 0.1),
			DelayL.ar(SinOsc.ar(330, 0), 0.05, 0.0123)
		])
	},
	\filters -> {
		Out.ar(0, [
			RLPF.ar(Pulse.ar(110, 0.3), SinOsc.kr(2, 0) * 400 + 800, 0.3) * 0.3,
			(MoogFF.ar(LFSaw.ar(110, 0), 1200, 2, 0) * 0.3) + (BLowPass.ar(LFTri.ar(220, 0), 900, 0.7) * 0.3)
		])
	},
	\panners -> {
		var s = SinOsc.ar(300, 0), t = SinOsc.ar(450, 0);
		Out.ar(0, Pan2.ar(s, SinOsc.kr(1, 0), 0.5) + Balance2.ar(s, t, 0.3, 0.5)
			+ PanAz.ar(4, t, 0.2, 0.5, 2, 0.5).keep(2))
	},
	\select_clip -> {
		var s = SinOsc.ar(220, 0) * 2;
		Out.ar(0, [
			Select.ar(LFSaw.kr(2, 0) * 1.5 + 1.5, [SinOsc.ar(220, 0), LFTri.ar(330, 0), Pulse.ar(440, 0.5)]) * 0.3,
			(Clip.ar(s, -0.5, 0.5) * 0.3) + (Wrap.ar(s, -0.4, 0.4) * 0.3) + (Fold.ar(s, -0.6, 0.6) * 0.3)
		])
	},
	\triggers -> {
		var imp = Impulse.ar(10, 0);
		Out.ar(0, [
			(Trig1.ar(imp, 0.01) * 0.2) + (Latch.ar(SinOsc.ar(3, 0), Impulse.ar(50, 0)) * 0.2)
				+ (Phasor.ar(Impulse.ar(4, 0), 0.001, 0, 1, 0) * 0.2),
			(Sweep.ar(Impulse.ar(4, 0), 2) * 0.2) + (ToggleFF.ar(Impulse.ar(20, 0)) * 0.2)
				+ (Decay2.ar(Impulse.ar(8, 0), 0.001, 0.05) * 0.2)
				+ (Lag.ar(Pulse.ar(30, 0.5), 0.01) * 0.1) + (Ramp.ar(Pulse.ar(30, 0.5), 0.01) * 0.1)
		])
	},
	\rates -> {
		Out.ar(0, [K2A.ar(SinOsc.kr(5, 0)), K2A.ar(A2K.kr(SinOsc.ar(5, 0)))])
	},
	\seeded_noise -> {
		RandSeed.ir(1, 42);
		Out.ar(0, [WhiteNoise.ar * 0.1, LFNoise1.ar(500) * 0.1])
	},
	\linmap -> {
		var s = SinOsc.ar(2, 0);
		Out.ar(0, [SinOsc.ar(LinLin.ar(s, -1, 1, 200, 400), 0) * 0.2, SinOsc.ar(LinExp.ar(s, -1, 1, 200, 800), 0) * 0.2])
	},
	\klank -> {
		Out.ar(0, Klank.ar(`[[400, 800, 1200], [0.3, 0.2, 0.1], [0.2, 0.3, 0.4]], Impulse.ar(8, 0), 1, 0, 1))
	},
	\buses -> {
		Out.ar(10, SinOsc.ar(330, 0));
		Out.ar(0, In.ar(10, 1) * 0.5)
	},
	\lines -> {
		Out.ar(0, [Line.ar(0, 1, 0.2, doneAction: 0), XLine.ar(0.01, 1, 0.2, doneAction: 0)])
	}
];
cases.do { |assoc|
	try {
		var def = SynthDef(\corpus, assoc.value);
		File.use(dir ++ assoc.key ++ ".scsyndef", "wb", { |f| f.putAll(def.asBytes) });
		("WROTE " ++ assoc.key).postln;
	} { |err| ("FAILED " ++ assoc.key ++ " " ++ err.errorString).postln };
};
0.exit;
)
