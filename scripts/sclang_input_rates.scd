// Record which input rates sclang's checkInputs accepts, per UGen, rate and input slot.
// Run via scripts/sclang_input_rates.py.
//
// Each class is built as in sclang_reference.scd. Its inputs are then replaced
// in place: every slot gets a signal at the UGen's own rate (the baseline), and
// one slot at a time gets an audio, control or scalar signal. A baseline that
// fails at the UGen's own rate is retried with every slot at audio rate. A rate is allowed
// in a slot if checkInputs returns nil.
(
var outPath = thisProcess.argv[0];
var rateMethods = [\ar, \kr, \ir];
var skip = [\mul, \add];
var overrides = (
	numChannels: 1, numChans: 2, envelope: Env([0, 1, 0], [1, 1]),
	specificationsArrayRef: `[[100], [1], [1]], weights: [0.5, 0.5],
	label: "x", rect: Rect(0, 0, 1, 1)
);
var probes = [\audio, \control, \scalar];
var entries = Dictionary.new;
var str = { |s| "\"" ++ s.asString.replace("\\", "\\\\").replace("\"", "\\\"") ++ "\"" };

UGen.allSubclasses.reject { |c| c.isMetaClass }.sortMap(_.name).do { |cls|
	var methods = Dictionary.new;
	rateMethods.do { |sel|
		var method = cls.class.findRespondingMethodFor(sel);
		if(method.notNil and: { [Object.class, UGen.class].includes(method.ownerClass).not }) {
			var names = method.argNames.asArray.drop(1);
			var defaults = method.prototypeFrame.asArray.drop(1).keep(names.size);
			try {
				SynthDef(\probe, {
					var u, make, check, base, n, slots = Dictionary.new, baseErr;
					var values = names.collect { |nm, i|
						var d = defaults[i];
						if(d.isNil and: { overrides[nm].notNil }) { overrides[nm] } {
							if(d.isNil and: { skip.includes(nm).not }) { DC.ar(0.5) } { d }
						}
					};
					cls.performList(sel, values);
					u = UGen.buildSynthDef.children.select { |c| c.class == cls }.last;
					if(u.notNil and: { u.inputs.size > 0 }) {
						make = { |r|
							switch(r, \audio, { DC.ar(0.5) }, \control, { DC.kr(0.5) }, { 0.5 })
						};
						check = { |ins| u.instVarPut(\inputs, ins); u.checkInputs };
						n = u.inputs.size;
						// T2K.kr reads audio: fall back to an all-audio baseline.
						[u.rate, \audio].do { |r|
							if(base.isNil or: { baseErr.notNil }) {
								base = Array.fill(n, { make.(r) });
								baseErr = check.(base.copy);
							}
						};
						if(baseErr.isNil) {
							n.do { |i|
								var allowed = probes.select { |r|
									var ins = base.copy;
									ins[i] = make.(r);
									check.(ins).isNil
								};
								if(allowed.size < probes.size) { slots[i] = allowed };
							};
						};
						if(baseErr.notNil or: { slots.size > 0 }) {
							methods[sel] = (rate: u.rate, inputs: n, slots: slots, baseline_error: baseErr);
						};
					};
				});
			} { |err| };
		}
	};
	if(methods.size > 0) { entries[cls.name] = methods };
};

File.use(outPath, "w") { |f|
	f.write("{\"sclang_version\":" ++ str.(Main.version) ++ ",\"ugens\":{");
	f.write(entries.keys.asArray.sort.collect { |name|
		str.(name) ++ ":{" ++ entries[name].keys.asArray.sort.collect { |sel|
			var m = entries[name][sel];
			str.(sel) ++ ":{\"rate\":" ++ str.(m.rate) ++ ",\"inputs\":" ++ m.inputs
			++ ",\"baseline_error\":" ++ (m.baseline_error !? str ? "null")
			++ ",\"slots\":{" ++ m.slots.keys.asArray.sort.collect { |i|
				str.(i) ++ ":[" ++ m.slots[i].collect(str).join(",") ++ "]"
			}.join(",") ++ "}}"
		}.join(",") ++ "}"
	}.join(","));
	f.write("}}");
};
"wrote % UGens to %".format(entries.size, outPath).postln;
0.exit;
)
