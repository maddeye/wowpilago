# Read-only navigation waypoints

Run from the repository root. This tool prints world `[x,y,z]` ground waypoints as JSON. It does not connect to the server, send movement, control GUI 94, or write client data. Pilot sa40 retains normal input ownership.

```sh
.local/navmesh/navmesh_path 0 -8911.4 -166.328 82.2088 -8947.64 -132.319 83.7199 \
  --base ../wow-test/data/client-data/mmaps
```

Saved route: `.local/navmesh/northshire-to-willem.json`.

## Build and check

Host `g++` is sufficient. No new dependencies or whole-core build.

```sh
SOURCE=.local/v2-build/20261019T150600.624050Z/source
mkdir -p .local/navmesh
g++ -std=c++17 -O2 \
  -I"$SOURCE/deps/recastnavigation/Detour/Include" \
  -I"$SOURCE/src/common" -I"$SOURCE/src/common/Collision/Maps" \
  tools/navmesh_path.cpp "$SOURCE"/deps/recastnavigation/Detour/Source/*.cpp \
  -o .local/navmesh/navmesh_path
python3 -m unittest discover -s tests -p test_navmesh_path.py -v
```

Tests rebuild that same disposable binary. They check coordinate roundtrip, bad input, missing/truncated files, bad tile headers, both directions of the actual Northshire route, endpoint heights, the exit bend, and a deliberately wrong altitude. Tests skip when the pinned source/compiler or actual data is unavailable.

## File and coordinate contract

The pinned source is `.local/v2-build/20261019T150600.624050Z/source`.

- `src/common/Collision/Management/MMapMgr.cpp` reads a raw `dtNavMeshParams` from `MMM.mmap`, then `MmapTileHeader` plus its payload from `MMMXXYY.mmtile`.
- `src/common/Collision/Maps/MapDefines.h` supplies the actual 56-byte header, version 20, and terrain flags. The tool includes this header rather than guessing offsets.
- `src/server/game/Movement/MovementGenerators/PathGenerator.cpp` maps world xyz to Detour yzx. The tool reverses that permutation for output.
- `src/tools/mmaps_generator/MapBuilder.cpp` supplies tile bounds and filename ordering. Detour uses the pinned 64-bit polygon references. Its `maxPolys` parameter is unused in this build; the actual map-0 file contains signed `-2147483648` there.

Default read-only data directory: `./mmaps`, relative to the current working directory. Select your matching data with the trailing named argument `--base MMAPS_DIRECTORY`. Existing callers using data elsewhere must now pass `--base` explicitly. Only use trusted matching server assets, not arbitrary downloaded tile payloads.

## Bounds and failures

Local queries only: endpoints at most 2,000 yards apart; load their tile bounding rectangle plus one tile margin. Split travel into local legs. Search endpoint polygons within two horizontal and three vertical yards, choosing the closest ground height before horizontal distance. There is no broad wrong-floor fallback.

Ground flags only; water, magma, slime, off-mesh corridor polygons and off-mesh waypoints are rejected. The corridor is bounded at 2,048 polygons, query nodes at 8,192, and output at 4,096 portal-crossing waypoints. Partial/truncated routes fail instead of returning a straight-line shortcut. Missing neighboring ocean tiles are allowed; missing required tiles cause endpoint/path failure. Errors go to stderr with exit 1 and no JSON on stdout.

## Northshire evidence

`.local/navmesh/evidence.json` records file hashes and measurements. `.local/navmesh/tests.log` records four passing tests.

Map 0 loaded nine tiles including `0004832.mmtile`. The complete corridor has 16 polygons and 16 waypoints, length 65.69 yards versus 49.72 direct. A Detour raycast confirms the direct segment is blocked. The route first bends east to `[-8905.60,-159.73,82.18]`, then heads northwest along the exit corridor before turning west toward Willem. Do not skip this bend and aim straight at the NPC.

The projected start is `[-8911.24,-166.39,82.18]`, 0.17 yards from the supplied position; the projected end is `[-8947.64,-132.32,83.88]`, 0.16 yards from Willem's supplied height. Route heights range from 80.85 to 83.88, not a roof or basement selection.

This is a static navmesh route, not proof of a client walk through the door. It does not account for live doors, units, client collision differences, or keyboard turning accuracy. `client_walk_verified` stays false. The pilot should test the first bend using short normal-input steps, observe progress at the doorway, and requery from a fresh position after a mismatch. No teleport, privileged API, DB writes, or restart is involved.
