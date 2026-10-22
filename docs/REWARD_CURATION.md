# Reward curation audit

## Reproduce

```sh
python tools/validate_rewards.py
python -m unittest discover -s tests -p test_reward_catalog.py -v
python tools/validate_rewards.py --live
# Intentional regeneration of the two catalogs only:
python tools/validate_rewards.py --rebuild --live
```

Offline checks require only Python's standard library. Live checks use the existing `wow-test-database-1` container's MySQL client against `acore_world`, root/test-only. This is the same MySQL instance published at 127.0.0.1:13317. The query helper accepts only single SELECT statements. No database writes, template patches, migrations, or stock generation occur. Root credentials are local test credentials, not a production deployment recommendation.

DBC directory defaults to `../wow-test/data/client-data/dbc` adjacent to the repository; override with `--dbc-dir`. Live validation reconstructs the bounded curation and compares both catalogs exactly. Rebuilds are deterministic for identical sources. A source change can change membership, names, eligibility, or pricing inputs and must be reviewed before regeneration is accepted.

## Source evidence

Audited against AzerothCore source commit `9fb906bb7296212ff42fc95ff73a92aaf8554f0d` at `../wow-test/azerothcore`. The database reports `ACDB 335.17-dev`, cache ID 17. Its server revision is `unknown`; this audit does not pretend the database is a pristine checkout of that core commit. Client data is the local 3.3.5a DBC installation, not a newly extracted or independently authenticated client distribution.

| DBC | SHA-256 |
| --- | --- |
| ItemSet | `28c285ea7cab86b74c06ad30138c62c26d5ea5303f1fd2bccb9b3285a95d3467` |
| Spell | `d5cce1a83550dcfa9eb2f0251dbb11fd24c272534b2b1a9b230924a44d817ab3` |
| Talent | `23aefff3add151bf504c4d0bab247e2e622f9cf29a473d091cb9f11127d99d68` |
| SkillRaceClassInfo | `341a42678faee5f208e0874ab154ee174b99ba469306df7458bdaf0ffcf76967` |
| SkillLineAbility | `4154b833d6a26b9b9ce53851d56cb594f0813c0936a72ec89f933cc69abe42c3` |
| Map | `261bd7c2c9dbdba1f2966ca21106673ed722c2e3681d227f1eed261b6ce870d5` |

`tools/validate_rewards.py` contains the exact SQL and DBC field offsets, checked against the core's `DBCStructure.h`. Item identity, quality, slot, class mask, skill requirements, levels, stats, and set ID come from `item_template`. Normal proficiency availability comes from `SkillRaceClassInfo.dbc`, intersected with the DB class mask. `npc_trainer`, `spell_ranks`, `Spell.dbc`, `SkillLineAbility.dbc`, and `Talent.dbc` audit abilities. `ItemSet.dbc` supplies set identity, names, and Classic/TBC membership. No external fan-site IDs are assumed.

## Catalog size and coverage

There are **885 distinct items**, comprising 874 nonlegendary items and 11 legendary identities. Quality counts are 76 Uncommon, 182 Rare, 616 Epic, and 11 Legendary. Expansion counts, including legends, are 288 Classic, 381 TBC, and 216 Wrath. There are 70 set records: 69 vendor-eligible featured sets and one legendary weapon set.

| Class ID / class | Shop candidates | Featured sets | Compatible legendary identities |
| --- | ---: | ---: | ---: |
| 1 Warrior | 467 | 8 | 11 |
| 2 Paladin | 414 | 11 | 4 |
| 3 Hunter | 369 | 5 | 6 |
| 4 Rogue | 317 | 5 | 5 |
| 5 Priest | 249 | 8 | 5 |
| 7 Shaman | 399 | 11 | 6 |
| 8 Mage | 226 | 5 | 5 |
| 9 Warlock | 226 | 5 | 5 |
| 11 Druid | 342 | 11 | 6 |

Class 6 is explicitly unsupported. Counts overlap between classes. Every class has more than 120 unique nonlegendary candidates, all three expansions, all three vendor qualities in each expansion, weapons, armor, rings, and trinkets. This supplies the requested 30–120 stock size without implementing the AP agent's sampling algorithm. It does not prove any particular sampling algorithm preserves coverage.

### Selection policy

This is a bounded pool, not all equippable DB entries. Explicit class raid sets are tier 1, tier 2, tier 4, tier 6, and tier 7. All tier-4/6/7 spec variants are included for hybrid classes: Paladin healing/tanking/melee, Shaman healing/caster/melee, Druid healing/caster/feral, Priest healing/caster, and Warrior tanking/melee. Nonset selection takes at most one highest-item-level candidate per class, expansion, quality, slot, and advisory role. Lower item ID breaks ties. Shared choices deduplicate globally.

