# Catalog and stock quality audit

This report supersedes the gear counts and role-selection description in `REWARD_CURATION.md`. Schema remains 2. Item fields, retained item identities, AP IDs, options and all 70 set records remain unchanged. `gear.json` adds the canonical top-level `class_roles` map. The catalog hash changes; the coordinator must regenerate the C++ header before integration. Old slot data needs its matching catalog/header; this is not an in-place saved-seed migration. Do not reroll already-persisted personal stock.

## Corrections

The suspected bugs were real. Unknown items received every role, every class had to satisfy all five roles, and merchant eligibility checked proficiency alone. In 2,000 baseline seeds per class, Warrior stock averaged 13.30 entries with source-backed roles irrelevant to Warrior, plus 6.15 entries whose roles could not be established. Hunter averaged 17.91 irrelevant and 7.33 unknown entries. These are separate counts, not claims that every irrelevant entry was cloth.

`tools/validate_rewards.py` and AP stock now use `gear.json:class_roles`. This covers viable specializations, not every role label for every class. Legendary selection retains its separate source-mask/proficiency policy.

Item roles now inspect positive stat modifiers and actual item-spell effects in `Spell.dbc`, including Classic spell damage/healing, attack power, mana regeneration, avoidance and triggered effects. Negative debuffs and on-hit weapon debuffs do not become wielder stats. Strength alone is melee, never caster or ranged. Intellect or mana regeneration on otherwise physical Hunter, enhancement or feral gear does not invent caster/healer suitability. Shared hit/crit/haste alone supplies no role evidence.

Unknown is no longer universal. Explicit health/stamina/resistance utility can retain shared roles, but shared utility cannot satisfy specialization coverage. Random-affix templates without known final stats are excluded from nonset selection. Nonset choices retain spawned-creature loot and source-expansion evidence. There are no fixed-affix Wrath greens in the admitted loot/level windows, so validation requires all three qualities per class overall and rare/epic coverage in each era, not fabricated Wrath green stats.

The bounded selector now takes two source-backed alternatives per class/era/quality/slot/viable-role facet. One alternative left Mage and Warlock unable to fill the valid 120-entry, four-featured-set, zero-roll configuration. Validation now reserves enough candidates for that worst case, and the stock test exercises it for every class.

Merchant candidates require both legal proficiency and a viable class role. Coverage facets use class-relevant roles, actual inventory types, all three eras and all three vendor qualities. After coverage and featured reservations, random-tied epic fillers take priority over rare/uncommon fillers. Prices and the 204-voucher supply are unchanged. This fixes the previous economy where 16,328 of 18,000 sampled stocks were entirely affordable.

Featured selection remains three sets by default, with independent 80% rolls for each real catalog piece. Unrolled featured pieces cannot return as fillers. Classic tier 1/2 and TBC tier 6 have eight pieces; tier 4 and tier 7 have five. No full-eight-piece guarantee was added. Existing uniform overflow sampling remains intact. Legendary set 699 is not a vendor featured set, and no quality-5 item enters stock.

## Source and catalog evidence

SQL used only SELECT statements through the existing `wow-test-database-1` MySQL client as root/test-only. Container port 3306 maps to `127.0.0.1:13317`. DBC files came from `../wow-test/data/client-data/dbc`, not an assumed `datadir` path. Core checkout is `9fb906bb7296212ff42fc95ff73a92aaf8554f0d`; DB version is ACDB 335.17-dev. The DB-reported runtime revision remains unknown.

Connected validation reconstructed every gear field, source membership, price and all 72 existing ability records successfully. DBC hashes still match `REWARD_CURATION.md`. No SQL, item-template or ability-catalog writes occurred.

The final catalog contains 1,204 items: 93 uncommon, 319 rare, 781 epic and 11 direct-only legendary identities. Era counts including legends are 468 Classic, 459 TBC and 277 Wrath. Compared with the original 885 items, 755 identities remain, 449 source-backed choices were added and 130 were removed. Retained records differ only in advisory roles. No ID was reassigned.

The following counts exclude irrelevant roles and legendary items. They are merchant candidate counts, not proficiency-only counts.

| Class | Candidates | Featured sets | Mean stock cost | Mean entries bought with 204 | Mean unsold cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| Warrior | 510 | 8 | 245.07 | 53.96 | 43.88 |
| Paladin | 708 | 11 | 238.77 | 54.03 | 36.93 |
| Hunter | 321 | 5 | 245.02 | 54.08 | 43.94 |
| Rogue | 280 | 5 | 249.20 | 53.61 | 48.08 |
| Priest | 264 | 8 | 238.97 | 54.73 | 37.45 |
| Shaman | 620 | 11 | 241.32 | 54.07 | 39.55 |
| Mage | 241 | 5 | 236.57 | 55.20 | 35.36 |
| Warlock | 242 | 5 | 235.71 | 55.34 | 34.41 |
| Druid | 532 | 11 | 241.59 | 54.11 | 39.87 |

