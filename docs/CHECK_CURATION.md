# Check curation v2

```sh
WOWPILAGO_DB_PASSWORD=test-only .venv/bin/python tools/validate_checks.py --report docs/check-validation.json
WOWPILAGO_DB_PASSWORD=test-only .venv/bin/python -m unittest discover -s tests -p test_check_catalog.py -v
```

`--generate` rebuilds `apworld/wowpilago/data/checks.json` and `profiles.json` only after connected validation passes. `--offline` checks structure and profile coverage, not source identities. Review source changes before regenerating against another snapshot. The password variable is `WOWPILAGO_DB_PASSWORD`.

## Scope and identity

Exactly 300 definitions exist before profile filtering: 150 quests, 60 zone entries, 48 dungeon bosses, 14 dungeon completions, 16 level milestones and 12 raid bosses. Schema version remains 2. AP IDs are each kind's base plus its real WoW source ID, never an array index. Quest names include their IDs because titles repeat.

The opening repair retains all 48 existing starter quests and adds 88 local quests, eleven per distinct starter zone. It retains fourteen later quests, one faction-compatible quest per faction per later cap band. The other 88 later quests are permanently reserved in `apworld/wowpilago/data/retired-checks.json`. The validator rejects reuse of their keys or AP IDs. All 212 surviving definitions retain their AP IDs. Each new quest AP ID is `919500000 + quest_template.ID`.

This deliberately spends 136 of 150 quests on startup. It meets the lower bound of 20 local opening checks, not the aspiration of roughly 30. It does not establish balanced leveling coverage. See [Opening curation](OPENING_CURATION.md) for the allocation, exact source queries, special objectives and catalog-hash impact.

Exploration remains confirmed top-level zone entry, not full exploration, exploration XP or subarea checks. Milestones require actual character level. No check type or realm history was changed.

## Pinned evidence

Both generated JSON files contain the same provenance. Connected validation compares it with a fresh read-only snapshot.

| Evidence | Source |
| --- | --- |
| AzerothCore checkout | `9fb906bb7296212ff42fc95ff73a92aaf8554f0d` |
| World database | `ACDB 335.17-dev`, cache ID 17; reported core revision `unknown` |
| Client target | WoW 3.3.5a, build 12340 |
| Database | `acore_world` on localhost port 13317 |
| DBCs | `../wow-test/data/client-data/dbc` |

The tool uses SELECTs inside a consistent read-only transaction, then rolls back. It does not read or change accounts, characters, bindings or check history. `docs/check-validation.json` records exact SELECTs, sorted-projection hashes, DBC/source-file hashes, every profile's coverage, and physical opening witnesses. Hashes cover the projections actually used, not whole database dumps. Source hashes include `PlayerQuest.cpp`, `QuestDef.cpp`, `QuestDef.h`, DBC structures, credit paths and the selected summon/transform scripts. Spell.dbc now also has a pinned hash because the objective audit checks item-use crafting.

A checkout revision does not establish the running worldserver binary's revision. A DBC header does not establish a client handshake. No credentials appear in generated data.

## Quest availability and locality

Faction follows `AllowableRaces`, then actual NPC starter hostility from FactionTemplate.dbc when the race mask does not settle it. Class and narrower race masks remain intact. There are 75 Alliance, 74 Horde and one neutral quest definition. Profiles come from real `playercreateinfo` rows and ChrRaces.dbc. Death Knights remain excluded.

Validation rejects repeatables, daily/weekly flags, event/pooled availability, negative or missing chain parents, exclusive/breadcrumb chains, unmodeled accept/show conditions, reputation/skill gates, timed quests and missing NPC starters/enders. Both `PrevQuestID` and incoming `NextQuestID` references define prerequisites. Filtering removes descendants of filtered parents. Missing parents, cycles and parents above a child's cap fail validation. Quest/minimum levels round upward to the next cap band.

`StartItem` is the item given when accepting a quest, not an item-start flag. The validator requires its template and a positive `ProvidedItemCount`, checks a finite unique-item limit, and rejects a count with no source item. Actual item-start evidence is `item_template.startquest`, which remains unsupported. Missing local item acquisition evidence also fails the opening audit. A source-item correction is not permission to waive external item gates.

