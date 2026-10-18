// A NetAddr that writes every outgoing message and bundle to a file, one per
// line, before sending it. Used by superdirt_oracle.scd (ORACLE_LOG_OSC).
OracleNetAddr : NetAddr {
	classvar <>logFile;

	// kind, latency (nil: immediate), sclang logical time, then the messages.
	*log { |kind, time, msgs|
		logFile !? {
			logFile.write(kind ++ " " ++ (time ? "nil").asString ++ " " ++ thisThread.seconds.asString ++ " "
				++ msgs.collect { |m| m.asArray.collect { |x| x.asCompileString }.join(",") }.join(" | ")
				++ "\n");
			logFile.flush;
		}
	}
	sendMsg { |... args|
		this.class.log("msg", nil, [args]);
		^super.sendMsg(*args)
	}
	sendBundle { |time ... msgs|
		this.class.log("bundle", time, msgs);
		^super.sendBundle(time, *msgs)
	}
}
