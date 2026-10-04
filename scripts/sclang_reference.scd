// Record sclang's SynthDef wire contract for every UGen class.
// Run via scripts/sclang_reference.py; see docs/dev/ugen-metadata-audit.md.
//
// For each UGen subclass and each rate method it responds to, build a SynthDef
// that calls the method with its declared defaults. Arguments without a default
// get DC at the method's rate, or at audio rate if that fails. Record the
// method's arguments and the last instance of the class in the graph.
(
var outPath = thisProcess.argv[0];
var rateMethods = [\ar, \kr, \ir, \dr, \new];
var skip = [\mul, \add];
// Arguments that need structured values; nil defaults elsewhere get DC.
var overrides = (
	numChannels: 1, numChans: 2, envelope: Env([0, 1, 0], [1, 1]),
	specificationsArrayRef: `[[100], [1], [1]], weights: [0.5, 0.5],
	label: "x", rect: Rect(0, 0, 1, 1)
);
var json, str, num, entries, defaultTexts;

str = { |s|
	"\"" ++ s.asString.as(Array).collect { |c|
		case
		{ c == $" } { "\\\"" }
		{ c == $\\ } { "\\\\" }
		{ c.ascii < 32 } { " " }
		{ c.asString }
	}.join ++ "\""
};
num = { |x|
	case
	{ x == inf } { "\"inf\"" }
	{ x == -inf } { "\"-inf\"" }
	{ x.isNaN } { "\"nan\"" }
	{ x.asFloat.asStringPrec(9) }
};
json = { |x|
	case
	{ x.isNil } { "null" }
	{ x == true } { "true" }
	{ x == false } { "false" }
	{ x.isNumber } { num.(x) }
	{ x.isString or: { x.isKindOf(Symbol) } } { str.(x) }
	{ x.isKindOf(Dictionary) } {
		"{" ++ x.keys.asArray.sort.collect { |k| str.(k) ++ ":" ++ json.(x[k]) }.join(",") ++ "}"
	}
	{ x.isSequenceableCollection } { "[" ++ x.collect(json).join(",") ++ "]" }
	{ str.(x.asString) }
};

// Default expressions by argument name, read from the method source.
// prototypeFrame holds nil for non-literal defaults such as `root = 60.midicps`;
// sclang 3.14 evaluates those when the argument is nil.
defaultTexts = { |method|
	var text = File.readAllString(method.filenameSymbol.asString);
	var i = text.find("{", offset: method.charPos) + 1;
	var result = Dictionary.new, close = nil, depth = 0, piece = "", pieces = List.new;
	while { i < text.size and: { text[i].isSpace } } { i = i + 1 };
	if(text.copyRange(i, i + 3) == "arg ") { close = $;; i = i + 3 };
	if(text[i] == $|) { close = $|; i = i + 1 };
	if(close.notNil) {
		while { i < text.size and: { (text[i] == close and: { depth == 0 }).not } } {
			var c = text[i];
			if("([{".includes(c)) { depth = depth + 1 };
			if(")]}".includes(c)) { depth = depth - 1 };
			if(c == $, and: { depth == 0 }) { pieces.add(piece); piece = "" } { piece = piece ++ c };
			i = i + 1;
		};
		pieces.add(piece);
	};
	pieces.do { |p|
		var eq = p.find("=");
		if(eq.notNil) {
			result[p.copyRange(0, eq - 1).stripWhiteSpace.replace("...", "").asSymbol] =
				p.copyRange(eq + 1, p.size - 1).stripWhiteSpace;
		};
	};
	result
};

entries = Dictionary.new;
UGen.allSubclasses.reject { |c| c.isMetaClass }.sortMap(_.name).do { |cls|
	var methods = Dictionary.new;
	rateMethods.do { |sel|
		var method = cls.class.findRespondingMethodFor(sel);
		// Skip the abstract constructors inherited from Object and UGen.
		if(method.notNil and: { [Object.class, UGen.class].includes(method.ownerClass).not }) {
			var names = method.argNames.asArray.drop(1);
			var defaults = method.prototypeFrame.asArray.drop(1).keep(names.size);
			var texts = defaultTexts.(method);
			var args = names.collect { |n, i|
				var d = defaults[i];
				Dictionary[
					\name -> n,
					\default -> if(d.isNil) { texts[n] } {
						if(d.isNumber or: { d == true } or: { d == false }) { d } { d.asString }
					}
				]
			};
			var result = nil, lastError = nil;
			// Retry with a UGen as the first argument: some classes return a
			// constant input unchanged (Lag.ar(0) is 0).
			[[sel, false], [\ar, false], [sel, true], [\ar, true]].do { |attempt|
				var subRate = attempt[0], subFirst = attempt[1];
				if(result.isNil) {
					var children = nil;
					try {
						// Capture before finishBuild: sclang 3.14 drops unused pure UGens.
						SynthDef(\probe, {
							var values = names.collect { |n, i|
								var d = defaults[i];
								if(d.isNil and: { overrides[n].notNil }) { overrides[n] } {
									if(d.isNil and: { subFirst.not } and: { texts[n].notNil }) { nil } {
										if((d.isNil or: { subFirst and: { i == 0 } }) and: { skip.includes(n).not }) {
											if(subRate == \ar) { DC.ar(0.5) } {
												if(subRate == \kr) { DC.kr(0.5) } { 0.5 }
											}
										} { d }
									}
								}
							};
							cls.performList(sel, values);
							children = UGen.buildSynthDef.children.copy;
						});
					} { |err| if(children.isNil) { lastError = err.errorString } };
					if(children.notNil) {
						var hits = children.select { |u| u.class == cls };
						var others = children.reject { |u| u.class == cls }
							.collect { |u| u.class.name }.asSet.asArray.sort;
						var u = hits.last;
						if(u.notNil or: { subFirst }) {
							result = Dictionary[
								\substitute_rate -> subRate, \substitute_first -> subFirst,
								\emits -> others
							];
						};
						if(u.notNil) {
							result[\rate] = u.rate;
							result[\special_index] = u.specialIndex;
							result[\outputs] = u.numOutputs;
							result[\output_rates] = if(u.isKindOf(MultiOutUGen)) {
								u.channels.collect(_.rate)
							} { if(u.numOutputs > 0) { [u.rate] } { [] } };
							result[\inputs] = u.inputs.asArray.collect { |in|
								if(in.isNumber) { in } {
									if(in.isKindOf(OutputProxy)) { in = in.source };
									"ugen:" ++ in.class.name
								}
							};
						};
					};
				}
			};
			methods[sel] = Dictionary[\args -> args];
			if(result.notNil) { methods[sel].putAll(result) } { methods[sel][\error] = lastError };
		}
	};
	if(methods.size > 0) {
		entries[cls.name] = Dictionary[\superclass -> cls.superclass.name, \methods -> methods];
	};
};

File.use(outPath, "w") { |f|
	f.write(json.(Dictionary[
		\sclang_version -> Main.version,
		\ugens -> entries
	]));
};
"wrote % UGens to %".format(entries.size, outPath).postln;
0.exit;
)
