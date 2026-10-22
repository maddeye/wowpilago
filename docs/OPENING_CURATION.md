# Local opening repair

The count-preserving quest-only repair is implemented. Every legal non-DK profile has **20 local opening checks** without AP unlocks. This is the minimum repair under the approved allocation, not a roughly-30-check opening or a balanced leveling catalog.

## Allocation

Retain the existing six starter quests per zone. Add these eleven per zone, with real quest IDs and `919500000 + questID` AP IDs:

| Physical starting zone | Added quest IDs |
| --- | --- |
| Dun Morogh 1 | 179, 170, 183, 3361, 182, 218, 318, 319, 233, 234, 320 |
| Elwynn Forest 12 | 783, 7, 5261, 33, 15, 18, 3903, 3904, 6, 21, 2158 |
| Durotar 14 | 4641, 788, 789, 4402, 792, 790, 804, 817, 808, 834, 826 |
| Tirisfal Glades 85 | 363, 364, 376, 3901, 3902, 380, 381, 382, 6395, 375, 426 |
| Teldrassil 141 | 458, 456, 457, 459, 916, 4495, 3519, 3521, 917, 920, 476 |
| Mulgore 215 | 747, 752, 750, 753, 755, 757, 780, 3376, 766, 833, 754 |
| Eversong Woods 3430 | 8325, 8326, 8327, 8346, 8334, 8336, 8345, 8335, 8347, 9704, 9352 |
| Azuremyst Isle 3524 | 9279, 9280, 10302, 9293, 9799, 9305, 9314, 9463, 9512, 9473, 9505 |

Dwarf/Gnome share Dun Morogh; Orc/Troll share Durotar. Eight distinct zones each needed eleven additions, so the repair adds 88 quests and retires 88 later quests. Seventeen local quests plus one zone entry plus actual-level milestones 5 and 10 give twenty. All selected early quest chains remain closed after profile filtering.

Retained later quests are exactly `12, 56, 216, 568, 844, 1387, 2862, 4124, 5092, 9443, 9770, 9777, 11155, 11167`. There is a faction-compatible quest for each faction at each later cap band. Retirement records include all 88 old keys, source IDs, AP IDs and titles in `apworld/wowpilago/data/retired-checks.json`. They are permanent reservations, not a migration plan.

Global totals remain 150 quests / 60 zone entries / 48 bosses / 14 clears / 16 levels / 12 raids. Cap-band totals across all kinds are:

| Cap | Definitions |
| --- | ---: |
| 10 | 154 |
| 20 | 12 |
| 30 | 16 |
| 40 | 11 |
| 50 | 8 |
| 60 | 10 |
| 70 | 43 |
| 80 | 46 |

136/150 quests now weight startup. Preserving a token quest at every later faction/cap band is not evidence of even pacing. Reaching roughly 30 local checks everywhere would require changing the approved allocation or semantics, not counting distant faction travel as local.

## Final profile counts

All classes within each listed race have the same counts. `docs/check-validation.json` contains the individual 52 rows. Local early is always 17 quests + entry + two milestones.

| Race | Class IDs | Profiles | Filtered total | Local early | Faction-wide early | Before 80 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Human 1 | 1,2,4,5,8,9 | 6 | 213 | 20 | 74 | 168 |
| Orc 2 | 1,3,4,7,9 | 5 | 205 | 20 | 66 | 160 |
| Dwarf 3 | 1,2,3,4,5 | 5 | 213 | 20 | 74 | 168 |
| Night Elf 4 | 1,3,4,5,11 | 5 | 213 | 20 | 74 | 168 |
| Undead 5 | 1,4,5,8,9 | 5 | 206 | 20 | 67 | 161 |
| Tauren 6 | 1,3,7,11 | 4 | 206 | 20 | 67 | 161 |
| Gnome 7 | 1,4,8,9 | 4 | 213 | 20 | 74 | 168 |
| Troll 8 | 1,3,4,5,7,8 | 6 | 205 | 20 | 66 | 160 |
| Blood Elf 10 | 2,3,4,5,8,9 | 6 | 215 | 20 | 76 | 170 |
| Draenei 11 | 1,2,3,5,7,8 | 6 | 218 | 20 | 79 | 173 |

