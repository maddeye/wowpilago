# City merchant map-control verification

## Native ten-city PASS

The reviewed map-control run exited0 in56 seconds. Parent independently decoded100 actual gossip replies and matched every observed category/page to its raw packet. GUID24 saw all30 personal rows in six Alliance/neutral cities; GUID37 saw all30 in four Horde cities. Stock entries, prices, voucher balances and remaining costs matched their immutable manifests and stayed identical across city changes and normal relogs.

The control remained at friendly same-map anchors. Its only new credit was55 native exploration XP, leaving GM13 level1/XP110. GUID24 remained77/XP0; GUID37 remained32 with exactly24 native exploration XP. The source-bounded rested transition and protected-state comparison passed. All characters/accounts were offline afterward; eleven historical pending rewards stayed untouched. Original three FAIL folders remain preserved.

See `docs/verification/native-city-merchants.json` and `.local/city-merchants-plan/map-control-reviewed/parent-audit.json`. This proves native gossip for the two preserved30-row fixtures, not stock-client60-row UI, every profile/city cross-product, ordinary transport or purchases. Separate `docs/verification/native-stock-persistence.json` proves all960 stock rows unchanged across ordinary GUI respec/relogs and the captured normal daily-reset advancement.

## Historical source-only preparation

Status at preparation: SOURCE ONLY, implemented and offline-tested. Zero new native observations. The parent approved the same-map control model, not a runtime attempt. All three existing FAIL folders remain immutable: `.local/city-merchants-plan/`, `rest-reviewed/`, and `gossip-reviewed/`. No grant, attempt directory, authentication, database connection, server access, or GUI operation was created during this preparation.

Current implementation: `tests/verify_city_merchants.py`. Tests: `tests/test_city_merchants.py`. Source evidence, current hashes, and test results: `.local/city-merchants-plan/map-control-review/`. Future runtime output is exclusively `.local/city-merchants-plan/map-control-reviewed/`; that directory is not created by preparation or the default CLI.

Parent additionally modeled the source-derived rested-state transition before any live retry. Offline rest accumulated at login can change only an owned actor's restState2 to1 when its saved rest_bonus exceeds10. Other transitions and all other character fields remain protected. This is the pinned Player.cpp SetRestBonus rule, not a blanket rest-state exclusion. The additional regression rejects bonus0/10, reverse transitions and unrelated health changes. Parent reran53 City/RealmClient tests successfully in `parent-rested-tests.txt`.

## Offline checks

```sh
PYTHONPATH=.:tests .venv/bin/python tests/verify_city_merchants.py
PYTHONPATH=.:tests .venv/bin/python -m unittest tests/test_city_merchants.py tests/test_realm_client.py
```

The default CLI reports zero observations and reads only local files. The suite has 32 City tests, retaining all 23 prior tests, plus 20 unchanged RealmClient tests. Tests drive real CityClient, TravelClient, and RealmClient processing with literal packets and mocked lower-wire queues. They do not establish native permissions, ACK receipt, spatial resolution, or scheduling.

## Separate control and actor routes

GM13 remains the existing TEST account 1 Human Warrior, level 1, baseline XP55, GM mode off. Its original creation proof remains `MerchantRunner.reuse_control`; no shared profile or level guard changes. The local ownership check additionally requires XP55, playerFlags 0 or capital REST32 only, and extra_flags0. No new GM, `.gm on`, no-XP flag, faction change, or SQL gameplay write exists.

GM13 goes only to these four source anchors. An actor's city is never used as GM13's XP ancestry or `.go` destination.

| Base map | Control anchor spawn | Intended control ancestry | Positive signed-level descendants |
| --- | --- | --- | --- |
| 0 | 9005000, Stormwind | 1519 | 1519 level10 |
| 1 | 9005002, Darnassus | 1657 | 1657 level10 |
| 530 | 9005008, Shattrath | 3703 | none |
| 571 | 9005009, Dalaran | 4395 | 4395 level75 |

Actor24 is APV2F account7, Human Warrior77, binding14. Actor37 is APV2C account4, Orc Shaman32, binding27. Their birth, profile, manifest, seed/checksum, original 30-stock records, receipts and progress checks remain unchanged. GUID37's matrix-root FAIL and GUID24's historical extension FAIL are not relabeled.

The actor is moved directly by `.tele name EXACT_ACTOR EXACT_GAME_TELE_NAME`, never summon. Exact names come from the pinned `data/sql/base/db_world/game_tele.sql`, selected by full map/XYZ/orientation equality with reserved `sql/world.sql` spawns. Comments' city labels are not command names.

