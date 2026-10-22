# Generation-only critical travel

Implemented for the source/test scope of TODO39eac8b86ad9 on 2026-10-20. This document does not mark the TODO, ledger, or parent reviews complete. The full design review is in `.local/critical-travel-review/REVIEW.md`.

Only `WoWPilagoWorld.create_regions` changes production behavior. Each new generation has five core regions: Menu, the selected profile's `Starting region <starting_zone>`, Azeroth, Outland, and Northrend. They exist even with every check category disabled.

| Directed connection | Requirement |
| --- | --- |
| Menu → selected start | Always; the only Menu exit |
| Selected start → Azeroth | Ordinary abstract walk/boat/zeppelin travel |
| Azeroth → selected start | Always |
| Azeroth → Outland, Dark Portal | Five Progressive Level Caps (cap 60) and Outland Access |
| Azeroth → Northrend, Alliance boat or Horde zeppelin | Six Progressive Level Caps (cap 70) and Northrend Access |
| Outland → Azeroth, Dark Portal return | Always once Outland is reachable |
| Northrend → Azeroth, return boat/zeppelin | Always once Northrend is reachable |

Only the selected faction's northern ingress exists. Neither expansion requires the other expansion item. These are route-family abstractions; cap 60/70 is a conservative AP boundary matching current check minima, not a claim about native boarding levels, specific docks, transport schedules, terrain, or runtime route enforcement.

Existing location buckets group by `(curated expansion owner, inherited requirements, opening)`. Opening leaves attach to the selected start; other leaves attach to their curated expansion region. Every leaf entrance retains the entire old access rule, including redundant expansion gates and inherited cross-expansion requirements. No numeric region/entrance IDs or serialized graph fields are introduced.

Curated expansion determines ownership, never map ID. Blood Elf and Draenei map-530 starts remain Azeroth and need no Outland Access. Tests cover all six existing Azeroth top zones on map 530: Eversong, Ghostlands, Silvermoon, Azuremyst, Bloodmyst, and Exodar, respecting faction filtering.

The addressless `Reach Level 80` event stays in Menu with its locked `Level 80 Victory` item. Exactly seven Progressive Level Caps suffice; six do not. Expansion, gear, abilities, and riding are unnecessary for this AP victory rule. The ordinary numbered `Reach level 80` check remains distinct. Native victory still requires actual server-confirmed level 80.

Real quest parents and inherited requirements continue to represent the logical ability to perform a chain. No completion events are added, and AP does not track live quest completion order. Disabling prerequisite reward categories leaves ordinary prerequisite gameplay necessary. Dungeon and raid prerequisite feasibility likewise does not replace runtime boss credit or same-instance history.

All 52 profiles retain exactly 20 local opening checks: 17 quests, one exploration entry, and two level checks. Faction-wide empty-state reachable totals remain 66–79. Default counts remain:

| Race group | Numbered checks |
| --- | ---: |
| Human, Dwarf, Night Elf, Gnome | 213 |
| Orc, Troll | 205 |
| Undead, Tauren | 206 |
| Blood Elf | 215 |
| Draenei | 218 |

The default Human pool remains 213 items, including 49 Gold Caches and 36 Consumable Caches. Literal 300-item content expansion and its 100/72 filler composition remain a separate open content task.

## Offline verification

Executed with an Archipelago Python environment, upstream `/tmp/archipelago-upstream`, `PYTHONDONTWRITEBYTECODE=1`, and the existing `.local/room-dependency-overlay` on `PYTHONPATH`. `tests/verify_world.py` bootstrapped the actual zipped world into a fresh temporary AP user path; nothing was installed into upstream.

