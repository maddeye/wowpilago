# TODO requirement and evidence audit

Audit snapshot: 2026-10-19. Only this document is owned by this audit. No content implementation, TODO checkmark, status JSON, realm table, account or character was changed. SELECT-only DB work used localhost:13317, root, the supplied test credential, and read-only transactions. Temporary scripts and outputs are under `/tmp/todo-*`.

## Findings that block blanket completion

| Requirement anchor | Finding |
| --- | --- |
| Ensure starting regions provide roughly **20–35 accessible checks** without needing item unlocks; aim for ~30. | Not met. Every one of 52 profiles has nine local opening checks. The 34-check assertion measures faction-wide logical access, not local starting-region content. See the source-backed replacement proposal below. |
| Include **100** Gold Cache items — Filler. | Present as base metadata, not an actual supported default seed pool. Alliance gets 59 and Horde 62. |
| Include **72** Consumable Cache items — Filler. | Present as base metadata, not an actual supported default seed pool. Alliance gets 42 and Horde 44. |
| Finalize the exact 150 quest / 60 zone / 48 boss / 14 dungeon / 16 level / 12 raid location catalogs. | Exact global counts and source validation pass, but finalization conflicts with the required local opening adjustment. |
| Run a real multiworld session with at least one other Archipelago game. | No inspected evidence. A two-WoW restrictive fill and synthetic websocket server are not this release gate. |

There is substantial proven data/APWorld work. There is not evidence for a finished v2 live game. Historical potion delivery is protocol 1, not proof of v2 caps, every check type, purchases, authorized high-level equipment, or actual level-80 victory.

## Evidence actually rerun or inspected

These are historical executed commands and raw outputs, not completion statements in subsystem documents. The personal interpreter path is shown as `/path/to/archipelago-venv/bin/python`; this redaction does not record a new run. Temporary paths are inspectable in this environment but are not durable release fixtures. Archive relevant logs before applying completion evidence elsewhere.

| Ref | Artifact and verification | Result and limit |
| --- | --- | --- |
| E1 | `support.json`; imported `tools.verify_support.verify_database` inside a read-only transaction; compared both source HEADs. `/tmp/todo-evidence-support-audit.log`. | Core `9fb906bb7296212ff42fc95ff73a92aaf8554f0d`; AP `54803be064fc7e80c4628777ed0b46a9390f255f`; ACDB 335.17-dev, cache 17, 2,917 updates and pinned update hash match. Build 12340 is the declared client target, not a fresh client handshake. Running binary provenance is not established. |
| E2 | `WOWPILAGO_DB_PASSWORD=test-only .venv/bin/python tools/validate_checks.py --report /tmp/todo-evidence-checks.json`; output `/tmp/todo-evidence-checks.log`. | Connected source/DBC validation succeeds, zero invalid rows. Exact 150/60/48/14/16/12 counts. All 52 profiles retain 229 Alliance or 234 Horde checks; 181/186 before cap 80; early 34, local nine. Current `docs/check-validation.json` agrees on these quantities. Provenance is a projection hash, not a full DB dump or proof of script playability. |
| E3 | `WOWPILAGO_DB_PASSWORD=test-only .venv/bin/python -m unittest discover -s tests -p test_check_catalog.py -v`; `/tmp/todo-evidence-check-tests.log`. | All 14 tests pass, including five real-source rejection/regeneration tests, with no skips. The opening test asserts faction-wide `early_checks`, not `early_local_count`. |
| E4 | `WOWPILAGO_DB_PASSWORD=test-only .venv/bin/python tools/validate_rewards.py --live`; `/tmp/todo-evidence-rewards-live.log`. | Source validation passes for 1,204 items, 70 sets and 72 abilities. Nine non-DK classes have eight source-audited abilities each. Broad role suitability is not a combat viability playtest. |
| E5 | `.venv/bin/python -m unittest discover -s tests -p test_reward_catalog.py -v`; `/tmp/todo-evidence-rewards-tests.log`. | All 27 tests pass. Real set counts, pricing, class proficiency/role policy, trainer/rank evidence and rejection cases are covered. |
| E6 | `/path/to/archipelago-venv/bin/python tests/verify_world.py /tmp/archipelago-upstream`; `/tmp/todo-evidence-world.log`. | All 26 AP tests pass, plus actual packaged generation, restrictive fill, spoiler and multidata assertions. Output `/tmp/wowpilago-world-test-uo5e791n`. Tests include all 52 profiles × 64 category selections, explicit rejection of undersized configurations, prefill, exclusions, balancing, two-WoW fill and configurable legendaries. None uses a live WoW client. |
| E7 | Same AP Python, `tests/simulate_seeds.py /tmp/archipelago-upstream --seeds 2000`; `/tmp/todo-evidence-2000.log`; raw report `/tmp/wowpilago-world-test-d7njl5rd/seed-simulation.json`. | 2,000 actual fills pass across 52 profiles. Every empty-state opening is logically 34. Independent piece inclusion 31,869/39,903 = 79.866%; full eight-piece rolls 530/3,301 = 16.056%, theoretical 16.777%; zero default overflow. Cost 209–281, mean 241.87; cheapest-first purchases mean 54.349/60. Check-quarter affordability 19.413, 33.6065, 45.835, 54.349. These are reward-order quarters, not elapsed leveling time. |
| E8 | Fresh packaged AP construction with asserts for Human Warrior and Orc Warrior; `/tmp/todo-evidence-pool.log`; inspected `create_items`, `test_pool`, `test_prefilled_location_accounting`. | Actual pools 229 = 128 fixed + 59 Gold + 42 Consumables; 234 = 128 fixed + 62 Gold + 44 Consumables. The packaged tests do not assert 100/72 in actual pools. |
| E9 | `.venv/bin/python tools/build_catalog.py --check`; `/tmp/todo-evidence-generated.log`. | Current `src/APCatalog.h` and `addon/WoWPilago/Catalog.lua` match authoritative JSON. The older header-regeneration warning in `docs/CATALOG_QUALITY.md` is no longer a current failure. Matching generated files does not prove the running binary contains them. |
| E10 | Native/core suites, `.venv/bin/python -m unittest discover -s tests -p test_native_progression.py -v`, and corresponding `test_native_delivery.py`, `test_core_patch.py`. Logs `/tmp/todo-evidence-test_native_progression.log`, `/tmp/todo-evidence-test_native_delivery.log`, `/tmp/todo-evidence-test_core_patch.log`. | 1 + 4 + 9 tests pass. Production policy and extracted functions execute with compiler assertions/sanitizers; core patch application/dispatch/validators are exercised in temporary copies. Not a linked realm/client or process-crash run. |
| E11 | `PYTHONPATH=tests .venv/bin/python -m unittest test_bridge_v2.ManifestTests -v`; `/tmp/todo-evidence-manifest.log`. | Four manifest/allowlist/stock boundary tests pass. No persistence SQL tests or realm writes were run. An initial invocation without `PYTHONPATH=tests` failed to import; corrected invocation passes. |
| E12 | Imported `tools.audit_todo.audit` without its CLI; `.venv/bin/python -m unittest discover -s tests -p test_todo_audit.py -v`; `/tmp/todo-evidence-support-audit.log`, `/tmp/todo-evidence-audit-tests.log`. | 187 anchors, zero checked, zero audit errors with empty evidence; three audit tests pass. `docs/requirements-evidence.json` is absent. Zero checked is not zero implemented. |
| E13 | Inspected and reran `/tmp/audit-wow-apids.py`, redirecting its report to `/tmp/todo-evidence-ids.json`; `/tmp/todo-evidence-id-audit.log`. | 98 item IDs and 300 location IDs versus 82 installed registered games; zero collisions, zero failed imports. Scope is this pinned installed registry, not all third-party APWorlds. `support.json` reserves legacy IDs and defines fresh-seed policy. |
| E14 | Raw `.local/live-delivery.log`, `.local/inventory-edges.log`; current `src/mod_archipelago.cpp`, delivery/progression/merchant implementations and SQL; historical `.local/v2-all-tests.log`. | Potion delivery/relog and full-bag/receipt-failure retry really have raw PASS lines, but are legacy evidence. The old v2 aggregate log contains two errors and one skip, not a green release run. Its bridge import error references an earlier file version. Do not treat it as a current failure without rerun, or as current success. Current loader registers all three v2 subsystems; older documents saying registration remains undone are stale. No fresh v2 linked/live evidence was established. |
| E15 | `/tmp/todo-starter-audit.py`, `/tmp/todo-starter-candidates.json`; exact proposal `/tmp/todo-starter-plan.py`, `/tmp/todo-starter-plan.json`; courier projections `/tmp/todo-courier-source.json`; impact `/tmp/todo-starter-impact.json`. | Read-only candidate/chain/restriction/DBC audit and in-memory proposal only. Exact source exceptions and remaining physical-play evidence are detailed below. No catalog was rewritten. |

