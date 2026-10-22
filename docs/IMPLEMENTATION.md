# Full implementation work plan

## Scope and completion

The active goal is every applicable requirement in TODO.md, including its release gates.
A completed implementation without the corresponding release evidence does not complete a release-gate checkbox.
Preserve unchecked tasks until their concrete requirement is verified.
The repository uses the local main branch. Keep the decision trail and reproducible test artifacts with the implementation.

## Decisions

V1 supports the nine non-Death-Knight classes and their legal WotLK race combinations.
Death Knights are explicitly excluded, as permitted by the backlog's start-mode requirement.
Victory requires the character's actual level 80 and no equipment, raid, class-ability, or expansion flag.
Expansion access still gates checks and server travel into Outland and Northrend.
Riding and class abilities keep their normal eligibility levels and prerequisites.
Merchants use personal categorized gossip menus. Other players never see the slot's stock.
Raid locations are filler-only. Ordinary mandatory access rules never require useful rewards.
Future class challenges and additional equipment/riding gates are explicitly deferred design decisions, not v1 features.

## Data contract

Authoritative JSON catalogs live in apworld/wowpilago/data and ship with the APWorld.
Other components consume these catalogs or generated tables, not independent hand-maintained copies.
Catalog schema and slot protocol version are 2.
Legacy potion ID 919000001 and protocol 1 remain reserved and are never repurposed.

checks.json is an object with schema_version and a checks array.
Each check has key, kind, wow_id, name, faction, classes, races, min_cap, expansion, riding, prerequisites, difficulty, effort_minutes, and ap_id.
Kinds are quest, exploration, boss, dungeon, level, raid.
Faction is any, alliance, or horde. Empty classes/races mean all legal supported profiles.
Expansion is azeroth, outland, or northrend. Riding is none, expert, or cold_weather.
Prerequisites are other check keys. Dungeon checks additionally list boss_ids and map_id.
Boss and raid checks additionally record map_id. Exploration means entering the named zone, not full map exploration.
AP ID bases are quest 919500000, level 919600000, exploration 919700000, boss 919800000, dungeon 919900000, raid 920000000, plus the source WoW ID.
Exactly 150 quest, 60 exploration, 48 boss, 14 dungeon, 16 level, and 12 raid definitions are required before filtering unsupported profiles.

abilities.json is an object with schema_version and abilities.
Each ability has class_id, base_spell, name, min_level, ranks, ap_id, and prerequisites.
Ranks are spell IDs in the same audited trainer/rank chain. AP ID is 919101000 + base_spell.
No talent-granted, essential form/stance, baseline pet, or mandatory introduction ability is shuffled.
Class 6 is excluded explicitly. Every other supported class has at most eight independent abilities.

gear.json is an object with schema_version, items, sets, and class_roles.
class_roles maps each class ID to the roles supported by its viable specializations.
Merchant stock intersects source-backed item roles with this map. Legendary selection uses its separate class/proficiency policy.
Each item has wow_id, name, quality, expansion, inventory_type, item_class, item_subclass, allowable_classes, required_skill, required_skill_rank, required_level, item_level, set_id, price, and roles.
Allowable classes are numeric class IDs determined from data and normal weapon/armor compatibility, not current specialization.
Roles are caster, healer, melee, tank, or ranged. Expansion is 0, 1, or 2.
Each set has wow_id, name, class_ids, pieces, and expansion. Pieces are real item IDs in items.
Legendaries are separate from shop stock and have quality 5. Their AP IDs are 919400000 + wow_id.

profiles.json records legal race_id, class_id, faction, and starting_zone combinations from the pinned database.
rewards.json records all generic item definitions with ap_id, name, kind, value, classification, and base_count.
Generic rewards use IDs 919100001 cap, 919100002 Outland, 919100003 Northrend, 919100010..14 riding, 919100020 talent, 919100031..33 vouchers, 919100040 bag, 919100050 gold, 919100051 consumables.
Riding order is apprentice, journeyman, expert, artisan, cold_weather.
Classes and named legendaries extend the generic pool from their catalogs.
The reference 300-location pool has 128 fixed rewards and 172 filler rewards, split into 100 Gold Caches and 72 Consumable Caches.
The 11-progression and 117-useful split applies when both flying tiers gate selected checks.
Cold Weather Flying remains useful when no selected check requires it. That changes the classification split, not the reward count.
The locally repaired profiles expose 205 to 218 locations. Filler adjusts to those actual counts and changed options.
The default Human Warrior has 213 locations, 49 Gold Caches, and 36 Consumable Caches.
Every profile has 20 local opening checks. Other accessible starting zones remain separate and do not inflate that local count.
The catalog version hashes canonical semantic JSON, excluding source provenance. Source revision text cannot reroll stock or invalidate otherwise identical manifests.

## Runtime invariants

A seed/slot binds to one character. Deletion archives the binding and preserves reward history.
Protocol 2 has a distinct schema and migration path. Existing protocol-1 inventory and receipts are not reset or silently reinterpreted.
Received AP indices, completed checks, merchant stock, voucher balance, and purchases are durable per binding.
Checks remain in an outbox until the AP server acknowledges them.
A completed purchase or reward cannot debit or grant twice after a replay.
The fixed single-character DB worker and commit-before-publication inventory path remain the baseline until replaced by an equally verified mechanism.
Live progression state belongs to the Player's CustomData, not a cross-player mutable map.
A five-second joined world tick saves changed cap-bank and level state. A saved actual level 80 remains necessary for bridge victory reporting.
AP equipment authorization is per item GUID, never a global item-template change.
AP bag rewards also bind to their receiving character. Consumable rewards remain normal consumables.
Only required character level is bypassed. Original item identity, stats, class, armor and weapon proficiency requirements remain intact.

## Work sequence

1. Inventory current behavior, pin source/data/client, and extract validated catalogs. Finish with count and live-data validation reports.
2. Implement APWorld profiles, options, exact pool accounting, deterministic stock/legendaries, regions, and access rules. Finish with real generation and seed simulations.
3. Implement v2 persistence and bridge contracts, progression effects, check outbox, and character lifecycle. Finish with SQL fault/replay tests and protocol integration.
4. Integrate server hooks, XP caps/banking, expansion travel, riding, talents, selected spell learning, equipment authorization, and merchants. Finish with builds and real realm probes.
5. Exercise every runtime category, supported profile, inventory/purchase failure, low-level equipment path, a full playthrough, and a cross-game multiworld. Update TODO only against inspected evidence.

## Delegation

Agents receive bounded file ownership and read this contract before writing.
Catalog authors own only their catalog/tool/test files. Runtime authors do not redefine catalog fields or IDs independently.
Report missing source evidence rather than invent a WoW ID, test result, or checked task.
The coordinator reviews actual artifacts and reruns tests before accepting delegated completion.