Normal nonset candidates must have an actual spawned-creature loot source in their declared expansion. The source query joins `creature_loot_template`, `creature_template`, and `creature`; it recursively expands `reference_loot_template` and resolves each spawn map through `Map.dbc` expansion field 63. ID-era bands and level/item-level windows additionally exclude recycled and unrelated rewards. IDs alone are not accepted as expansion evidence. Crafting-only, reputation-only, class-spell-required, race-restricted, faction-flagged, test, and deprecated nonset candidates are excluded. Set pools are the explicit historically identified raid tiers above, not inferred from numeric ID bands alone.

Roles come from real item stats and weapon/armor subtype. They are broad advisory equipment categories, not a promise that every tagged item is optimal for every spec. Intellect/spirit/spell stats cover caster/healer choices; physical stats cover melee/ranged choices; defense, avoidance, block, shields, and Druid-compatible agility/strength leather supply tank choices. Shared hit/crit/haste stats alone do not turn caster gear into physical gear. Statless utility items are shared choices. Raid-set variants provide explicit spec representation independently of these broad tags. Generation must not lock the pool to the character's current spec.

### Set counts and the tier-7 discrepancy

Classic tier 1/2 each have 8 pieces. TBC tier 4 has 5, and tier 6 has **8**, including Sunwell belt/bracer/boot extensions. Wrath tier 7 has 5 pieces per spec variant. The catalog stores the actual selected piece IDs, so consumers use `len(pieces)`, not a universal count.

The local tier-7 `ItemSet.dbc` item arrays point at unused 437xx/438xx copies. Several even disagree with those templates' DB `itemset`. For example, set 787 lists 43743, but the DB assigns that item to 788. Those unused copies are not curated. For tier 7, membership is instead the five real Heroes' templates with matching DB `itemset` below ID 40000. Set identity, name, and bonuses remain those of the original DBC set. The validation requires both directions of each catalog set relationship and compatible class membership.

Set 699 is the real two-piece Warglaive set. It is recorded to preserve the original item/set relationship, **not as a featured vendor set**. Consumers must filter vendor items to `quality != 5` and featured sets to sets whose pieces are all nonlegendary. The summary tool's raw set counts include 699 for Warrior/Rogue; the table above excludes it.

### Exact voucher policy

Voucher prices are AP design policy, not a claim that the source DB contains voucher costs. The source-backed inputs are quality, expansion, item class, set membership, and item level. The formula is fixed and tested:

| Curated category | Vouchers |
| --- | ---: |
| Uncommon | 1 |
| Rare | 2 |
| Classic / TBC / Wrath epic armor, jewelry, trinket, or set piece | 3 / 4 / 5 |
| Classic / TBC / Wrath curated epic weapon | 6 / 7 / 8 |
| Legendary | 0, direct-only, never purchasable |

The bounded selector takes high-item-level epic weapons within each pool; no hidden vendor/gold-cost conversion is used. Expansion-priced nonset epics fill the backlog's otherwise unspecified nonset epic category. Zero is a direct-reward sentinel, not a free vendor price. Economy simulations and deterministic stock composition belong to the AP agent, not this catalog change.

## Legendary compatibility

The curated IDs are Sulfuras 17182; Thunderfury 19019; Atiesh 22589, 22630, 22631, 22632; Warglaives 32837/32838; Thori'dal 34334; Val'anyr 46017; Shadowmourne 49623. All are real DB quality-5 weapons. Direct AP identity is `919400000 + wow_id`.

Compatibility uses the real DB masks **and** normal weapon skills. Warglaives' mask is 9, leaving Warrior/Rogue. Shadowmourne's mask is 260643; intersecting supported classes and two-handed axes leaves Warrior/Paladin. Val'anyr's mask is 32767, but maces still exclude Mage, Warlock, and Hunter. Thunderfury excludes Druid, Priest, and Shaman through sword proficiency. Sulfuras allows Warrior, Paladin, Shaman, and Druid through two-handed maces. Thori'dal allows Warrior, Hunter, and Rogue through bows.

The four Atiesh templates actually have `AllowableClass = -1` in this DB. They are therefore legal for all supported staff users, including Warrior, Hunter, and Shaman. This is deliberately the server's equip compatibility, **not** a fabricated lore/class restriction from the original acquisition quests. Likewise, legal caster swords or Rogue maces are not removed just because their stats/procs may be unattractive. No class gets an incompatible weapon to meet a count. Every supported class has at least two legal identities under these actual data rules. If the project wants a stricter thematic/spec whitelist, that is a separate explicit curation decision, not permission to bypass normal equip checks.

All four Atiesh templates share their real DB name. Consumers must use `wow_id`/AP ID as identity and disambiguate displayed reward names, for example by appending the WoW ID. Never collapse them by display name. Warglaives are two separate items, not one synthetic item.

## Ability audit and early banking

There are **72 independent abilities**, exactly eight for each supported class, covering **129 rank spell IDs**. The user-proposed Mage and Warrior lists are retained exactly. Warlock Ritual of Doom 18540 and Inferno 1122 were rejected because they have no trainer rows in this DB; Shadow Ward and Unending Breath replace them. Purge's base is **370**, not second rank 8012.