`docs/CHECK_CURATION.md` uses `WOW_DB_PASSWORD` in its example commands and skip description, but the current validator/tests actually read `WOWPILAGO_DB_PASSWORD`. The examples would fail connected validation or skip live tests. E2/E3 used the actual variable and did not skip them. Its claim that the full update list is embedded is also stale; current provenance stores update count/hash projections, as `docs/CATALOG_QUALITY.md` correctly notes.

The support verifier CLI writes `docs/support-verification.json`; the TODO audit CLI writes `docs/requirements-status.json` even without `--apply`. Neither CLI was run. In particular, do not run `tools/audit_todo.py --apply` merely because this document exists: that tool consumes `requirements-evidence.json`, not this Markdown.

## Starting regions: physical content, not AP reachability

Current catalog arithmetic is 48 starter quests, six in each of eight distinct starting zones; one local zone-entry check and milestones 5 and 10 give nine. Dwarf/Gnome share Dun Morogh, Orc/Troll share Durotar. All 52 profiles are affected. Other friendly zones and cities account for the rest of the faction-wide 34. Boats, zeppelins, teleport orbs and walking between distant racial starts do not turn those checks into a local opening.

`create_regions` groups checks by cap/expansion/riding tuples and connects those groups directly from Menu. It does not model physical starter geography or journey time. Critical quest ancestors are converted to inherited item requirements, not a simulation of completed quest steps. This is adequate for bounded AP fill evidence, not for claiming a 30-check starting-area play session.

### Smallest count-preserving candidate under current check meanings

Keep the 300 global definitions and all six category totals. Keep existing starter quests, all exploration definitions and their zone-entry semantics, all bosses/clears/levels/raids. Replace 88 later quest definitions with eleven additional local quest definitions in each starting zone. Then each profile has 17 local quests + one zone entry + two milestones = 20 without AP item unlocks.

This is the minimum number of replacement quest definitions under those constraints: each distinct starting zone lacks eleven checks, and eight × eleven = 88. It meets the lower bound, not the ~30 aspiration. With only local quests, one zone entry and two milestones, 30 per zone would require 27 × eight = 216 quests, exceeding the entire 150-quest budget. Even distributing all 150 quests into starts gives only 21.75 average local checks with those three nonquest checks. A genuine ~30 target needs an approved change to check semantics/allocation or budget, not a relabeling of faction travel.

These are exact proposed new IDs. Existing six per zone remain unchanged. Titles and restrictions come from the pinned DB, not invented names or assigned ordinal IDs. For example, 179 is Dwarven Outfitters, 183 The Boar Hunter, 3361 A Refugee's Quandary, 318 Evershine and 319 A Favor for Evershine. Locality assertion output is `/tmp/todo-starter-locality.log`.

| Local region | Eleven additional source quest IDs | Required new ancestor edges, beyond existing ancestors |
| --- | --- | --- |
| Dun Morogh, races 3/7 | 179, 170, 183, 3361, 182, 218, 318, 319, 233, 234, 320 | 170←179; 218←182; 318←317 existing; 319←318; 233←179; 234←233; 320←319 |
| Elwynn Forest, race 1 | 783, 7, 5261, 33, 15, 18, 3903, 3904, 6, 21, 2158 | 7←783; 5261←783; 33←5261; 15←7; 18←783; 3903←33; 3904←3903; 6←18; 21←15 |
| Durotar, races 2/8 | 4641, 788, 789, 4402, 792, 790, 804, 817, 808, 834, 826 | 789←788; 4402←788; 804←790 |
| Tirisfal Glades, race 5 | 363, 364, 376, 3901, 3902, 380, 381, 382, 6395, 375, 426 | 3901←364; 3902←376; 380←376; 381←380; 382←381; 6395←376; 426←404 existing |
| Teldrassil, race 4 | 458, 456, 457, 459, 916, 4495, 3519, 3521, 917, 920, 476 | 457←456; 459←458; 3519←4495; 3521←3519; 917←916; 920←917; 476←475 existing |
| Mulgore, race 6 | 747, 752, 750, 753, 755, 757, 780, 3376, 766, 833, 754 | 750←747; 753←752; 755←753; 757←755; 780←750; 754←748 existing |
| Eversong Woods, race 10 | 8325, 8326, 8327, 8346, 8334, 8336, 8345, 8335, 8347, 9704, 9352 | 8326←8325; 8327←8326; 8334←8327; 8335←8334; 8347←8335; 9704←8347; 9352←8463 existing |
| Azuremyst Isle, race 11 | 9279, 9280, 10302, 9293, 9799, 9305, 9314, 9463, 9512, 9473, 9505 | 9280←9279; 9293←10302; 9799←10302; 9473←9463; 9505←9473 |

Two narrow source corrections are necessary before this proposal can pass honest validation:

1. `StartItem` is a quest-provided source item, not proof the quest starts from an item. `QuestDef.h:GetSrcItemId`, `QuestDef.cpp:LoadQuestTemplateAddon`, and `PlayerQuest.cpp:AddQuest`/`GiveQuestSourceItem` establish this. The proposed NPC-given quests 233, 234, 320 and 754 provide items 2187, 2188, 2696 and 5411 respectively. Their `item_template.startquest` values are zero. Real creature starters and enders exist. Add source-item count/template validation and separate actual item-start evidence; do not globally waive external item gates. All four currently fail only the validator's blanket `StartItem` prohibition. Preserve every other availability rejection.
2. Resolve `AreaTable` ancestry before mixed-map expansion classification and local-count attribution. Real starter subareas include Coldridge Valley 132→1, Northshire 9→12, Valley of Trials 363→14, Deathknell 154→85, Shadowglen 188→141, Red Cloud Mesa 220→215, Sunstrider Isle 3431→3430, Ammen Vale 3526→3524. Current `expansion()` labels 3431/3526 as Outland because map 530 exemptions recognize only top-level zones. Current local counting compares raw quest area to top-level starting zone. Keep source `area_id`; resolve its top-level parent for these policies rather than falsifying the DB area.

The temporary proposal leaves source rows unchanged except for in-memory suppression of the four known provided-item false rejections. It explicitly checks and accounts for the sixteen expected island-subarea expansion mismatches. All other `validate_sources` checks pass; prerequisite closure and real race/class masks give 20 local checks in all 52 profiles after these two proposed corrections. This is a source-backed candidate, not a passing unmodified validator or completed gameplay test.

The source scan also caught false local candidates: quest 787 is filed under Valley of Trials, but its starter Eitrigg is spawned in Orgrimmar. It was excluded from the final list in favor of 826. Quest 861 was avoided as a Mulgore addition because its route is not wholly local. All 88 final proposed quests have actual starter and ender spawns within their starting zone's `WorldMapArea` rectangle on its map. Realm `creature.zoneId`/`areaId` are zero for these spawns, so those cached columns cannot establish locality. Rectangles and quest categories still do not prove objective positions, terrain, script success or safe level-10 combat. These must be checked before marking the opening requirement verified.

### Explicit donor set and balance cost

A bounded donor rule is to retain these fourteen post-cap-10 quests, one faction-compatible choice per faction per later cap band, and retire the other 88 current post-cap-10 quest definitions:

| Cap | Retained Alliance quest | Retained Horde quest |
| --- | ---: | ---: |
| 20 | 12 | 844 |
| 30 | 56 | 216 |
| 40 | 1387 | 568 |
| 50 | 4124 | 2862 |
| 60 | 5092 | 9443 |
| 70 | 9777 | 9770 |
| 80 | 11155 | 11167 |

