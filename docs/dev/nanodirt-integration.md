# nanodirt and nanosynth: packaging

Status: analysis, 2026-10-18. No decision yet. Related: `roadmap.md`, `livecoding.md`.

## Licences

Checked against each project's licence file at the revision nanodirt reads.

| Project | Licence | nanodirt's relation |
|-|-|-|
| nanosynth | MIT | dependency |
| SuperDirt `650a1d6` | GPL-2.0-or-later (`LICENSE`; header in `SuperDirt.sc`) | nanodirt translates its classes and SynthDefs: a derivative work |
| Vowel quark | LGPL-2.1 | nanodirt copies its formant tables |
| vortex `aefea84` | GPL-3.0-or-later | `nanodirt.vortex` imports it |
| Strudel `a3302cf` | AGPL-3 | nanodirt reads its sample maps (data) and reimplements small helpers (`noteToMidi`, `githubPath`) |
| Tidal | not used | talks to nanodirt over OSC only |

nanodirt is GPL-3.0-or-later. That satisfies SuperDirt through its "or later" clause and vortex directly.

## Should nanodirt merge into nanosynth?

For merging:

- **Version coupling.** nanodirt pins nanosynth by local path. It cannot ship until nanosynth releases sc3-plugins and the fixes nanodirt needed.
- **Cross-cutting changes.** Four nanosynth fixes came from nanodirt work: `DynKlank` expansion, `LFGauss.range`, UDP after reboot (`patches/sc-asio-restart.patch`), and `LocalIn`'s first block. Each was two changes in two repos.
- **Split test setup.** The oracle (`scripts/superdirt_oracle.py`) and the sclang build live in nanosynth. The parity tests that use them live in nanodirt, which finds nanosynth by relative path.

Against:

1. **Licence.** A nanosynth wheel containing nanodirt is a GPL distribution. Merging into one package means relicensing nanosynth.
2. **Scope.** nanodirt is an application: UDP and WebSocket servers, a `websockets` dependency, a CLI, CDN downloads, ffmpeg, a vortex integration. nanosynth is a general engine.
3. **Cadence.** nanodirt follows SuperDirt, Strudel and vortex; nanosynth follows SuperCollider.

Options:

| | Option | Licence | Cost |
|-|-|-|-|
| A | Two repos, nanodirt depends on released nanosynth | separate | Drift between repos; the rules below contain it |
| B | One repo, two packages (uv workspace) | separate wheels, separate licences | Repo restructure, two release flows in one CI |
| C | One package | nanosynth becomes GPL | Ends nanosynth's permissive use |

C is viable only if you relicense nanosynth. The choice is between A and B. B is better if nanodirt is nanosynth's main consumer; A costs little if nanosynth has other users and releases often.

## Option A: preventing drift

1. **Declare a compatible range.** `nanosynth>=0.5,<0.6`; today it is `nanosynth>=0.4.1` with no upper bound. Before 1.0, a minor version may break, so the upper bound is the next minor. The `[tool.uv.sources]` path entry does not reach a built wheel's metadata, which keeps only the range. It does mean development runs against nanosynth's working tree, not the release users get; item 2 covers that.
2. **Test three nanosynth versions in nanodirt CI:**
   - the minimum in the range;
   - the latest release;
   - nanosynth `main`, nightly. A failure here opens an issue; it does not block nanodirt.
3. **Make the contract explicit.** Add `tests/test_downstream_contract.py` to nanosynth, covering the API nanodirt uses:
   - `Server`: `send_bundle`, `read_buffer`, `audio_bus`, `control_bus`, `next_node_id`, `on_node`, `default_group_id`, `status`;
   - `Options` fields;
   - `SynthDefBuilder`, `control`, `SynthDef.parameters`;
   - the signal helpers (`range`, `linlin`, ...);
   - `Envelope`;
   - the UGens and sc3 wrappers nanodirt builds with;
   - `OscBundle`, `OscMessage`, `OscError`.

   A change that breaks it needs a CHANGELOG "Upgrading" entry.