| Actor | City | Spawn | Exact game_tele name |
| --- | --- | --- | --- |
| 24 | Stormwind | 9005000 | Stormwind |
| 24 | Ironforge | 9005001 | Ironforge |
| 24 | Darnassus | 9005002 | TempleOfTheMoon |
| 24 | Exodar | 9005003 | TheExodar |
| 37 | Orgrimmar | 9005004 | Orgrimmar |
| 37 | Undercity | 9005005 | Undercity |
| 37 | Thunder Bluff | 9005006 | ThunderBluff |
| 37 | Silvermoon | 9005007 | SilvermoonCity |
| 24 | Shattrath | 9005008 | Shattrath |
| 24 | Dalaran | 9005009 | Dalaran |

The fixed dump reader checks the actual CREATE TABLE columns in order: `id,position_x,position_y,position_z,orientation,map,name`. For lines starting `(` it removes the outer tuple and trailing comma/semicolon, then uses standard `csv.reader` with comma delimiter, single-quote quoting, backslash escaping, `doublequote=False`, and `strict=True`. Seven fields, integer bounds, finite numeric positions, unique IDs, unique selected names, and unique matching anchor tuples are required. Unrelated duplicate names in the dump do not invalidate the ten selected names. There is no SQL parser dependency or general SQL parser framework.

Before any future transport, read-only SQL must match all seven fields of each source tuple and reject another row matching its name. All ten creature rows must also match the reserved source spawns before interaction. These live comparisons have not been run here.

## Source-backed command and NPC completion

All source paths below are relative to `.local/v2-build/20261019T191318.518327Z-mail-fixed/source/`.

`cs_tele.cpp:30..54` registers `teleport name` with RBAC permission740. `ChatCommand.cpp:234..275` supports visible command prefixes, including `.tele`. `ChatCommandArgs.cpp:48..67` resolves string names through `ObjectMgr::GetGameTele`; `ObjectMgr.cpp:9797..9819` prefers case-insensitive exact name matches. Numeric strings are not substituted for the selected names. Base RBAC links give security3 role192, then193, then197, then740. That source closure is not a claim about current live RBAC overrides or effective permission.

`cs_tele.cpp:109..197` checks online target security and rejects an already-teleporting target. Its exact English online reply is `You are teleporting |cffffffff|Hplayer:NAME|h[NAME]|h|r to LOCATION.` The offline branch inserts ` (offline)` after the player link and saves a DB position. An offline response, missing online response, wrong actor/name, parser error, security denial, or any other GM message refuses completion. `acore_string.sql` rows102/110/111/1511/1512 pin the teleporting/error formats. No new runtime GUID parser was added.

For each city the existing two-session lifecycle is retained:

1. Both owned sessions stay open. GM13's finite `.go xyz` moves only itself to its map's friendly anchor. Source `cs_go.cpp:432..492` is the self-player path. Success is source-silent and requires fresh per-GUID teleport/ACK evidence and anchor map/XYZ within five yards.
2. Only after that completion, GM13 sends the exact actor `.tele name` command. Completion requires the exact online reply plus a fresh actor teleport and matching ACK, correct actor map and XYZ within five yards. Both clients are pumped in bounded slices; 15 seconds is a deadline, not a sleep. Release and runner deadline checks run throughout. Unresolved commands are logged before cleanup.
3. GM13 queries `.npc info RESERVED_SPAWN` from the proven anchor on the same base map. `Chat.cpp:658..675` searches its current map's `GetCreatureBySpawnIdStore` without a distance check. Actor loading of its target grid can therefore make a remote same-map NPC available. `cs_npc.cpp:628..749` also has a DB fallback, which is explicitly refused. The bounded query pumps both sessions until the loaded response includes its position, script, and source-native zero spell-school mask marker.
4. The existing full native Creature GUID parser must find exactly one entry900500 GUID and the exact DB spawn ID. GM anchor and actor city maps must agree. Native NPC coordinates must be within five yards of the reserved source point and the actor. GM13 need not be within five yards of the NPC. Wrong map, wrong spawn, duplicate GUID output, DB-only data, or missing native coordinates fail. Only then may the actor gossip with that GUID.
5. Read all four categories and every Next page without purchasing. SEND validates against the retained prior menu before clearing it for the next reply. Compare all 30 original rows, prices, sold flags, balance and unsold cost across each actor's six/four cities and relog. Socket closure precedes bounded offline cleanup on failures too.

Permission, actor-grid loading across remote anchors, native menu visibility, actual-point terrain/VMAP ancestry and native command/ACK timing still need a future authorized observation. No runtime fallback, wider five-yard tolerance, fixed longer sleep, Horde control visit, or level relaxation is allowed.

Exodar and Silvermoon are Azeroth starter zones on map530. The pinned `APProgressionCanEnter` already uses `Azeroth530Zone` to exempt them from Outland access requirements. Actor37 does not receive Outland access; no progression bug fix is needed.

## Exact exploration and protected state