None of these retained later quests has a catalog ancestor. Exact retired IDs are derived from current `checks.json` and recorded in `/tmp/todo-starter-impact.json`. Global counts stay 150 quests / 60 explorations / 48 bosses / 14 clears / 16 levels / 12 raids. Global cap bands become 154, 12, 16, 11, 8, 10, 43, 46 for caps 10 through 80.

| Race IDs | Proposed filtered locations | Local early | Faction-wide early | Before cap 80 | Proposed Gold / Consumables |
| --- | ---: | ---: | ---: | ---: | --- |
| 1, 3, 4, 7 | 213 | 20 | 74 | 168 | 49 / 36 |
| 2, 8 | 205 | 20 | 66 | 160 | 45 / 32 |
| 5, 6 | 206 | 20 | 67 | 161 | 45 / 33 |
| 10 | 215 | 20 | 76 | 170 | 51 / 36 |
| 11 | 218 | 20 | 79 | 173 | 52 / 38 |

Narrow source race masks on introduction quests explain these differences. Do not invent native-race restrictions on the other starter quests to force faction-wide totals back to 34. Fixed reward count remains 128 and voucher supply remains 204.

This proposal is small in event-system scope, not in content impact. It makes 136/150 quests starter quests and leaves just fourteen later quest checks. It preserves the requested category counts, but weakens the separate cap-band balance requirement. It is the smallest quest-only lower-bound repair, not a recommendation to call the whole catalog balanced. If preserving broad later quest coverage or aiming near 30 is mandatory, the parent must approve a different allocation. Subarea exploration is a possible tradeoff, but would change the documented top-level-zone-only contract, require native area-transition reporting and new tests, and still retire/reassign real source identities. It is not a silent data-only substitute.

### Bounded implementation scope for the parent

| Surface | Required follow-up, not implemented here |
| --- | --- |
| Source validator and curation | Correct provided-item versus item-start validation; normalize area ancestry; review objective locations/scripts for the exact shortlist; replace exactly the agreed donor IDs in `QUEST_IDS`; regenerate checks/profiles and source evidence only after review. |
| AP and data tests | Assert local 20–35 per all 52 profiles with local prerequisite closure; stop imposing the same upper bound on faction-wide early checks. Keep a separate faction-wide count. Exercise actual pools/options/fills after replacement and review cap-band balance. |
| Native/addon/bridge consumers | Regenerate `APCatalog.h` and `Catalog.lua`, validate the resulting manifest/hash and rebuild the integrated module. Check local quest turn-ins and island access live. No new event type is needed for the quest-only proposal. |
| Identity and old seeds | Existing `kind_sourceID` keys/AP IDs never change meaning. New IDs are quest base 919500000 + real quest ID. Retired IDs remain reserved and must not be reused. New catalog hash requires a fresh seed; retain old catalog/header/binary for existing manifests. Never rewrite saved stock, checks, receipts, bindings or inventory. Apply protocol/schema increments if an incompatible contract change is chosen, per `support.json`, not to conceal a catalog replacement. |
| Acceptance | An eight-zone physical route/quest audit at cap 10 with no AP item unlocks, both shared-race starts and every legal class restriction, is still required. Then run ordinary fill/stock tests. Full client, playthrough and cross-game gates remain separate. |

## Pool arithmetic: exact base versus actual slots

`rewards.json` stores 100 Gold and 72 Consumables. With eight abilities and two legends, its proposed base is 300 = 128 fixed + 172 filler. Base classifications are 11 progression + 117 useful + 172 filler. Current checks require Expert Riding but no Cold Weather Flying, so actual default classification moves Cold Weather Flying to Useful: 10 progression + 118 useful, before filler.

All legal default profiles filter the global definitions. Actual item-bearing locations are 229 Alliance or 234 Horde, not 300. `create_items()` discards filler base counts and computes `filler = unfilled ordinary locations - remaining fixed rewards`; Gold is integer-rounded as `(filler * 100 + 86) // 172`, with Consumables taking the remainder. Therefore default filler is 101 or 106, yielding the E8 measured 59/42 and 62/44. The addressless locked victory event does not receive ordinary pool filler. Ordinary same-player fixed prefill decrements that reward's remaining fixed count. Excluded locations still exist and receive items; excluding them from progression placement is not deleting checks. Category removal and legendary-count changes alter capacity; undersized settings raise an explicit error rather than silently dropping fixed rewards.

`docs/CHECK_CURATION.md` and `docs/CATALOG_QUALITY.md` truthfully disclose filtered counts. `docs/IMPLEMENTATION.md` says normal baseline counts follow section 9 exactly and filler adjusts to actual locations, but never gives actual filler numbers. That sentence needs an explicit base-metadata qualifier. `test_pool` checks fixed counts and `sum(base_count) + 8 + 2 == 300`; it does not check actual Gold/Consumable counts or independently execute a 300-location configuration. Options/prefill tests check capacity, not exact filler ratio in every case. There is no supported default profile with a real 100/72 pool.

Do not mark the exact 100-Gold and 72-Consumable checkboxes fulfilled as actual-seed requirements. The parent must decide and record whether those anchors mean only the hypothetical 300-location base, while actual slots scale automatically, or whether 300 item-bearing locations per profile is required. The latter requires a much larger catalog and is not the current design. Preserving a literal 172 filler in 229/234 checks would force dropping fixed rewards, which the implementation correctly refuses.

## Live release evidence still needed

| Gate | Minimum missing evidence |
| --- | --- |
| Integrated v2 realm | Linked current loader/module/core patch and matching catalog; startup/config checks; real binding and all reward kinds; actual XP cap/bank release; talent/respec/dual-spec and trainer/rank paths; reconnect/restart/deletion and absent bridge/AP. Policy tests do not invoke every real core callback. |
| Client, travel and equipment | Build-12340 client interactions for ten cities, personal stock privacy, purchases/full bags, same-item ordinary versus authorized copies, original stats/procs/sets/sockets/enchants, equip/on-use restrictions and transfer attempts; actual boats/zeppelins/portals/teleports, starter islands, flying, temporary mounts and vehicles. |
| Credit and faults | Each check kind, same-instance/reset clear persistence, tap/group credit and playerbot assistance; simultaneous v2 purchases, rollback/deadlock, disconnect before/after commit, process kill between commit and publication, verification failure and restart recovery. Legacy potion probes and extracted SQL/core tests do not cover all this. |
| Leveling and balance | Actual cap-10 local opening route and 1-to-80 solo/playerbot-assisted run. Count coverage, conservative cap estimates and simulated voucher quarters do not prove leveling pace or baseline class viability. |
| Cross-game multiworld | At least one other AP game, real server connections, cross-game sends/receipts, reconnect and both goals. A local synthetic AP websocket or two-WoW generation is insufficient. |

## Exact requirement ledger

The following ledger preserves every checkbox description verbatim. `V` means the whole bounded data, design-decision, pure-generation or unit-test requirement is proven by named artifacts and reruns. It does not certify adjacent runtime behavior. `P` means implementation/partial evidence exists but the full wording remains unproven; keep open. `G` is a demonstrated gap. `D` is an explicit v1 deferral, not an implemented feature. No ledger row changes TODO automatically.


### 0. Agreed design baseline