4. **Run nanodirt's suite as a downstream job in nanosynth CI**, on pull requests that touch `src/` or `thirdparty/`. This catches breaks before release, not after.
5. **Fix upstream, release, then bump.** A defect nanodirt hits in nanosynth is fixed in nanosynth first. nanodirt carries no monkeypatches. A temporary workaround names its TODO entry in a comment, as the per-channel `Select` workaround does.
6. **Record what the fixtures came from.** `tests/fixtures/superdirt_defs/` in nanodirt gets a manifest: SuperDirt revision, sclang version, sc3-plugins version, the oracle command. A test checks the manifest's SuperCollider version against the one nanosynth vendors (`SCVersion.txt`), so an SC upgrade forces regeneration.
7. **Release order.** nanosynth first, then nanodirt with a raised lower bound. Never release nanodirt against unreleased nanosynth behaviour.
8. **Keep shared tooling in one place.** The oracle stays in nanosynth: it is generic (SuperDirt on nanosynth's engine) and MIT, since it runs SuperDirt without containing it. nanodirt finds it through `NANOSYNTH_SRC`; it is never copied into nanodirt.

## Option B: advice for a monorepo

**Layout.** Keep nanosynth at the repository root and add `nanodirt/` as a uv workspace member, with its own `pyproject.toml`, `LICENSE`, `README.md`, `CHANGELOG.md`, `src/` and `tests/`. Moving nanosynth into `packages/` would disturb scikit-build paths, `build-dir`, the cibuildwheel and release workflows, and `thirdparty/` references, for no gain.

**Licence hygiene:**

- one `LICENSE` per package;
- SPDX headers (`GPL-3.0-or-later`) in nanodirt's source files;
- the root README states the split;
- nanosynth's sdist must exclude `nanodirt/`: add it to `sdist.exclude`, and check in CI that the nanosynth sdist and wheel contain no nanodirt files.

**Versions: independent, not in lockstep.**

- nanosynth's version signals engine and API changes, nanodirt's signals SuperDirt and front-end changes. Lockstep forces empty releases of one whenever the other changes, and a nanodirt fix would bump the version of a C++ wheel built for 15 platforms.
- nanodirt declares `nanosynth>=X.Y,<X.(Y+1)` exactly as in option A. Inside the workspace, uv resolves it to the local package, so development always runs against current nanosynth.
- Exception: if nanosynth has no users besides nanodirt, lockstep becomes the simpler choice. Then use one version and one tag, and accept that a nanodirt fix rebuilds the nanosynth wheels.

**Releases: when needed, not at the same time; ordered when coupled.**

- A nanodirt release must work with a *released* nanosynth. A release check installs nanodirt with nanosynth from PyPI at its declared minimum and runs the tests. This is the one rule that keeps the workspace from hiding drift.
- When a change spans both, release nanosynth first, then nanodirt with the raised bound, the same day if you like.
- Tags: keep nanosynth's unprefixed `<major>.<minor>.<patch>`, which `release-abi3.yml` requires. Give nanodirt `nanodirt-<version>` tags and its own workflow. It builds one pure-Python wheel, without cibuildwheel.

**CI:**

- Path filters: changes under `nanodirt/` run nanodirt's tests only.
- Changes to nanosynth run both suites, so nanodirt acts as nanosynth's downstream test.
- The oracle, audio and vortex tests stay opt-in, or run on a schedule; they need sclang, an audio device and network.

**Commits and changelogs.** A commit may span both packages. Each package's CHANGELOG gets its own entry, so each release's notes describe that package only.

## Questions that decide it

1. Will you relicense nanosynth as GPL? If yes, C is possible and only the scope argument remains.
2. Does nanosynth have, or expect, users other than nanodirt? If not, B with lockstep versions is the simplest. If so, A or B with independent versions.
3. Will nanosynth release often enough for nanodirt to wait for it? If not, B, so changes land atomically and releases follow in order.