The 20–35 assertion applies only to LOCAL coverage. Faction-wide early count has no artificial upper bound. Counts differ from the temporary proposal's faction-wide totals because the final catalog retires the actual donors and preserves source race restrictions.

## Reproducible source audit

```sh
WOWPILAGO_DB_PASSWORD=test-only .venv/bin/python tools/validate_checks.py --generate --report docs/check-validation.json
WOWPILAGO_DB_PASSWORD=test-only .venv/bin/python -m unittest discover -s tests -p test_check_catalog.py -v
```

Connected validation has zero invalid rows; the actual 14 tests, including all five live-source tests, pass. No DB test was skipped. Read source data from `acore_world` at localhost:13317 using root and the environment password. DBCs are `../wow-test/data/client-data/dbc`. Only read-only source inspection was used; no realm mutation, binding conversion or history rewrite occurred.

The report's `source_queries` contains the exact SELECT text, including all IN-list IDs. `provenance.table_sha256` pins each sorted projection. `opening_evidence` records one concrete local starter and ender for every one of 136 quests, plus explicit objective/item witnesses. Every selected quest/minimum level is at most 10. Loot witnesses use local creatures with template max level at most 10. Direct objective templates are at most 12; the level-12 case is Kyle's feeding event. No objective was treated as local merely because QuestSortID says so.

WorldMapArea membership uses the physical map, x and y rectangle. Realm `creature.zoneId` and `areaId` were zero in the proposal audit, so they are not used as evidence. AreaTable ancestry determines logical starter attribution and mixed-map expansion, while `area_id` and `source_area_id` keep actual source values. In particular 3431→3430 and 3526→3524 stay Azeroth on map 530.

Core source semantics are `QuestDef.h:GetSrcItemId/GetSrcItemCount`, `QuestDef.cpp:LoadQuestTemplateAddon`, and `PlayerQuest.cpp:AddQuest/GiveQuestSourceItem`. The following exact SELECT returned these four rows:

```sql
SELECT q.ID,q.StartItem,a.ProvidedItemCount,i.startquest
FROM quest_template q JOIN quest_template_addon a USING(ID)
JOIN item_template i ON i.entry=q.StartItem
WHERE q.ID IN (233,234,320,754) ORDER BY q.ID;
```

| Quest | Provided item | Count | Item starts quest |
| --- | ---: | ---: | ---: |
| 233 | 2187 | 1 | 0 |
| 234 | 2188 | 1 | 0 |
| 320 | 2696 | 1 | 0 |
| 754 | 5411 | 1 | 0 |

The validator no longer zeros StartItem, changes source rows, or suppresses expansion errors. It rejects missing source-item templates, invalid counts, actual `item_template.startquest` starts, unmodeled DB conditions and absent local acquisition evidence.

## Nontrivial objectives inspected

These are bounded source checks, not evidence that the scripts ran successfully in a client.

* **754, Winterhoof Cleansing.** Item 5411 casts spell 4975. Spell.dbc gives focus 6 and quest-complete effect 16 with misc value 754. The well's local physical spawn is map 1, x -2544.29, y -711.974, z -9.77772. No class/profession or AP spell is needed.
* **6395, Marla's Last Wish.** Samuel Fipps 1919 is level 5 at map 0, x 1982.9, y 1376.01, z 63.0515. His loot directly supplies Samuel's Remains 16333 at 100%; that item casts 20364. The quest's explicit grave target -178090 also has a local spawn in the report. This implicit item requirement was not inferred from an empty RequiredItem list.
* **8346, Thirst Unending.** Local Mana Wyrms 15274 have SmartAI spell-hit handlers for Arcane Torrent 28730, 25046 and 50613, each casting credit spell 61314. Its DBC effect 134 grants target credit 15468. This uses the Blood Elf racial, not an AP-shuffled major ability. The retained race masks matter; faction compatibility alone does not grant it to every Horde profile.
* **746, retained Dwarven Digging.** Broken Tools 4703 do not directly drop. Local Bael'dun Diggers 2989 and Appraisers 2990 drop Prospector's Pick 4702 at 41% and 34%; template levels are 7–8 and 8–9. Item 4702 casts 4954, whose DBC effect 24 creates 4703 and requires focus 3. A local forge 17190 is at map 1, x -1981.14, y 442.017, z 133.59. The validator checks this generic item-use creation path rather than exempting quest 746 or pretending 4703 is a drop.
* **11129, retained Kyle's Gone Missing.** Kyle 23616 is level 12 at map 1, x -2459.23, y -484.062, z -9.01284, but the objective is feeding him, not killing him. Tender Strider Meat 33009 drops at 50% from local strider entries 2956/2957/3068 and casts 42222. SmartAI credits 23616 on summoned unit 23622. Template level alone is not evidence of a level-12 combat gate.