| Status / ID | Exact checkbox text | Evidence or missing proof |
| --- | --- | --- |
| P `a7da8dda558c` | Build an Archipelago `APWorld` and an AzerothCore integration module/bridge. | E6 proves APWorld; source loader integrates modules, but E14 lacks current linked/live v2 bridge proof. |
| P `9433ed69edfe` | Support **curated** checks (not all quests by default): quests, level milestones, dungeon bosses, dungeon completions, zone exploration, and raid bosses. | Six-type data and reporting code exist; all six actual client events still need live evidence. |
| P `b9f218a44085` | Set **victory condition to reaching level 80**; do not require raids, equipment, or every ability to win. | E6 proves level-only logical goal; actual server-confirmed level-80 event needs a live v2 run. |
| V `8de94a908f29` | Use **hybrid randomization**: levels, expansion access, riding, selected class abilities, and reserved talent points can be Archipelago rewards. | E4/E6: selected cap/access/riding/ability/talent rewards exist in real pools. |
| P `647efb6151cc` | Keep baseline class combat functionality available without Archipelago rewards. | Whitelist preserves baseline exclusions in source; all-class baseline combat viability is not playtested. |
| P `07c845a98c93` | Implement seed-specific equipment vendors in major cities, with the **same personal inventory** at each vendor. | Generated personal stock and ten-city SQL exist; live city identity/privacy/persistence remains unproven. |
| P `cec1c7b32b15` | Award **equipment vouchers** through Archipelago; let players choose purchases. | E6 proves voucher pool; live receipt/balance/purchase path remains unproven. |
| P `214c43f9aba1` | Give **legendary equipment directly** as named Archipelago rewards, not through the shop. | E6 proves named direct reward generation; live delivery remains unproven. |
| P `3401e6ea9fe7` | Allow Archipelago-awarded equipment to be equipped **below its normal required level**, preserving original stats and set bonuses while retaining class/armor/weapon proficiency requirements. | E10 proves bounded policy only; integrated v2 issuance/equipment/client/transfer and crash cases remain unproven. |
| P `44b12dc083f9` | Make Archipelago-awarded equipment character/slot-bound, non-tradeable, and non-auctionable. | E10 proves bounded policy only; integrated v2 issuance/equipment/client/transfer and crash cases remain unproven. |

### 1. Project structure & data model

| Status / ID | Exact checkbox text | Evidence or missing proof |
| --- | --- | --- |
| V `5f73decf774e` | Pin the supported AzerothCore commit, database revision, and 3.3.5a client build. | E1: supported source/data/client target pinned; running binary is a separate question. |
| V `c46a9e3bb2ed` | Create repositories/directories for the Python APWorld, AzerothCore C++ module, bridge service, data catalogs, and tests. | Inspected apworld/, src/, bridge/, data/, tests/ directories. |
| V `243f7febbdd1` | Define stable, noncolliding Archipelago item and location IDs and a migration/versioning policy. | E13 plus support.json permanent-ID/fresh-seed policy; collision scope is installed upstream registry. |
| V `7ffb2d21459b` | Define a machine-readable catalog for curated quests, levels, boss kills, dungeon clears, zones, and raid bosses. | E2: machine-readable checks.json for all six types. |
| V `7bd97a9eaedb` | Record for each check: source WoW ID, name, faction, class restrictions, minimum logical level cap, expansion/riding requirements, prerequisites, difficulty, and expected effort. | E2/E3: required fields and relationships validated on all rows. |
| V `fefcc6dfcaa6` | Validate quest, boss, map, area, spell, and item IDs against the pinned AzerothCore data. | E2/E4: connected source/DBC check and reward validation, not playability. |
| V `7e0be66766f3` | Decide whether Archipelago slots are strictly one-character-per-slot (recommended initially). | IMPLEMENTATION.md, profiles/slot-data contract: one character per seed/slot. |
| P `6fc8925feb1a` | Persist seed ID, slot ID, connected character GUID, received AP items, completed checks, vouchers, vendor stock, and purchases. | Schema/bridge/native persistence exists; no fresh v2 DB lifecycle/restart/purchase evidence in this audit. |
| P `e464c4889b34` | Make reward application and check reporting idempotent across reconnects, relogs, crashes, and world restarts. | Unit/SQL design exists; whole-process crash/restart and complete v2 effect replay remain unproven. |

### 2. Archipelago checks (~300 initial target)

| Status / ID | Exact checkbox text | Evidence or missing proof |
| --- | --- | --- |
| V `3b9c8109c970` | Curate **150 quest completion** checks; exclude dailies, repeatables, impossible faction/class combinations, and problematic chains. | E2/E3: 150 source-valid curated quests with availability/chain filtering. Script gameplay remains separate. |
| V `5718c153ee29` | Curate **60 exploration** checks; specify whether each represents entering a zone or completing its exploration criteria. | E2/E3: 60 real top-level zones, explicitly confirmed zone entry, not full exploration. |
| P `45200b6116a8` | Curate **48 dungeon boss** checks; count each boss only once per AP slot. | E2 proves 48 identities; per-slot permanent first-kill deduplication needs live credit/restart evidence. |
| V `c0a326ff8bef` | Curate **14 dungeon completion** checks; define unambiguous clear conditions. | E2/E3: 14 normal-map clears with exact curated boss prerequisites and per-run credit contract. |
| P `f412770cb0bd` | Implement **16 level milestones** (5, 10, ..., 80), reconciling early milestones with character start mode. | E2/E10 prove milestone definitions/policy; actual server level-up reporting not freshly exercised. |
| V `cb52dcb99623` | Curate **12 raid boss** checks; keep these optional and non-progression for the level-80 goal. | E2/E6: 12 real raid identities, filler-only excluded placement, no victory dependency. |
| G `0042b3b6d55a` | Ensure starting regions provide roughly **20–35 accessible checks** without needing item unlocks; aim for ~30. | E2/E3/E6 prove nine local, not 20–35. See exact source-backed proposal and physical acceptance limits. |
| P `191074b0d276` | Balance locations across cap bands (10, 20, 30, 40, 50, 60, 70, 80), adjusting for expansion access. | Count distribution is not measured leveling balance. Proposed minimum starter repair further front-loads content. |
| V `6eaf01f7bdba` | Ensure the majority of useful leveling checks are available **before** reaching level 80. | E2: 181/229 Alliance and 186/234 Horde before cap 80. |
| V `946b0c8cec96` | Specify party credit rules, first-kill credit, lockouts, playerbot behavior, and multi-character edge cases. | checks.json credit_policy and CHECK_CURATION.md specify all listed cases; execution not inferred. |
| V `28f40cac65ce` | Support optional raids without placing victory-critical progression exclusively behind them. | E6/E7: real fills restrict raids to filler and reach victory without raid-only progression. |

### 3. Level caps, XP, expansion access & victory

| Status / ID | Exact checkbox text | Evidence or missing proof |
| --- | --- | --- |
| P `2fa8a3d977e8` | Start normal classes at level 1 with a **level cap of 10**. | Manifest and native policy choose level 1/cap10; bind a real new character and exercise XP to cap. |
| V `449e217a8d3a` | Include **7 Progressive Level Cap** items: caps 20, 30, 40, 50, 60, 70, and 80. | E6: seven cap rewards; policy sequence 20 through 80. |
| P `f21a10ba9aa3` | Implement actual server-side XP/level-cap enforcement and preserve cap state across reconnects. | Implementation/policy evidence exists; full live behavior remains unproven by this audit. |
| P `4b4a7d823fa0` | Implement capped **XP banking** at cap (initial proposal: up to 50% of XP needed for the next level); define the exact award/release behavior. | E6/E10 prove exact 50% bank policy; durable native receipt release/relog/rollback needs integration. |
| V `eb4daf797945` | Add **Outland Access** as one progression item. | E6: one Outland Access progression reward. |
| V `fdf352b18911` | Add **Northrend Access** as one progression item. | E6: one Northrend Access progression reward. |
| P `3fb5910642e4` | Restrict all relevant routes (portals, boats, zeppelins, spells, teleports) in accordance with expansion access flags. | Implementation/policy evidence exists; full live behavior remains unproven by this audit. |
| P `00c3544ded0d` | Keep ordinary Azeroth travel accessible without randomized continent gating. | Source permits Azeroth including starter islands; actual ordinary transport routes not exercised. |
| P `8eb09b5ddcfd` | Implement the **level-80 victory event** when the character actually reaches level 80. | Source reports actual level 80, E6 tests logical goal; no real v2 character reached 80 in inspected evidence. |
| V `54c9536a29e0` | Decide whether Northrend Access is a strict victory prerequisite or merely an optional regional unlock; **current chosen goal is level only**, so don't silently add extra victory requirements. | IMPLEMENTATION.md and E6 caps-only-victory test explicitly choose level only. |
| V `36ffbe237228` | Add a separate, valid **Death Knight start mode** (starts at 55, initial cap around 60, mandatory introduction access, adapted cap items/checks) or explicitly exclude Death Knights from v1. | support.json, profiles.json and E3/E6 explicitly exclude class 6. |

### 4. Riding and flying

