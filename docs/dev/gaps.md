# Gaps

nanosynth gaps that affect nanodirt's parity with strudel.cc and with Tidal on stock SuperDirt. As of 2026-11-11. Front-end gaps are in nanodirt `docs/dev/gaps.md`. Status and priorities are in `TODO.md`.

- **No MP3, Ogg or FLAC decoding.** libsndfile is built WAV/AIFF only. Strudel's `piano` map and the `gm_` soundfont presets are MP3, so nanodirt needs ffmpeg. Options are in nanodirt `docs/dev/soundfonts.md`.

- **Realtime tests run in CI on Linux only.** First users are on macOS. The macOS realtime suite passed once by hand (2026-10-27, `roadmap.md` R4).

- **`Select` flattens a vector inside `sources`.** sclang expands one `Select` per channel; nanodirt writes these per channel by hand.

- **`IEnvGen` is missing.** Only SuperDirt's unused `DirtEnvGen` needs it.

- **Supernova crashes on reboot in one process.** Not blocking: nanodirt uses scsynth.

- **Some UGen errors are not detectable by the current checks.** Overruns from computed `IN`/`OUT` indices (`ugen-metadata-audit.md`, step 4), and swapped inputs that share a default.

- **199 arguments in 101 UGens are required in nanosynth but defaulted in sclang** (`compatibility-position.md`, "Low"). Translations must spell them out.
