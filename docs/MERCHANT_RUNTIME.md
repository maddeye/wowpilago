# Personal merchant runtime

## Integration

Compile `src/APMerchant.cpp` with the module and call `WoWPilago::RegisterMerchantScripts()` once from the module loader. It registers `archipelago_merchant` and the public `.archipelago` command tree. Remove the old prototype command root before registering this one. Do not register a second `.archipelago` root. `WoWPilago::ShowStatus(Player*)` is also public for another player-only UI caller.

This change owns only `src/APMerchant.cpp`, `src/APMerchant.h`, `tools/build_world_sql.py`, `sql/world.sql`, `tests/test_merchant.py`, and this document. Loader, delivery, progression, catalogs, bridge, schema and TODO are outside its ownership.

The merchant calls the real `APDelivery.h` APIs. `BuyStock` alone owns debit, grant, receipt, sold-marker, authorization and crash-consistency handling. `EquipAuthorized` and `UseAuthorized` own item-instance authorization and normal core equip/use validation. No inventory or voucher writes occur in the merchant. Failure messages do not claim delivery succeeded.

## Player UI and privacy

Every city reads the same durable binding stock. The view joins the current server-resolved binding ID and the interacting player's character GUID, and rejects archived or non-v2 bindings. There is no caller-supplied character, seed, slot or query override. All SQL substitutions are server-owned integers. Queries are synchronous, matching the existing module boundary. Module code cannot add core prepared-statement enum entries without modifying files outside this change.

Four categories cover weapons/shields/held items, armor/cloaks, jewelry/trinkets, and set pieces. Set pieces take precedence over their ordinary slot category. Pages contain at most 12 stock rows plus four navigation/summary rows, below the 32-option gossip limit. Stock is never level-filtered. All configured 30 through 120 entries remain inspectable, including sold entries, actual item hyperlinks, voucher prices and stable zero-based stock indices. The header displays current persisted vouchers and the sum of unsold prices. Stock generation and the default count of 60 remain the APWorld/bridge's responsibility.

Selection reloads this player's binding stock and checks NPC interaction range, flags and entry, index bounds, catalog membership, class compatibility, catalog price, sold status and balance. Legendary templates and legendary catalog entries fail the entire view closed. Delivery must still independently validate its transaction, including catalog/legendary rejection. The sold row is informational and cannot select a purchase. No stock is stored in `CreatureAI`, a shared NPC object, or `npc_vendor`. There is no per-NPC or cross-player cache.

`.archipelago status` and `.archipelago` show binding seed/team/slot, bridge status and heartbeat freshness, cap/level, XP bank, riding available versus received-but-pending, talent eligibility, vouchers, unsold cost, remaining enabled checks, pending deliveries and authorized item GUIDs. A recent heartbeat is a bridge observation, not a separate probe of the AP server socket.

Public player commands use `SEC_PLAYER`, `Console::No`, typed `uint32` item GUID arguments, typed equipment slots and no target-player argument. They require the caller's own human binding. No GM privilege is needed.

```text
.archipelago status
.archipelago buy <stock index>
.archipelago equip <owned authorized item GUID> <equipment slot 0..18>
.archipelago use <owned authorized item GUID>
```

For `buy`, select a nearby Archipelago merchant first. Gossip buying uses a confirmation popup and closes after the attempt. Reopen to read committed stock. Equipment slots are normal zero-based WoW equipment slots, including rings 10/11 and trinkets 12/13. Equip/use do not waive proficiency, class, combat, uniqueness, cooldown, targeting or other ordinary gear requirements. Delivery's current use fallback supports unit/self targets, not ground/item targets.

## World data

Entry `900500` is named `Archipelago Equipment Merchant`, faction 35, non-attackable flag 2, gossip NPC flag 1, ScriptName `archipelago_merchant`. Display 25465 comes from the pinned DB's neutral merchant Scalper Ahunae, entry 28484. Level 80 on the NPC does not impose a player-level restriction.

The generator reads only `acore_world` through TCP `127.0.0.1:13317`, root, with `WOWPILAGO_DB_PASSWORD`. It uses the installed `mysql:8.4` Docker image as the client, host networking, and `MYSQL_PWD` rather than a password command argument. It never executes its generated SQL or writes to any realm schema.

```sh
WOWPILAGO_DB_PASSWORD=test-only python tools/build_world_sql.py
```

Source DB observed during verification: `ACDB 335.17-dev`, cache ID 17. Entry 900500, its models, GUIDs 9005000 through 9005009, and existing spawns using the entry were all absent. The generator validates finite/map-bounded coordinates, the expected map for each city, source uniqueness, allocation collisions and existing NPC distance. It does not invent elevations or assume that a city name implies its map.

