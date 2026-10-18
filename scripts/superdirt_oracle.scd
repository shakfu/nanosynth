// Attach SuperDirt to a running nanosynth engine as client 1.
// Started by scripts/superdirt_oracle.py, which passes settings in the environment.
(
var env = { |k, d| (k.getenv ? d) };
var port = env.("ORACLE_ENGINE_PORT", "57110").asInteger;
var dirtPort = env.("ORACLE_DIRT_PORT", "57120").asInteger;
var samples = env.("ORACLE_SAMPLES", "");
var orbits = env.("ORACLE_ORBITS", "12").asInteger;
var o = ServerOptions.new
	.numBuffers_(env.("ORACLE_BUFFERS", "262144").asInteger)
	.maxLogins_(env.("ORACLE_MAX_LOGINS", "4").asInteger)
	.memSize_(8192 * 32)
	.maxNodes_(1024 * 32)
	.numWireBufs_(2048)
	.numInputBusChannels_(2)
	.numOutputBusChannels_(2);

s = Server.remote(\nano, OracleNetAddr("127.0.0.1", port), o, 1);
Server.default = s;
s.latency = 0.3;
s.doWhenBooted({
	// ORACLE_LOG_OSC=path: log every message SuperDirt sends, from its node tree on.
	env.("ORACLE_LOG_OSC", "").size.sign.do {
		OracleNetAddr.logFile = File(env.("ORACLE_LOG_OSC", ""), "w");
	};
	~dirt = SuperDirt(2, s);
	if(samples.size > 0) {
		samples.split($:).do { |p| ~dirt.loadSoundFiles(p) };
	};
	s.sync;
	~dirt.start(dirtPort, 0 ! orbits);
	s.sync;
	// ORACLE_DUMP_UGENS=path: one line per SynthDef, its name then its UGen classes.
	env.("ORACLE_DUMP_UGENS", "").size.sign.do {
		File.use(env.("ORACLE_DUMP_UGENS", ""), "w", { |f|
			SynthDescLib.global.synthDescs.values.select { |d| d.def.notNil }.do { |d|
				f.write(([d.name] ++ d.def.children.collect { |u|
					(u.isKindOf(OutputProxy)).if { u.source.class.name } { u.class.name }
				}.asSet.asArray.sort).join(" ") ++ "\n");
			};
		});
	};
	// ORACLE_DUMP_DEFS=dir: each SynthDef's compiled bytes as <name>.scsyndef.
	env.("ORACLE_DUMP_DEFS", "").size.sign.do {
		SynthDescLib.global.synthDescs.values.select { |d| d.def.notNil }.do { |d|
			File.use(env.("ORACLE_DUMP_DEFS", "") +/+ d.name ++ ".scsyndef", "wb", { |f|
				f.putAll(d.def.asBytes)
			});
		};
	};
	"ORACLE READY client=% maxLogins=% synthdefs=%".format(
		s.clientID, s.maxNumClients, SynthDescLib.global.synthDescs.size
	).postln;
}, onFailure: { "ORACLE FAILED: engine did not answer".postln; 1.exit });
)