Quest `area_id` and `source_area_id` preserve actual `QuestSortID`. `starting_zone` resolves the full AreaTable ancestry. Expansion uses that ancestor as well. Sunstrider Isle 3431 resolves to Eversong Woods 3430; Ammen Vale 3526 resolves to Azuremyst Isle 3524. Both are Azeroth even though their physical map is 530.

All 136 opening quests have normal-spawn NPC starters and enders inside their physical starting zone's WorldMapArea rectangle. Explicit objective targets and item sources also have local witnesses. Item drops use creature templates at level 10 or below; direct targets allow the conservative cap-plus-three margin. The highest direct target is level-12 Kyle, a feeding objective, not a required kill. Crafted Broken Tools use a local pick source, DBC creation spell and local forge. These are source witnesses, not a route planner or script interpreter. Implicit scripted requirements are inspected separately in the opening document.

Profile positions and orientation must still match playercreateinfo, source map and DBC zone bounds. Rectangles can overlap neighboring cities and do not prove terrain, collision, path safety or travel time. The selected witnesses were inspected; a rectangle match alone is not full gameplay evidence.

## Coverage

Every one of the 52 legal profiles has 20 local cap-10 Azeroth/no-riding checks after prerequisite closure: 17 quests, one zone entry and milestones 5 and 10. All nine classes retain that coverage without AP reward flags. The validator enforces 20–35 on this LOCAL metric.

Faction-wide early availability is a separate metric with no artificial 35 upper bound. It ranges from 66 to 79 because masks and inherited quest restrictions differ. It includes distant friendly starting regions and cities. Those checks are not counted as local.

The report gives all 52 profiles separately. Filtered totals range from 205 to 218, not 300. Before-cap-80 counts range from 160 to 173 and remain a majority. APWorld must recompute filler from the selected profile and categories. APWorld opening assertions and generated native/addon catalogs are separate consumers.

## Dungeon, raid and credit contracts

Dungeon, boss, exploration, level and raid definitions are unchanged. All fourteen dungeon clears use normal difficulty and require exactly every curated boss in that map, credited to the bound character in one instance/lockout. Partial runs cannot combine. Individual boss checks remain permanent.

Wailing Caverns means the four Fanglords and Kresh, not Naralex/Mutanus or every optional boss. Mechanar means its three named main bosses and still requires Expert Riding for its aerial entrance. Ramparts requires both Vazruden and Nazan. Wailing Caverns uses cap 30, TBC instances cap 70, and Northrend instances cap 80. Normal entry templates are checked for level, item and quest gates. Critical boss sequence prerequisites remain explicit.

Normal DB spawns support ordinary boss identities. Vazruden, Nazan and Ragnaros use checked map-specific summons and enum definitions. Svala 26668 uses a checked transform from normally spawned 29281. The native scripts still control encounter phases and doors.

Credit policy remains one bound character per seed/slot, deduplicated forever by seed/slot/check key. Quests require rewarded turn-in; levels require actual levels; exploration requires zone entry. Bosses use real core tap/group kill-credit semantics, not map-wide or last-hit credit. Playerbots grant no synthetic credit. Clears additionally need same-instance/lockout state that survives reconnects without combining resets.

The twelve raid checks remain filler-only and nonrequired at cap 80: nine Molten Core bosses including Ragnaros, Onyxia, Gruul and Magtheridon. Ragnaros retains the other eight curated MC prerequisites; Majordomo's original sequence still applies. No raid may hold required progression.

## Verification limits

Connected validation reports zero invalid rows. All 14 catalog tests pass with the five DB-dependent tests actually executed. Tests cover local profile counts, independent faction-wide counts, unchanged later cap-band representation, source-item/count rejection, genuine item starts, external item gates, source-area ancestry, absent physical starters, retired identities, regeneration and the existing identity/chain/dungeon/raid rejection cases.

No live client quest completion, combat route, party/playerbot session, full leveling playthrough or multiworld test was performed. This is local source-backed opening coverage and structural validation, not a claim of complete leveling balance or live gameplay certification.