The supplementary inspection used these exact queries, in addition to the report's automated projections:

```sql
SELECT c.id,t.minlevel,t.maxlevel,c.map,c.position_x,c.position_y,c.position_z
FROM creature c JOIN creature_template t ON t.entry=c.id
WHERE c.id IN (1919,2989,2990,23616) ORDER BY c.id,c.position_x;
SELECT Entry,Item,Chance FROM creature_loot_template
WHERE Item IN (4702,16333,33009) ORDER BY Item,Entry;
SELECT entry,name,spellid_1 FROM item_template
WHERE entry IN (4702,5411,16333,33009) ORDER BY entry;
SELECT t.entry,t.Data0 AS focus,g.map,g.position_x,g.position_y,g.position_z
FROM gameobject_template t JOIN gameobject g ON t.entry=g.id
WHERE t.entry IN (2913,17190) ORDER BY t.entry;
SELECT entryorguid,event_type,event_param1,action_type,action_param1
FROM smart_scripts WHERE entryorguid IN (15274,23616)
AND action_type IN (11,33) ORDER BY entryorguid,id;
```

Results: the creature query returned Samuel once, 21 Diggers, 13 Appraisers and Kyle once. Loot rows were `(2989,4702,41)`, `(2990,4702,34)`, `(1919,16333,100)` and `(2956/2957/3068,33009,50)`. Item spell IDs were `4702→4954`, `5411→4975`, `16333→20364`, `33009→42222`. Focus rows were `2913→6` and `17190→3` at the coordinates above. SmartAI returned three Mana Wyrm cast rows and Kyle's summoned-unit credit row. DBC field indices follow the pinned DBCStructure.h SpellEntry layout.

The temporary proposal had already rejected quest 787 because Eitrigg starts it in Orgrimmar despite its Valley of Trials category, and avoided quest 861's nonlocal route. Neither was added. The final objective scan required no further substitutions. High-level alternate item drops were not accepted as witnesses when a local level-10-or-below source existed.

## Hash and deployment impact

The bridge's semantic catalog version changes:

```text
old 12df641b1ebd18ef35b4bac5768a950cb7f040456bdfd32d2a69729b09c0a18c
new 4611c269173e443bff425e85a255fa086315ffdec0657c9098982d8e6fe9e1b0
```

This hashes all five authoritative catalogs without provenance. It changes both because of the 88 replacements and the source-preserving quest ancestry fields. File SHA-256 values after regeneration:

```text
checks.json   3ea02dcbddcfa447a205ca6502872779f432c67b153da63a69fbcf827d06ace6
profiles.json 3b42240668ec66c1476673d02399a4b3b6482e823bdd6e4588f285240d237bbc
```

The 212 retained definitions preserve AP IDs; the 88 additions use fresh real-quest IDs and do not intersect retired AP IDs. Profile starts, positions, orientation and restrictions remain unchanged. Profiles.json changes only in provenance.

Existing manifests/bindings using the old catalog hash must remain unchanged. They will not match the new installed catalog. Generate new seeds against matching catalogs; preserve old artifacts for old sessions. The parent must regenerate `src/APCatalog.h` and `addon/WoWPilago/Catalog.lua` and rebuild native consumers. This task did not edit APWorld logic/tests or generated headers.

No source-audit blocker remains. Terrain, collision, phases, hidden script behavior, safe combat routes, timing, actual turn-in/credit hooks and client behavior still need live gameplay checks. The evidence establishes local source coverage, not a full 1–80 playthrough or even leveling balance.