- `tests/verify_world.py /tmp/archipelago-upstream`: **34 tests passed**, followed by successful real restrictive generation, spoiler, and protocol-2 multidata checks.
- The exhaustive real AP graph matrix uses all 52 profiles × eight cap counts (0–7) × four expansion inventories × four Expert/Cold Weather inventories: **6,656 inventories and 1,403,776 numbered-location comparisons**, plus the same number of full leaf-rule comparisons against an independent implementation of the old inherited pure rule. Core gateway reachability and cap-only victory are checked in every inventory.
- The existing all-profile and category fill tests remain. **3,328 profile/category combinations** comprise **1,094 successful restrictive fills** and **2,234 expected fixed-reward capacity rejections**. Even rejected combinations construct and verify the selected start first.
- `tests/simulate_seeds.py /tmp/archipelago-upstream --seeds 52`: **52 additional successful real fills**, covering all 52 profiles. This bounded run is not the separate 2,000-seed statistical exercise.
- Existing default pool, useful-reward independence, prefill, exclusions, multiplayer, cap self-lock, victory, and progression tests pass. New tests cover owner ancestry, no Menu bypass, faction routes, unconditional reachable returns, thresholds, map-530 starts, real quest closure, and disabled boss prerequisites.
- Temporary in-memory changes to individual real catalog rows test missing-parent closure, cycle rejection, cross-expansion ownership, and future direct/inherited Cold Weather handling (cap 77 rounds to seven caps and requires Expert). Each row is restored. No catalog file is modified; no constant world replacement is used.
- All 52 fixed-seed profile slot-data values, per-field hashes, requirement hashes, pool counts, and opening/reachable counts match their pre-change baselines.
- Two fresh actual generations at seed **919000001**, one using the captured pre-change package, produced identical slot data, datapackages, numbered IDs, and placements. The canonical generated slot-manifest SHA-256 is `8a6752fae7754271991cc41a6a18c6e379179be55a0c9222b3e8b99ec9925df8`. Placement equality here is an observation for this seed, not a cross-version guarantee.

Evidence, command logs, captured packages, and before/after manifests are in `.local/critical-travel-implementation/`. `before.apworld` is the captured current-source baseline, not the frozen room package. `after.apworld` is the separately identified new generation package.

## Byte preservation and deployment boundary

All **120** snapshotted files match before/after: six catalog JSON files, 20 files in `.local/real-room-frozen-source`, and 94 original room files in `.local/v2-multiworld/run-79mlu0ta`. This is a file-hash check only; no original room was loaded, regenerated, resumed, or authenticated.

| Catalog file | Unchanged SHA-256 |
| --- | --- |
| abilities.json | `5ea50ae2c4587784fb8fe60b1b09f1bca13258b36db4b13b5fa03354822dedb7` |
| checks.json | `05f20411c9111103e9505ae6ce3c53348ede3419a9321a7b81b865addfb29af0` |
| gear.json | `650918a637a5de2e38bf71a0d6d5f4502ecc378fbfbabf7982de9fa3cf904716` |
| profiles.json | `983eb0520c12881976be715c822cdad21dbc8e0b5be148f5cfe90cac74795963` |
| retired-checks.json | `28897a9e7404a26f545b6875fd6f1584cd53927e9544fee6ad4387ccb3f531a8` |
| rewards.json | `afef139f580393bdb2cbee5567e5404339ac2a3c65763ee6bab34a47bd1fb423` |

The semantic catalog version remains `4611c269173e443bff425e85a255fa086315ffdec0657c9098982d8e6fe9e1b0`. The original room save remains `d7a6744dac9404f1c4dd60b10fcedb1a25aed67f10f14f1b3b8f7ca335be84b3`; its original manifest remains `c7b42ef8e28e97cf9edee06e8767ff426cc26b4f2067e19bced94a58e86f41c2`.

Source/package bytes necessarily change. The captured new package SHA-256 is `3091685148fb5a9bef914fe295b6569dce773468d2e3a506352741a9d624c722`; it is for future generations only. Keep the existing room's frozen package, source, manifest, saves, and GUID4 binding. No database or binding reads/writes were performed, so this work makes no fresh runtime binding claim.

This work performs no authentication, network activity, server start, native/GUI operation, bridge/config/SQL/C++ edit, catalog expansion, or existing-room deployment. It does not establish gameplay transport execution, native completion-order tracking, live level-80 completion, or complete 1–80 geographic pacing. GUI/display and source/gossip audit work remain outside this implementation.