| Status / ID | Exact checkbox text | Evidence or missing proof |
| --- | --- | --- |
| P `672400c3d2f4` | Add **Apprentice Riding** reward (usual level 20 eligibility, 60% ground mount speed). | Reward/policy source and E10 exist; actual training, mount/flying eligibility and early-arrival/travel paths need live realm/client evidence. |
| P `afbf00090aa9` | Add **Journeyman Riding** reward (usual level 40 eligibility, 100% ground mount speed). | Reward/policy source and E10 exist; actual training, mount/flying eligibility and early-arrival/travel paths need live realm/client evidence. |
| P `0b19ba898285` | Add **Expert Riding** reward (usual level 60 eligibility, flying in Outland). | Reward/policy source and E10 exist; actual training, mount/flying eligibility and early-arrival/travel paths need live realm/client evidence. |
| P `bf4bff9c6393` | Add **Artisan Riding** reward (usual level 70 eligibility, faster flying). | Reward/policy source and E10 exist; actual training, mount/flying eligibility and early-arrival/travel paths need live realm/client evidence. |
| P `88b709ff3379` | Add **Cold Weather Flying** reward (usual level 77 eligibility, Northrend flying). | Reward/policy source and E10 exist; actual training, mount/flying eligibility and early-arrival/travel paths need live realm/client evidence. |
| P `d8f7682b8494` | Grant training/use permissions from AP rewards without requiring full standard training fees. | Reward/policy source and E10 exist; actual training, mount/flying eligibility and early-arrival/travel paths need live realm/client evidence. |
| P `e89c7b926117` | Preserve normal level eligibility for riding tiers unless a future option explicitly overrides it. | Reward/policy source and E10 exist; actual training, mount/flying eligibility and early-arrival/travel paths need live realm/client evidence. |
| V `b1c7b4d7412b` | Add Expert Riding / Cold Weather Flying to access rules **only** for curated flying-dependent checks. | E6 source/rules: flying gates only where curated; four Expert-dependent checks, zero CWF-dependent checks. |
| P `ad1244654053` | Make **ground-accessible** locations completable without mount unlocks. | AP ground rules pass E6; physical completion without mount items needs live route/quest evidence. |
| P `5ac07de75396` | Handle flying and mount edge cases when riding items arrive before prerequisites. | Reward/policy source and E10 exist; actual training, mount/flying eligibility and early-arrival/travel paths need live realm/client evidence. |
| P `310be80d250e` | Verify actual travel and flying restrictions for WotLK 3.3.5a; no ordinary Eastern Kingdoms/Kalimdor flying. | Reward/policy source and E10 exist; actual training, mount/flying eligibility and early-arrival/travel paths need live realm/client evidence. |

### 5. Talent points (hybrid)

| Status / ID | Exact checkbox text | Evidence or missing proof |
| --- | --- | --- |
| P `d76d43372c68` | Preserve the normal WotLK level-80 ceiling of **71 talent points**. | E6/E10 prove talent arithmetic; actual save/relog/respec/dual-spec and delayed receipt reconciliation need realm execution. |
| P `5c5b0afe3072` | Reserve **12** normally earned points for Archipelago (proposed reservation levels: 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70). | E6/E10 prove talent arithmetic; actual save/relog/respec/dual-spec and delayed receipt reconciliation need realm execution. |
| V `c905cf2df934` | Include **12 Talent Point Unlock** items in the item pool. | E6: exactly twelve talent unlocks in actual default pools. |
| P `26255f2e776d` | Restore one reserved point per AP unlock when the character has reached the corresponding eligibility threshold. | E6/E10 prove talent arithmetic; actual save/relog/respec/dual-spec and delayed receipt reconciliation need realm execution. |
| P `aeb945b8c3cf` | Bank early-arriving unlocks and release them later when eligible. | E6/E10 prove talent arithmetic; actual save/relog/respec/dual-spec and delayed receipt reconciliation need realm execution. |
| P `222962632d68` | Do not let early AP rewards bypass intended talent tier/level requirements. | E6/E10 prove talent arithmetic; actual save/relog/respec/dual-spec and delayed receipt reconciliation need realm execution. |
| P `3fd742b2d42f` | Recalculate available/spent points consistently after level-ups, respecs, relogs, and dual-spec switches. | E6/E10 prove talent arithmetic; actual save/relog/respec/dual-spec and delayed receipt reconciliation need realm execution. |
| P `346cfaefdaad` | Verify special behavior for Death Knights and any modified talent progression. | DK excluded by E1/E6, so DK gameplay is not applicable; modified non-DK talent lifecycle still needs integration. |
| V `525408ae2993` | Keep talent points **Useful**, not required progression, unless custom checks explicitly gate on them. | E6: talent items Useful and absent from mandatory access rules. |

### 6. Major class abilities

| Status / ID | Exact checkbox text | Evidence or missing proof |
| --- | --- | --- |
| P `95cd973f3680` | Ensure each class retains a viable baseline rotation, survival tools, and mandatory mechanics. | Implementation/policy evidence exists; full live behavior remains unproven by this audit. |
| V `d962d97fdf51` | Create a class-specific whitelist of **up to 8 independently learned major abilities** per class. | E4/E5: 72 abilities, eight per each supported class; DK explicitly excluded. |
| V `daab4824471d` | Exclude talent-granted abilities from the initial ability shuffle; leave them on the talent trees. | E4/E5: source talent/rank validation and rejected talent candidates. |
| V `fa578525f11c` | Exclude class-defining prerequisites such as essential stances, Druid forms, baseline pet functionality, and mandatory DK intro spells. | E4/E5: source-audited whitelist/baseline prerequisite policy; DK excluded. |
| V `3efd4b046877` | Review Mage options (e.g., Blink, Frost Nova, Counterspell, Ice Block, Polymorph, Slow Fall, Spellsteal, Invisibility). | E4/E5: actual Mage whitelist, trainer/rank/level evidence. |
| V `1af943ac8fad` | Review Warrior options (e.g., Charge, Intercept, Pummel, Shield Wall, Retaliation, Recklessness, Intimidating Shout, Challenging Shout). | E4/E5: actual Warrior whitelist, trainer/rank/level evidence. |
| V `42e1129c6a7a` | Review candidate lists for Paladin, Hunter, Rogue, Priest, Death Knight, Shaman, Warlock, and Druid. | E4/E5: all other supported class lists audited; DK exclusion is explicit. |
| V `8525af4dd96e` | Audit the final list for trainer/rank chains, talent dependencies, class quests, minimum levels, and 3.3.5a compatibility. | E4/E5: live source/DBC reconstruction and rank/trainer/prerequisite validation. |
| P `9fe2d17d5346` | Implement persistent ability-unlock flags; receiving an unlock permits the base spell and normal eligible ranks. | Persistent flags and base/rank guards exist; real trainer/receipt/relog execution not proven. |
| P `a54e75da792b` | Queue early ability rewards until eligible; handle trainers, relogs, specialization changes, and internal spell-learning paths. | Policy and core-hook tests pass; actual specialization/internal learning paths need realm tests. |
| V `a5fa8ea67e66` | Do **not** require shuffled major abilities for normal quest access or level-80 victory in v1. | E6: useful-ability-free access and caps-only victory tests. |
| D `265a8f92f57d` | Consider optional future class-specific challenge checks with explicit spell requirements. | IMPLEMENTATION.md explicitly defers class challenge checks; decision considered, feature not implemented. |

### 7. Randomized equipment vendor