| Class | Eight audited abilities |
| --- | --- |
| Warrior | Charge, Intercept, Pummel, Shield Wall, Retaliation, Recklessness, Intimidating Shout, Challenging Shout |
| Paladin | Divine Shield, Lay on Hands, Hand of Protection, Hand of Freedom, Hand of Sacrifice, Hand of Salvation, Turn Evil, Divine Intervention |
| Hunter | Disengage, Feign Death, Freezing Trap, Frost Trap, Tranquilizing Shot, Flare, Concussive Shot, Rapid Fire |
| Rogue | Sprint, Evasion, Vanish, Kick, Blind, Kidney Shot, Distract, Cloak of Shadows |
| Priest | Fade, Psychic Scream, Mind Control, Fear Ward, Shackle Undead, Mass Dispel, Levitate, Mind Vision |
| Shaman | Astral Recall, Earthbind Totem, Tremor Totem, Grounding Totem, Wrath of Air Totem, Fire Elemental Totem, Hex, Purge |
| Mage | Blink, Frost Nova, Counterspell, Ice Block, Polymorph, Slow Fall, Spellsteal, Invisibility |
| Warlock | Fear, Howl of Terror, Death Coil, Soulshatter, Ritual of Summoning, Shadow Ward, Unending Breath, Banish |
| Druid | Dash, Bash, Barkskin, Innervate, Rebirth, Hibernate, Challenging Roar, Enrage |

Every base must be the first `spell_ranks` rank, or an unranked trainer spell. Every selected rank has a trainer row and a real Spell DBC record. Every chain is checked against all five rank columns of every `Talent.dbc` record. Class associations come from `SkillLineAbility.dbc`; newer spells with class mask zero inherit their class skill-line association. No selected ability is itself an essential stance, form, baseline pet spell, or talent grant. Ordinary damage/healing, Druid forms, Warrior stances, Rogue Stealth, Hunter pet taming/revival, Warlock baseline demons, and ordinary resurrection remain baseline. Fire Elemental is an optional timed guardian, not baseline pet functionality.

Top-level ability fields exactly follow schema 2. `prerequisites` is a list of typed metadata objects, not AP check keys or AP access gates:

* `rank_eligibility`: one per rank, in `ranks` order. Contains `spell_id`, `min_level`, trainer `required_spell`, `required_skill`, `required_skill_rank`, DBC `totem_items`, `totem_categories`, and `reagents` as `{wow_id, count}`. `min_level` is the maximum of trainer ReqLevel and Spell DBC SpellLevel. A deterministic lowest-level trainer row supplies trainer prerequisites. The full live reconstruction detects source changes.
* `baseline_form_mask`: exact DBC allowed stance/form bit mask. Bits are form ID minus one, not AP item flags.
* `baseline_spells`: audited baseline examples, including Berserker Stance 2458 for Pummel/Intercept/Recklessness, Defensive Stance 71 for Shield Wall, Battle Stance 2457 for Charge/Retaliation, Cat Form 768 for Dash, and Bear Form 5487 for Bash/Challenging Roar/Enrage. Bear's stance mask also permits Dire Bear normally.
* `equipped_item`: exact Spell DBC item class, subclass mask, and inventory mask where required. Shield Wall therefore retains its shield requirement.

An early AP receipt records the unlock but does not lower these levels, auto-buy reagents, bypass class quests, or manufacture forms/stances/totem access. `min_level` is the first learnable level; later ranks retain their own levels and normal rank order. For example Pummel is level 38 with baseline Berserker Stance, Dash is level 26 with baseline Cat Form, and Purge ranks are levels 12/32. Totem categories and reagents are ordinary casting requirements, not reasons to withhold an otherwise eligible learned spell. Rebirth records each rank's distinct reagent. None of these records creates a location-access or victory requirement.

## Verification and remaining gates

The offline suite has 22 tests. They exercise complete-catalog relationships and actual rejection of duplicate IDs, incorrect pricing, illegal weapon/plate classes, missing/wrong set pieces, overlapping spell ranks, missing banking metadata, bad AP IDs, DK inclusion, talent-granted source spells, nonbase ranks, missing trainers, wrong class associations, malformed DBC headers, and write statements. Tests also assert actual featured piece counts, Warglaive/Shadowmourne masks, Pummel/Dash prerequisites, and Purge rank eligibility. Live validation successfully reconstructs all 885 items and all 72 ability records from the current SQL/DBC sources.

This is content evidence, not a runtime release test. Still required: instance-only level exemption, proficiency training at normal levels, dual wield/offhand requirements, client equip behavior, proc/set-bonus behavior below level, ability trainer/internal-learning interception, early unlock release, ordinary totem/form class quests, reagent/casting restrictions, stock coverage/economy simulations, and live delivery. No normal item-template requirements should be globally changed. No other agent's files or TODO checkboxes were edited.