| City | Map | game_tele ID | Spawn GUID |
| --- | ---: | ---: | ---: |
| Stormwind | 0 | 954 | 9005000 |
| Ironforge | 0 | 507 | 9005001 |
| Darnassus, Temple of the Moon | 1 | 993 | 9005002 |
| Exodar | 530 | 1055 | 9005003 |
| Orgrimmar | 1 | 703 | 9005004 |
| Undercity | 0 | 1263 | 9005005 |
| Thunder Bluff | 1 | 1212 | 9005006 |
| Silvermoon | 530 | 869 | 9005007 |
| Shattrath | 530 | 859 | 9005008 |
| Dalaran | 571 | 1398 | 9005009 |

Coordinates and orientations are copied exactly from these game_tele rows into `sql/world.sql`. The central Darnassus teleport, ID 252, failed the NPC clearance check because arena-event pedestal NPCs occupy it. The Temple of the Moon anchor passed without an arbitrary coordinate offset. All selected anchors have no existing foreign NPC within three metres in 3D on their map. These are DB navigation anchors, not proof of live client walkability, gameobject clearance or immunity from future roaming NPCs.

Install `sql/world.sql` into the world database only during the coordinator's deployment step. It uses one transaction over the three pinned InnoDB tables and an installation procedure that signals errors on collisions. Only a template with the exact merchant name and script, and reserved spawn GUIDs with the exact entry and `WoWPilago merchant v2` comment, may be updated. An existing merchant entry spawn outside the reserved range aborts installation rather than being deleted or duplicated. Foreign templates and spawns are never deleted. Import-time distance checks repeat the generation-time overlap guard. A failed installation can be retried, since the next import recreates the installer procedure. Run installation while other world-content installers are stopped; this is not a concurrent installer protocol.

## Verified evidence

`WOWPILAGO_DB_PASSWORD=test-only WOWPILAGO_MERCHANT_SQL_TEST=1 python -m unittest discover -s tests -p test_merchant.py -v` passed all three tests with no skips. Tests execute production C++ category/page/cost/selection helpers under undefined-behavior sanitization for every stock size from 30 to 120. They cover sold visibility, category precedence, all-in-one-category paging, invalid actions, index bounds and separate stock vectors. They do not mock core callbacks and do not claim a live gossip purchase occurred.

Generator tests execute the production generator, including repeat generation, wrong-map/NaN/out-of-map/missing/duplicate source rejection, template/GUID/entry collisions, same-map NPC overlap and rejection of write/multiple-statement query inputs.

The MySQL test creates a uniquely named disposable `wowpilago_merchant_test_*` schema, clones the actual pinned `creature_template`, `creature_template_model` and `creature` table definitions with `CREATE TABLE ... LIKE acore_world...`, and imports the actual `sql/world.sql` twice. It verifies exactly ten merchant spawns, preservation of foreign rows, template collision failure, foreign reserved-GUID failure, out-of-range entry-spawn failure and overlap failure. The test drops only its own newly created schema. It does not install or delete anything in `acore_world`.

Final `APMerchant.cpp` object compilation passed with C++20, `-O0 -g0 -Werror`, using the existing `wowpilago-module-check:latest` compiler environment and compile-command include/define settings. The source mounted at `/core` was the actual local patched checkout `../wow-test/azerothcore`, HEAD `9fb906bb7296212ff42fc95ff73a92aaf8554f0d`, not the image's older embedded core. Project sources were mounted read-only at `/module`. The real concurrent agent's `APDelivery.h` was present; no stub or fake delivery implementation was used. Object output: `/tmp/wowpilago-merchant-results/APMerchant.cpp.o`, SHA-256 `b117181c122d64463f3bf492edb739d1f65a6ef77adc235e8584d5927ef2c279`. The object is not a linked worldserver build.

Python byte compilation passed. The core SQL style checker could not run because this project has no `origin/master` remote, which that checker fetches. SQL behavior was verified by the isolated MySQL imports above, not by claiming a style-check pass.

## Live checks still pending

The coordinator still needs to wire registration/remove the prototype command root, link and deploy the full module, and install the world SQL. No realm restart, world install or live character mutation was performed here.

Use two bound human players with different manifests to check privacy, city-to-city stock identity, relog persistence, all 120 entries, bought labels, balance/cost updates and forged/stale selection rejection. Verify purchases and full-bag failures through the delivery implementation, rather than inferring transaction safety from UI tests. On a normal 12340 client, inspect all ten spawn locations and both factions' interactions, then exercise command equip/use with original high-level items and ordinary non-AP copies. NPC walkability, actual client item-link rendering, authorization/proc/set behavior and complete linked-runtime integration remain unverified.