The table uses seeds 0 through 1,999 for each class, slot 1, default stock settings, and cheapest-first purchases. Across these 18,000 corrected stocks, costs ranged from 206 to 287. Cheapest-first purchases averaged 89.4% to 92.2% of stock by class; even the worst sample bought 48 of 60. Buying in shuffled display order averaged 49.37 to 52.09 entries by class. No sampled inventory was entirely affordable. Unsold cost is the sum of remaining entries after actual purchases, not simply total cost minus 204.

Every corrected stock had 60 unique legal, role-relevant, nonlegendary items. Class-specific role coverage and every available era/slot/quality facet passed for every sample. There were zero unknown-role or wrong-class-role entries. All featured-piece membership assertions passed. Across 356,937 piece rolls, inclusion was 79.910%; 4,719 of 28,979 eight-piece featured sets rolled complete, or 16.284%, against the theoretical 16.777%. Default overflow was zero. The pre-fix and corrected runs produced identical featured rolls.

## Verification

Reproduce the committed suites with the existing AP environment:

```sh
AP_PY=/path/to/archipelago-venv/bin/python
python tools/validate_rewards.py --live
python -m unittest discover -s tests -p test_reward_catalog.py -v
"$AP_PY" tests/verify_world.py /tmp/archipelago-upstream
"$AP_PY" tests/simulate_seeds.py /tmp/archipelago-upstream --seeds 2000
```

All 27 reward tests and all 26 existing APWorld tests passed, including real packaged generation, profile/options construction and restrictive fills. Only the existing stock test in `apworld/wowpilago/test/__init__.py` was edited. It now checks relevant role coverage, rejection of proficiency-only irrelevant gear, affordable-most-but-not-all stock, and the maximum-size zero-roll case.

The existing 2,000-seed AP simulation passed real fills across all 52 legal profiles. Shop cost was 209 to 281, mean 241.87. Cheapest-first purchases averaged 54.349 of 60 entries. Mean affordable counts at actual check-completion quarters were 19.413, 33.6065, 45.835 and 54.349. This is simulated reward ordering, not measured playtime. Its raw role-label totals are not class-specialization coverage; the separate 18,000-stock audit checked class-specific facets.

Temporary evidence remains at `/tmp/reward-quality-live.log`, `/tmp/reward-quality-tests.log`, `/tmp/reward-quality-world-tests.log`, `/tmp/reward-quality-ap-simulation.log` and `/tmp/stock-quality-simulation.json`. The before/after stock audit script is `/tmp/simulate-quality-stock.py`, with baseline `/tmp/gear-before-quality.json`. These are session artifacts, not release fixtures.

## Global AP IDs

An unfiltered registry import under AP Python 3.13.11 loaded 82 games from `/tmp/archipelago-upstream`, revision `54803be064fc7e80c4628777ed0b46a9390f255f`. WoW was excluded from comparison. All 98 WoW item IDs and 300 location IDs were compared with the corresponding item/location namespaces of every loaded game. Actual collisions: zero. Failed world imports: zero. No IDs needed changing.

Evidence is `/tmp/wow-apid-audit.json`; reproducer is `/tmp/audit-wow-apids.py`. This covers the installed upstream registry, not uninstalled third-party APWorlds or a universal reservation of these IDs. No custom-world directory was present in that checkout. AP used its documented pure-Python LocationStore fallback; no native build was performed.

## Current check capacity

The later opening curation supersedes the counts below. The current 300 definitions provide 205 to 218 compatible checks across 52 profiles. Human Warrior has 213 checks, 49 Gold Caches and 36 Consumable Caches. Every default profile has 20 source-local opening checks. `docs/OPENING_CURATION.md` and `docs/CRITICAL_TRAVEL.md` state their source and logic limits. These counts do not prove a completed ordinary opening route or the full playthrough.

The literal 100 Gold and 72 Consumable caches require 300 selected checks per default slot. Expanding the raw catalog and its category totals awaits the user's specification decision. No extra content has been admitted to satisfy that arithmetic.

## Historical checks and profiles recommendations

At this audit's checkpoint, there were 300 definitions, but only 229 Alliance or 234 Horde locations after profile filtering. Pre-cap-80 counts are 181 and 186. All 52 profiles have 34 faction-wide early checks, not 34 local checks. The documented local opening remains nine checks. Do not mark the 20-to-35-local-check opening requirement complete without reallocating starter content or explicitly accepting faction-wide travel and measuring that route.

The inspected catalogs already use `world_updates_count: 2917` and an updates projection hash. They do not currently embed two copies of all 2,917 update rows, despite the older curation document's wording. Their identical provenance blocks are about 3,664 bytes each when serialized independently with two-space indentation. Keep compact count/hash references and retain the full update list in source-validation evidence. That small remaining duplication does not justify a new loader or schema. Checks and profiles were not edited.

No native runtime/build, client equip/proc/set-bonus test, delivery/purchase transaction test, travel timing, full playthrough or live multiworld was performed. Role labels remain broad equipment suitability, not a gear optimizer. Proficiencies trainable later are still subject to normal training and non-level requirements. Header regeneration and runtime integration remain the coordinator's work; these results do not complete the backlog's runtime release gates.
