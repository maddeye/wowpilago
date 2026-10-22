# Build the protocol-2 realm

## Fresh checkout

The host needs Docker with a running daemon, Git, tar, and Python 3 with venv
support. From the WoWPilago project root, create the Python environment and build
the Ubuntu 24.04 dependency image:

```bash
python3 -m venv .venv
docker build -f tests/Dockerfile -t wowpilago-v2-toolchain-check:latest .
```

The build tool and catalog generator need only Python's standard library.
`tests/Dockerfile` installs the compiler, CMake, Python, Git and development
libraries. It downloads no core source and compiles no module. Image creation is
not native feature validation. Do not overwrite `wowpilago-module-check:latest`:
the existing realm uses its exact image ID for runtime libraries.

Fetch the pinned Git objects into isolated repositories if you do not already
have the inputs described below. No checkout or submodule update is needed:

```bash
CORE="$PWD/.local/build-inputs/azerothcore"
git init "$CORE"
git -C "$CORE" fetch https://github.com/mod-playerbots/azerothcore-wotlk.git \
  9fb906bb7296212ff42fc95ff73a92aaf8554f0d
git init "$CORE/modules/mod-playerbots"
git -C "$CORE/modules/mod-playerbots" fetch https://github.com/mod-playerbots/mod-playerbots.git \
  2f7d9f774987d0157c6a0d0cc08c40bec3db3945
.venv/bin/python tools/build_realm.py --core "$CORE" --jobs 4
```

With the existing repositories at `../wow-test/azerothcore`, use
`.venv/bin/python tools/build_realm.py --jobs 4` after building the image instead.

Run the image build and full realm build in background terminals. A complete
build can take tens of minutes. Use `--jobs 2` or `--jobs 1` when less RAM is
available. The tool rejects
values above four. It uses `-O1 -g0` with core precompiled headers disabled to
limit compiler memory, not the core's usual optimized release settings.
Script precompiled headers remain enabled. Three content scripts at this pin
otherwise compile but fail to link because `Cell::VisitObjects` template
definitions come from `ScriptPCH.h`.

## Inputs

The tool needs `wowpilago-v2-toolchain-check:latest`, built with the command
above, Git, Python, tar, and the project's `.venv`. It records the image's
immutable ID and runs that ID, not a mutable tag after preparation. Rebuild the
image when its Dockerfile changes. The old runtime image is not a prerequisite.

- Core `9fb906bb7296212ff42fc95ff73a92aaf8554f0d`, archived from
  `../wow-test/azerothcore`.
- Playerbots `2f7d9f774987d0157c6a0d0cc08c40bec3db3945`, archived from
  `../wow-test/azerothcore/modules/mod-playerbots`.
- Current `patches/azerothcore-v2.patch`, applied by a snapshotted copy of
  `tools/apply_core_patch.py`. See [CORE_PATCH.md](CORE_PATCH.md).
- `patches/playerbots-safety.patch`, applied only to the archived pinned playerbots
  module with original/patched Factory fingerprints and an enforced patch digest.
  See [PLAYERBOTS_PATCH.md](PLAYERBOTS_PATCH.md) for the exact pin, digest and regression.
- Current `src/`, copied at build start after `.venv/bin/python tools/build_catalog.py`.
  The manifest records SHA-256 for each copied file, including `APCatalog.h`.

`--core /absolute/path/to/azerothcore` selects a different local Git repository
containing the same pinned commits. Both archives come from Git objects, never
host working-tree files. The source checkout and its modules may be dirty.
The tool neither resets nor patches them. Catalog regeneration updates the
project's generated native header and addon catalog as requested.

## What gets built

CMake configures the archived core from scratch with static content scripts,
static WoWPilago and playerbots modules, and both server applications. It does
not reuse `/core`, `/build`, or compile commands baked into the image.
The archived sources are mounted read-only during compilation. Docker networking
is disabled and the build runs with the invoking user's UID/GID.

Before compiling, the tool checks that every WoWPilago `.cpp` appears in the new
compile database. It checks `MOD_PLAYERBOTS`, the `PlayerbotMgr.h` include path,
and preprocesses the actual `APProgression.cpp` command to require
`WOWPILAGO_PLAYERBOTS=1`. This prevents a successful build that silently omits
the native playerbots adapter. The core's module discovery supplies these flags
and includes; no source changes are injected by the build tool.

Make runs with keep-going enabled so independent translation units can report
errors in one attempt. Any compile or link error makes the run fail. Installation
only follows a successful build. Neither application is started.

## Artifacts and outcomes

Each invocation creates a new timestamped directory under `.local/v2-build/`.
Previous runs are kept, with no deployment or runtime-directory replacement.