The actual pinned AreaTable DBC is traversed through every descendant, not merely city roots. GM13's four anchor ancestries contain exactly three positive areas: Stormwind1519 level10, Darnassus1657 level10, Dalaran4395 level75. Shattrath3703 has none. This proves the allowed set, not the terrain area's identity at an actual coordinate. Unexpected areas refuse.

`Player.cpp:5905..6020` computes exploration XP even with GM mode on. At level1, all three positive areas use source baseXP level6 =55 at `Rate.XP.Explore=1`. Source level1 threshold is400. At most three new areas give165 additional XP, so baseline55 +165 =220 <400. Source-only preflight verifies those DBC descendants, source rows and configured rate. No assumption about already explored areas is needed for this upper bound.

Only native opcode `0x1F8`, exactly two little-endian uint32 values, area and amount, supplies accepted credits. GM13's teleport/menu/logout phases require the current control anchor ancestry. Login permits only the same four friendly control ancestries, to accommodate its saved friendly location, including Stormwind after the future Talent work. It never permits an actor's Horde destination. Actor24/37 retain their original current-city ancestry and normal source XP formulas. A delayed packet outside the role's allowed phase/ancestry fails strictly.

Credits retain GUID, role city, session, phase, area, amount and raw bytes. Duplicate GUID/AreaID credits are rejected globally across sessions, both in the real client parser and final comparison. Saved13 must remain level1 with `after.xp == before.xp + sum(accepted13)` and XP<=220, at most three areas. Baseline must still be55. Only after exact validation is XP normalized for comparison. Actor24/37 have their unchanged exact native sums and levels. No blanket XP or timestamp exclusion was added; binding date normalization remains exact serialization, not ignored dates.

The existing frozen comparison protects all42 historical character identities, every other character's XP, flags, AP progress, XP banks, caps, rewards, all11 historical pending receipts, stock, vouchers, money, items, inventory, spells, talents, auras, skills, roles and legacy queues. This is the existing snapshot scope, not a new database audit or current census. DK42, normal4 and Transfer22 remain protected.

Only13/24/37 retain existing travel-position/explored-area and played/logout/rest/latency projections, plus capital REST32 masking. Every other flag remains exact. Control health, money, items and all AP state remain exact. The only aura exception remains actor24's native removal of saved flight spell32242. Only owned24/37 may add unacknowledged exploration outbox checks already listed in their immutable manifests. No receipt acknowledgement or purchase is fabricated.

## Preserved failures and future authorization

The first FAIL exposed capital resting projection; `rest-reviewed` exposed clearing the menu before select authorization; `gossip-reviewed` exposed the fixed-sleep completion assumption. `readiness-forensics/FINDINGS.md` establishes actor24 self-create/time-sync before the old summon and attributes the old teleport/ACK to GM13, not24. The offline summon reply was consumed after actor logout. Its exact original delay remains INCONCLUSIVE. The old nine-positive-city control route was independently unsafe for level1 and Horde combat; `completion-review/CONTROL_POLICY.md` remains an unchanged historical rejection. This implementation replaces that route, not those results.

A future parent must create a fresh `map-control-reviewed/release.json`, release all native owners and matrix work, independently verify offline/exclusive access, and approve at most1800 seconds. Required true fields remain `owned_release`, `gui40_released`, `mail46_released`, `native_matrix_released`, `all_native_owners_released`, `all_offline`, `no_other_runners`; also a nonempty release ID, timezone-aware issue/expiry and the pinned world hash. SA77's all-characters-offline Talent audit grants no City login permission.

Only then is `PYTHONPATH=.:tests .venv/bin/python tests/verify_city_merchants.py --run` eligible. It checks the release before runtime work, reserves `attempt.json` exclusively, verifies existing native/helper/ownership inventories and image/install provenance, and refuses to overwrite a previous attempt or FAIL. The runtime budget remains1720 seconds plus bounded cleanup. No automatic retry or alternate output root exists. This source preparation creates neither that directory nor its grant/reservation.

Pinned candidate fingerprints remain:

```text
world     3b9b2bf9f946a1eeef5908e440ed917132c0559c4bc483ba14be199060641809
image     sha256:55bfa1750408af5f5645166e47928aac6ecf0be92dd24005411cd96115f18ed9
manifest  6ac13239c2b11940904ece49ea6064c72980e433d6ef06aff587f36babc51553
base      0edea8dba721f996f00cf0b5c95e3576fff1ad4dd6e637fd8c0ad45b06f1285b
AP cpp    85e1a31476fe3d918dd61bfba685401c520707d72dcc3d4579788c3b4baa83c7
patch     76342b88b9864f85525771ba51de7c2b78467343027075b83184bc76356aca6c
```

No native/Core/shared-helper, config, grants, SQL or account-role files were edited. No purchase, AP ingress, GUI/full60 demonstration, reward setup, restart or new character was attempted. The native City status remains three preserved FAILs, not ten-city PASS.

Next action: rerun the two offline commands above. Do not authenticate from this preparation.