| Status / ID | Exact checkbox text | Evidence or missing proof |
| --- | --- | --- |
| P `d2bcb646256b` | Add an Archipelago Equipment Merchant to every supported major city for both factions. | sql/world.sql contains ten source-backed placements; no current live spawn/walkability verification here. |
| P `e1124fdf853f` | Give each AP slot **one shared personal stock list** visible at every city vendor. | Stock/UI/SQL source exists; current v2 city/private-stock/purchase/full-bag/reconnect behavior needs integrated realm/client tests. |
| P `b071886f58d8` | Generate stock **once per seed/slot**; never reroll it on relog, respec, city change, or daily reset. | Deterministic seed generation and saved-stock source exist; relog/respec/day-reset evidence missing. |
| P `63f3f26747d5` | Allow players to inspect the full inventory from level 1, including unpurchased goods and prices. | Stock/UI/SQL source exists; current v2 city/private-stock/purchase/full-bag/reconnect behavior needs integrated realm/client tests. |
| V `702b5b8e0960` | Target **60 unique equipment entries** per stock list (configurable, suggested 30–120). | E6: real stock selector defaults to 60, unique stock and sizes 30/60/120 tested. |
| V `f4797d86069c` | Choose equipment based on the character's class and all viable specializations; do not force a single current spec. | E4/E5/E6: source-backed class_roles, viable-role candidate selection, all-class facet tests. |
| V `783521e2a853` | Exclude all legendary equipment from vendor stock. | E5/E6: quality-5 identities rejected from generated stock. |
| V `67eb33dae22a` | Include normal weapons, armor, rings, trinkets, and set items across Classic, TBC, and WotLK pools. | E4/E5/E6: real candidate facets cover equipment types, set pieces and three eras. |
| P `eaa87e6ad580` | Prefer a native vendor-like UI, but support categorized gossip menus if per-character vendor stock is impractical. | Gossip implementation and explicit MVP decision exist; actual player UI interaction not verified. |
| P `8f4755033e95` | Limit purchases to **one copy per stock entry** by default. | Stock/UI/SQL source exists; current v2 city/private-stock/purchase/full-bag/reconnect behavior needs integrated realm/client tests. |
| P `4cb8029063a6` | Display remaining voucher balance and total remaining shop cost. | Stock/UI/SQL source exists; current v2 city/private-stock/purchase/full-bag/reconnect behavior needs integrated realm/client tests. |
| V `11153b495a06` | Select **3 featured class-compatible sets** per stock list by default (configurable 1–4). | E6: default three sets, configurable set count and stock overflow cases. |
| V `c6ade71baeaf` | For each piece of a featured set, independently include it with **80% probability** (configurable). | E6/E7: independent seeded piece rolls at configurable 80% default. |
| V `f98b65ce73db` | Do **not** guarantee full sets, but make them substantially likelier than under uniform item-by-item sampling. | E6/E7: rolled featured membership excludes unrolled pieces; no full-set guarantee. |
| V `a2ca923dbd5f` | Confirm each featured set's actual piece count; e.g., for an 8-piece set, full inclusion probability is `0.8^8 ≈ 16.8%`. | E4/E5: actual DB/DBC set membership; eight-piece theoretical probability is 0.8**8. |
| V `f090ccb43ca2` | Reserve space for selected set pieces and fill remaining slots with other curated equipment. | E6: featured reservations before ordinary stock fill. |
| V `2f9d4e0e47e6` | Handle inventory-cap overflow if featured-set rolls produce too many items. | E6: stock 30/four featured/100% roll overflow handling tested. |
| V `612e7139f77a` | Deduplicate set pieces and other stock entries. | E6: all tested stocks contain unique IDs, featured/filler membership checked. |
| V `02c625deb16f` | Shuffle/sort the shop display without altering deterministic seed stock. | shop.py and E6 deterministic/personal stock reproduction; display ordering is persisted stock order. |
| V `a9b948cadb23` | Ensure meaningful representation of different equipment slots, expansions, and class specs. | E4/E5/E6: all available era/slot/quality and class-relevant role facets checked, not a gear optimizer. |
| P `fc43bdac69c8` | Create a single persistent **Equipment Voucher** balance per AP slot. | Stock/UI/SQL source exists; current v2 city/private-stock/purchase/full-bag/reconnect behavior needs integrated realm/client tests. |
| V `8648ba9890a7` | Define Archipelago rewards: **45 × Voucher +1**, **28 × Voucher +3**, **15 × Voucher +5**. | E6: fixed voucher counts 45/28/15. |
| V `8598a72238ba` | Verify total voucher supply: **204 vouchers across 88 AP items**. | E6: actual pool has 204 vouchers in 88 items. |
| V `9311a8988d9a` | Implement proposed costs: Uncommon 1; Rare 2; Classic raid set piece 3; TBC raid set piece 4; WotLK raid set piece 5; high-end epic weapon 6–8. | E4/E5: source-derived prices checked for quality/era/weapons. |
| P `4822b95e3a5d` | Ensure shop purchase is atomic: check balance, debit once, mark sold, deliver item, and persist all results transactionally. | Stock/UI/SQL source exists; current v2 city/private-stock/purchase/full-bag/reconnect behavior needs integrated realm/client tests. |
| P `76d4f4b471f8` | Handle full bags and disconnects without losing vouchers or duplicating purchases. | Stock/UI/SQL source exists; current v2 city/private-stock/purchase/full-bag/reconnect behavior needs integrated realm/client tests. |
| V `47fd0741b562` | Test whether **204 total vouchers** lets the player buy most (but not necessarily all) of a typical 60-item inventory. | E7: mean 54.349/60 cheapest-first; stock costs exceed 204 in all 2,000 samples. |
| P `c0d3873f55fd` | Tune prices/stock generation based on sample seeds; favor meaningful early purchases over permanently unaffordable gear. | Role/stock tuning and sample evidence exist; meaningful early purchase timing still needs play. |
| V `24dcf2665b3b` | Keep voucher rewards **Useful**, not required progression for level-80 victory. | E6: voucher Useful classification, no mandatory voucher rules. |
| P `eb73c0d4dbfa` | Preserve original item stats, procs, set bonuses, visuals, and item identity. | E10 proves bounded policy only; integrated v2 issuance/equipment/client/transfer and crash cases remain unproven. |
| P `e7a730ce2291` | Bypass **required character level** only for individually authorized Archipelago-awarded item instances. | E10 proves bounded policy only; integrated v2 issuance/equipment/client/transfer and crash cases remain unproven. |
| P `e7aafa1d43f8` | Preserve class, armor-type, weapon-skill/proficiency, and other non-level compatibility rules. | E10 proves bounded policy only; integrated v2 issuance/equipment/client/transfer and crash cases remain unproven. |
| P `340e17cfcd50` | Check whether other item/equipment validation paths and unmodified 3.3.5a client behavior need special treatment. | E10 proves bounded policy only; integrated v2 issuance/equipment/client/transfer and crash cases remain unproven. |
| P `68866a5e63d9` | Bind AP equipment to the receiving character/slot; block trade, mail transfers, auction house, and other transfer exploits. | E10 proves bounded policy only; integrated v2 issuance/equipment/client/transfer and crash cases remain unproven. |
| P `20ab8fd19997` | Prevent buying one authorized item from unlocking unrestricted use of ordinary drops with the same item ID. | E10 proves bounded policy only; integrated v2 issuance/equipment/client/transfer and crash cases remain unproven. |
| P `d7c303b57bcd` | Test low-level characters using high-end procs, stats, sockets, enchants, and set bonuses. | E10 proves bounded policy only; integrated v2 issuance/equipment/client/transfer and crash cases remain unproven. |
| P `91ca518f9d9e` | Compare implementation approaches: core-level instance-specific equipment exemption vs. alternate item templates; prototype the former first. | Instance-specific approach is implemented and policy-tested; no complete comparison/client prototype evidence established. |

### 8. Direct legendary rewards