| Path inside a run | Contents |
| --- | --- |
| `manifest.json` | Pins, immutable image ID, source and patch digests, flags, outcome and timestamps |
| `source-files.sha256.json` | SHA-256 map of the complete patched source tree, including both modules |
| `source/`, `core.tar`, `playerbots.tar`, `inputs/` | Exact source snapshots and build/patch tooling |
| `build/` | CMake cache, compile database, objects and static libraries |
| `install/bin/worldserver`, `install/bin/authserver` | Linked binaries, only after a successful build/install |
| `*.log`, `adapter.macros` | Catalog, patch, configure, adapter, build, install and dependency-check evidence |

`module_tree_sha256` and `source_tree_sha256` hash the UTF-8 JSON representation
of their per-file digest maps with sorted keys and separators `(',', ':')`.
Archive digests cover the
complete Git tar streams. `installed_files_sha256` records installed files;
`libraries_sha256` records build-tree static/shared libraries on success.
`WITHOUT_GIT=ON` means the binary's built-in revision string says `Archived`;
use the manifest for the actual pins. Bit-for-bit binary reproducibility is not
claimed because build paths, timestamps and compiler details can affect output.

The tool exits nonzero and records `status: failed` on an ordinary failure.
Inspect `configure.log`, `adapter-check.log`, or `build.log` in that run.
A forcibly killed process can leave `status: building` or `preparing`; that is
not success. Do not deploy a failed or incomplete run. To rebuild after parent
source fixes, run the same command again for a fresh snapshot.

### Fresh toolchain verification

An uncached build succeeded:

```bash
docker build --no-cache --progress=plain -f tests/Dockerfile -t wowpilago-v2-toolchain-check:latest .
```

The resulting image ID was
`sha256:55bfa1750408af5f5645166e47928aac6ecf0be92dd24005411cd96115f18ed9`.
All 15 requested dependencies were checked as installed. Ubuntu 24.04 supplies
`libncurses5-dev` through `libncurses-dev`.

That exact image passed a fresh CMake configure using the full-build flags above,
the read-only pinned patched source at
`.local/v2-build/20261019T150600.624050Z/source`, and current `src/` mounted
read-only over the module source. The native playerbots adapter check passed.
The fresh compile database commands produced ELF objects for `APDelivery.cpp`,
`APMerchant.cpp`, `APProgression.cpp` and `mod_archipelago.cpp`, using the current
catalog version starting `4611c269`.

Local evidence is in `.local/toolchain-check/result.json`, `image-build.log`,
`packages.log`, `configure.log`, `adapter-check.log` and `objects.log`.
Source and existing install fingerprints, running container IDs/start times,
and the old runtime image tag were unchanged. This check did not repeat the
completed full realm build, link servers, install files or validate gameplay.
Ubuntu packages are not version-locked; a later image rebuild can have a
different ID. Each full build records the ID it actually uses.

### Post-curation cached refresh

The final-curation refresh reuses
`.local/v2-build/20261019T150600.624050Z/build`. Its one-shot driver is
`post-curation.py` in that run directory. It preserves the complete previous
`source/`, module, inputs, manifests and installed binaries in
`post-curation-before/` before updating anything. It regenerates the catalog,
replaces only the WoWPilago module snapshot, and applies the playerbots safety
patch to the archived module. It keeps the core patch digest
`3524780ac845b301fb606bcd74d80899669f5a18a8867f23cbade9fa06948c28` unchanged.

The driver reconfigures with the existing flags, rebuilds changed module objects,
relinks and installs into the same artifact directory. It checks that no core
object timestamp or core static-library digest changed. Evidence has distinct
`post-curation-` names, including `post-curation-manifest.json`,
`post-curation-source-files.sha256.json` and build, regression, registration,
macro and dependency logs. Earlier manifests and logs are not replaced.
`post-curation-RESULT.md` names the binaries and verification outcome.

This driver refuses to overwrite its own manifest. Do not rerun it over the
completed artifacts. A later refresh needs separately named evidence and another
backup. The normal build command above always creates a fresh run instead.

A successful result checks ELF headers and resolves shared-library dependencies
with `ldd` inside the build image. Host compatibility is not implied. There are
no server startups, deployment operations, container restarts or SQL writes.
Linking does not verify gameplay, database compatibility or client behavior.

The remaining pinned playerbots warning is
`src/PlayerbotAIConfig.cpp:984`, possible timestamp truncation in a bounded
`snprintf` into a 32-byte log timestamp buffer. It does not index enchantment
arrays and is outside the patched selection path. The safety patch removes the
Factory's iteration-three undefined behavior warning. No other playerbots logic
is changed. Neither a clean link nor the extracted-loop regression verifies
live gameplay.