| Status / ID | Exact checkbox text | Evidence or missing proof |
| --- | --- | --- |
| V `99428b8a8e6f` | Place **2 directly awarded named legendary items** per normal seed; make count configurable. | E6: default two named legends; configurable 0/1/2 tested and impossible counts rejected. |
| V `d6fff56e213e` | Pick items from a curated class/weapon-compatible whitelist (e.g., Thunderfury, Sulfuras, Val'anyr, Shadowmourne where compatible). | E4/E5/E6: deterministic selection from real class/proficiency-compatible quality-5 catalog. |
| V `a74806c2a919` | Select actual legendary identities deterministically at seed generation, visible in spoiler logs. | E6: actual generated spoiler includes each selected item identity and named AP reward. |
| P `6c3714f1ec43` | Deliver legendary rewards directly upon receipt of the AP item, without visiting the vendor. | E10 proves bounded policy only; integrated v2 issuance/equipment/client/transfer and crash cases remain unproven. |
| P `b3c20f33b5d0` | Apply the same instance-specific level exemption and binding/trade restrictions as vendor gear. | E10 proves bounded policy only; integrated v2 issuance/equipment/client/transfer and crash cases remain unproven. |
| P `f2573b2aa8f8` | Queue delivery safely for offline characters or full inventories. | E10 proves bounded policy only; integrated v2 issuance/equipment/client/transfer and crash cases remain unproven. |
| P `e842f15e1726` | Prevent duplicate application after reconnects, AP retransmission, or crashes. | E10 proves bounded policy only; integrated v2 issuance/equipment/client/transfer and crash cases remain unproven. |
| P `9dbf810f31ef` | Test low-level legendary procs and unusual class/equipment restrictions. | E10 proves bounded policy only; integrated v2 issuance/equipment/client/transfer and crash cases remain unproven. |
| V `4190d213ce68` | Keep direct legendaries **Useful**, not prerequisites for any ordinary checks or victory. | E6: legendary Useful classification and no mandatory legendary rules. |

### 9. Seed item-pool composition (current proposed 300 items)

| Status / ID | Exact checkbox text | Evidence or missing proof |
| --- | --- | --- |
| V `110d251e2489` | Generate exactly one Archipelago item for each ordinary item-bearing location after accounting for events/prefill. | E6: actual pool/location cardinality, addressless victory and ordinary fixed-prefill tests. |
| V `18b0e45376de` | Include **7** Progressive Level Cap items — Progression. | E6: actual fixed count seven and Progression classification. |
| V `c06d196ceabc` | Include **1** Outland Access and **1** Northrend Access — Progression. | E6: actual fixed count one each and Progression classification. |
| V `36c5dda51005` | Include **1** Expert Riding and **1** Cold Weather Flying — Progression if required by selected flight-dependent checks. | E6: riding classification varies with selected check gates, not blindly with base metadata. |
| V `74be0caffde2` | Include **3** other riding unlocks — Useful. | E6: three other riding rewards remain Useful. |
| V `cfb6a9efc407` | Include **12** Talent Point Unlock items — Useful. | E6: twelve talent unlocks, Useful. |
| V `8990b21ec260` | Include **8** class-specific Major Ability items — Useful (adjust count if a class has fewer safe candidates). | E4/E6: eight selected class abilities, Useful, for all nine supported classes. |
| V `a83df706c84f` | Include **4** Bag Upgrade items — Useful. | E6: four bag upgrades, Useful. |
| V `e0789e1cac35` | Include **45** Voucher +1 items — Useful. | E6: 45 Voucher +1, Useful. |
| V `5a95659a189d` | Include **28** Voucher +3 items — Useful. | E6: 28 Voucher +3, Useful. |
| V `cbd463930449` | Include **15** Voucher +5 items — Useful. | E6: 15 Voucher +5, Useful. |
| V `7a5dc34b3109` | Include **2** direct named Legendary items — Useful. | E6: default two compatible named legends, Useful. |
| G `8f78051f7815` | Include **100** Gold Cache items — Filler. | E8 proves actual defaults 59/62 Gold, not 100; base_count alone does not fulfill actual-seed wording. |
| G `3808edfd0db9` | Include **72** Consumable Cache items — Filler. | E8 proves actual defaults 42/44 Consumables, not 72; parent must resolve base-versus-slot interpretation. |
| V `a65e97dbc087` | **Audit pool arithmetic:** above counts sum to **300** (11 progression + 117 useful + 172 filler). | E6/E8: hypothetical base sums to 300. Actual default totals/classification differ as explained above; this verifies arithmetic, not a 300-location supported seed. |
| V `1d7492a28814` | Recompute filler counts automatically when check count, class ability count, settings, excluded locations, or prefill changes. | E6/E8: capacity-based filler recalculation, all category masks, legendary changes, prefill and exclusions tested; exact ratio lacks committed regression asserts. |
| P `70cb9cbc6c49` | Scale gold/consumable rewards sensibly to the recipient's current character progression. | E10 executes gold/potion level-boundary policy; live delivery/scaling not exercised. |
| V `0c004e2b751a` | Decide if raid locations use explicit filler-only placement restrictions or Archipelago excluded-location rules. | IMPLEMENTATION.md, __init__.py and E6 choose both EXCLUDED and explicit filler-only item_rule. |

### 10. APWorld logic and generation

| Status / ID | Exact checkbox text | Evidence or missing proof |
| --- | --- | --- |
| V `04e197726c7b` | Model region/access rules primarily from level cap, expansion access, and explicitly flight-gated checks. | E6: real cap/expansion/explicit-riding access-rule tests. |
| V `048a4510a813` | Keep class abilities, talent points, vouchers, equipment, and legendaries out of mandatory victory logic. | E6: no Useful reward gates ordinary checks or victory. |
| V `bb31e44b740c` | Ensure raids never hold items required for level-80 victory. | E6/E7: actual raid placements are filler-only. |
| V `d38dc37e0e1b` | Ensure each cap upgrade can be reached without needing that same cap upgrade. | E6/E7: empty-state actual fill walks and cap-selflock assertions pass. |
| G `39eac8b86ad9` | Encode starting regions per faction/class and any critical quest chains or travel links. | Profiles and ancestor inheritance exist, but physical starter/travel links are not encoded as regions; cap tuples and nine local checks do not fulfill the full wording. |
| P `80d42f59fb02` | Use conservative logical level thresholds; physically entering a zone does not mean its checks are completable. | E2 rejects caps below source levels and uses rounded conservative thresholds; real combat and route difficulty unmeasured. |
| V `c974d425ca91` | Support configurable `progression_balancing` and accessibility, and test how excluded raid locations interact with those settings. | E6: accessibility full/minimal, balancing 99 and exclusion tests pass. |
| V `4fcf568f6969` | Make item generation deterministic for a given seed and settings (including vendor stock and selected legendaries). | E6/E7: repeated seed/slot stock and complete slot-data determinism checked. |
| V `7e7f3b353783` | Validate all supported combinations of race, class, faction, and optional check categories. | E6: all 52 legal profiles times 64 category masks exercised; undersized masks explicitly reject. |
| V `ec974d180eaa` | Provide location and item names that are meaningful in AP clients and spoiler logs. | E2/E4/E6: source-backed descriptive names and actual named spoiler assertions. |

### 11. AzerothCore bridge, persistence & UX

| Status / ID | Exact checkbox text | Evidence or missing proof |
| --- | --- | --- |
| P `ccd4f7816717` | Implement a reliable bridge from the AzerothCore module to an Archipelago client/protocol connection. | Manifest tests and bridge source exist; no fresh actual v2 realm-to-real-AP reconnect session. |
| P `82b94c14a99e` | Send checks only after confirmed quest turn-in, milestone, exploration, boss defeat, dungeon clear, or raid defeat. | Native event hooks inspected; all real check types/parties/resets need live invocation evidence. |
| P `ed8fde3a4bd4` | Persist check sends locally until acknowledged; deduplicate after reconnection. | Outbox/ack source exists; no fresh v2 persistent reconnect/ack/rollback test in this read-only audit. |
| P `e91b0699ec74` | Persist received items with unique AP indices; apply exactly once. | Unique-index/effect SQL and policy exist; real v2 exactly-once application/crash recovery not demonstrated. |
| P `ed96d54aabb3` | Surface item receipts, cap upgrades, abilities, vouchers, and legendaries clearly in-game. | ITEM/STATE/SHOP handling exists; historical client popup only proves legacy potion receipt. |
| P `1e939564eab4` | Add simple status commands/UI showing AP connection, slot, level cap, riding unlocks, available vouchers, and remaining checks. | Merchant status command reads requested fields; no current in-game output checked. |
| P `45c1b4a9b983` | Safely handle absent bridge, unavailable AP server, server restart, logout, and character deletion. | Lifecycle source/fail-stop design exists; absence/restart/deletion integration still needed. |
| P `59bd867adafb` | Restrict privileged APIs and authenticate bridge communications. | Manifest/SQL/config boundary tests exist; AP connection/DB trust model and deployment security not fully verified. |

### 12. Testing & release criteria

| Status / ID | Exact checkbox text | Evidence or missing proof |
| --- | --- | --- |
| V `83b136ca8ca6` | Unit-test item-pool counts and classification with all optional check categories. | E6: all category/profile combinations and item classifications tested. |
| V `02889efb84fe` | Unit-test level cap increments, XP banking, talent reservations, and delayed reward eligibility. | E6/E10: cap sequence, exact banking/release, every talent reservation/unlock threshold, delayed ability/riding eligibility. |
| V `c08a9a1f1e68` | Generate thousands of seeds and verify logical reachability of the level-80 victory event. | E7: fresh 2,000 actual restrictive fills reach the logical victory event. |
| V `6ec04608bfd2` | Verify raids and legendary/voucher rewards never accidentally become mandatory. | E6/E7: useful-free access, caps-only victory and filler-only raid placement. |
| P `b4329d2b6095` | Test both factions and every supported class, including exceptional DK handling. | E6/E7 cover both factions/all 52 profiles logically and reject DK. No equivalent live all-class matrix. |
| V `3f85243a4653` | Simulate shop inventory generation for thousands of seeds; measure set-piece and full-set distributions. | E7: fresh 2,000 generated stocks with piece/full-set/overflow statistics. |
| V `8d74169e2da6` | Verify 80% independent set-piece rolls produce approximately 16.8% complete 8-piece featured sets before stock-cap effects. | E7: 79.866% piece rolls and 16.056% full-eight rolls, versus theoretical 80% and 16.777%. |
| P `0db7a1e3b8ff` | Test voucher-price economy for realistic early/mid/late check progression. | E7 measures check-quarter income, not realistic time/level/route progression; needs playthrough. |
| P `26233758fa48` | Test simultaneous purchases, crashes during purchases, full bags, rollback, and reconnect idempotency. | Historical legacy fault output exists; complete v2 purchase concurrency/process-fault/client recovery is unproven. |
| P `b62cdf75dbc4` | Test equipping high-level raid gear and directly awarded legendaries at low levels without client errors or server-side exploits. | No stock build-12340 low-level raid/legendary equip/exploit run inspected. |
| P `0bc6e0c750ba` | Test normal non-AP equipment still obeys all original item requirements. | Core validator policy tests preserve ordinary restrictions; actual ordinary-copy versus authorized-copy client test missing. |
| P `06433b30b57f` | Test every check type on a live 3.3.5a client, including parties and playerbots. | No all-six-type live client/party/playerbot report inspected. |
| P `08e7a4a3e3de` | Run a complete solo or playerbot-assisted level-1-to-80 playthrough. | No complete level-1-to-80 run evidence inspected. |
| P `b5641a8bab84` | Run a real multiworld session with at least one other Archipelago game. | No real cross-game multiworld evidence inspected. |

### 13. Open decisions / explicit follow-ups

| Status / ID | Exact checkbox text | Evidence or missing proof |
| --- | --- | --- |
| V `840e0c6b4f80` | Finalize raid boss list and whether raid locations should be filler-only or simply non-required by generation logic. | checks.json and E2/E6: raid identities fixed and filler-only decision enforced in generation. |
| G `b73f2b435ce3` | Finalize the exact 150 quest / 60 zone / 48 boss / 14 dungeon / 16 level / 12 raid location catalogs. | Exact current counts validate, but starter requirement forces a content decision; cannot finalize conflicting catalog unchanged. |
| P `7774a56f94ad` | Decide whether **level only** victory can occur outside Northrend without changing intended difficulty. | Level-only/outside-Northrend decision is explicit; unchanged intended difficulty is not measured. |
| V `b3108764257f` | Finalize Death Knight support (adapted progression or excluded in first release). | support.json and E3/E6: DK exclusion finalized and illegal profiles rejected. |
| V `2a2ec89484e5` | Audit the final per-class major-ability lists; the earlier candidates are not yet validated. | E4/E5: current per-class source lists/ranks audited, no reliance on early candidate summary. |
| V `49587e34ca76` | Confirm whether level restrictions are waived only for gear, **not for riding and ability eligibility** (current recommendation). | IMPLEMENTATION.md and policy source/E10: only authorized gear waives level; riding/abilities retain eligibility. Decision proven, live behavior separate. |
| V `55c1d0ad5e9a` | Decide if native vendor UI is essential, or categorized gossip inventory is acceptable for MVP. | IMPLEMENTATION.md chooses categorized gossip as acceptable MVP. |
| V `111727bf9f60` | Decide whether inventory entries are visible to other players sharing a server but using separate AP slots (recommended: never). | IMPLEMENTATION.md and merchant source specify private per-binding inventory, never cross-player stock. Decision proven, live privacy separate. |
| V `7837c5703cb1` | Confirm stock 60, featured sets 3, piece inclusion 80%, legendary count 2, and voucher pricing after simulations. | E6/E7: 60/3/80%/2 defaults and pricing tested in 2,000 seeds. |
| V `f5d81fe3eed2` | Define treatment of auction-house and normal high-level item acquisition relative to unrestricted AP-awarded equipment. | IMPLEMENTATION.md/runtime policy: only authorized instance GUIDs waive level; ordinary acquired gear does not. Actual transfer/equip tests remain separate. |
| D `4cb52e525f64` | Determine whether to introduce optional special class challenges and equipment/riding progression beyond the v1 logic. | IMPLEMENTATION.md explicitly defers special challenges/additional v1 gates; not an implemented expansion. |

### 14. Suggested implementation order

| Status / ID | Exact checkbox text | Evidence or missing proof |
| --- | --- | --- |
| P `cb9c4a6cfcbf` | **M1 — Connectivity:** APWorld skeleton, slot binding, server-side bridge, receipt/check persistence. | AP skeleton and persistence code exist; legacy potion connectivity is not complete v2 connectivity evidence. |
| P `f68924af5743` | **M2 — Progression vertical slice:** 10–20 curated checks, level caps 10→20→30, level milestone reporting, victory simulation. | E6/E10 prove generation/policy slice, not actual milestone/XP vertical-slice gameplay. |
| P `311033b08616` | **M3 — Class systems:** expansion access, riding flags, talent reservations, and one tested class's major abilities. | Unit policies exist; expansion travel, riding/talents and one class ability need an integrated realm run. |
| P `864b37cb0b5f` | **M4 — Shop vertical slice:** one city merchant, deterministic stock, vouchers, purchase persistence, unrestricted AP-only equipment. | Stock/vouchers/UI/issuance code exists; live one-city atomic purchase and low-level equip missing. |
| P `454352441b77` | **M5 — Equipment depth:** featured sets, 60-entry catalog, full class compatibility, other city vendors, direct legendaries. | E4–E7 prove catalog/stock/legendary generation; other-city and direct reward runtime missing. |
| P `87fb6fd1ed5b` | **M6 — Full content:** ~300 checks, all supported classes/factions, dungeons, raids, balance testing. | 300 definitions and logical profile fills exist; local content and physical dungeon/raid/balance evidence missing. |
| P `b61ede21ebe8` | **M7 — Release hardening:** exploit protection, crash recovery, reconnect behavior, multiworld testing, documentation and setup scripts. | Crash/exploit/reconnect/client/playthrough/cross-game release gates remain open. |

## Snapshot integrity

Ledger: 187 anchors; 90 V, 90 P, 5 G, 2 D. These are audit classifications, not applied checkmarks.

| Input | SHA-256 |
| --- | --- |
| `TODO.md` | `f0438c88bc42159ed8c0d752856aa3f761fcd81ca25ae26fd5fe667b5f061323` |
| `docs/requirements-status.json` | `ca6db5722d1bb658a30f26436ee0585b0399b35af3745f6dbfe7663f0e2b89dc` |
| `support.json` | `5175c55e1d057f892d133076892ab33972baaee5da182512eb6b0d2ff74cc1ef` |
| `apworld/wowpilago/data/checks.json` | `8eceab13eefb8a11d5a0c8fbdd5fbd602e80745e4acc6e26871cc1865559c492` |
| `apworld/wowpilago/data/profiles.json` | `0e84eede2fb7c11df14afed6cad8f6b6f95d30f894d31b8d5dd18684fb315d27` |

No live realm/client mutations, deployment/build, full playthrough or cross-game session were attempted. The proposed starter content and donor allocation are not implemented or physically certified.
