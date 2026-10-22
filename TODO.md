# AzerothCore × Archipelago — Implementation TODO

> **Target:** AzerothCore / World of Warcraft 3.3.5a, integrated with Archipelago Multiworld.  
> **Design status:** Working specification / implementation backlog. Checked tasks have requirement-specific evidence in `docs/requirements-evidence.json`. Runtime and release gates remain separate.  
> **Current version:** v0.4 — Hybrid progression + randomized equipment merchant.

## 0. Agreed design baseline

- [x] Build an Archipelago `APWorld` and an AzerothCore integration module/bridge.
- [x] Support **curated** checks (not all quests by default): quests, level milestones, dungeon bosses, dungeon completions, zone exploration, and raid bosses.
- [x] Set **victory condition to reaching level 80**; do not require raids, equipment, or every ability to win.
- [x] Use **hybrid randomization**: levels, expansion access, riding, selected class abilities, and reserved talent points can be Archipelago rewards.
- [ ] Keep baseline class combat functionality available without Archipelago rewards.
- [x] Implement seed-specific equipment vendors in major cities, with the **same personal inventory** at each vendor.
- [x] Award **equipment vouchers** through Archipelago; let players choose purchases.
- [x] Give **legendary equipment directly** as named Archipelago rewards, not through the shop.
- [ ] Allow Archipelago-awarded equipment to be equipped **below its normal required level**, preserving original stats and set bonuses while retaining class/armor/weapon proficiency requirements.
- [x] Make Archipelago-awarded equipment character/slot-bound, non-tradeable, and non-auctionable.

## 1. Project structure & data model

- [x] Pin the supported AzerothCore commit, database revision, and 3.3.5a client build.
- [x] Create repositories/directories for the Python APWorld, AzerothCore C++ module, bridge service, data catalogs, and tests.
- [x] Define stable, noncolliding Archipelago item and location IDs and a migration/versioning policy.
- [x] Define a machine-readable catalog for curated quests, levels, boss kills, dungeon clears, zones, and raid bosses.
- [x] Record for each check: source WoW ID, name, faction, class restrictions, minimum logical level cap, expansion/riding requirements, prerequisites, difficulty, and expected effort.
- [x] Validate quest, boss, map, area, spell, and item IDs against the pinned AzerothCore data.
- [x] Decide whether Archipelago slots are strictly one-character-per-slot (recommended initially).
- [x] Persist seed ID, slot ID, connected character GUID, received AP items, completed checks, vouchers, vendor stock, and purchases.
- [ ] Make reward application and check reporting idempotent across reconnects, relogs, crashes, and world restarts.

## 2. Archipelago checks (~300 initial target)

- [x] Curate **150 quest completion** checks; exclude dailies, repeatables, impossible faction/class combinations, and problematic chains.
- [x] Curate **60 exploration** checks; specify whether each represents entering a zone or completing its exploration criteria.
- [ ] Curate **48 dungeon boss** checks; count each boss only once per AP slot.
- [x] Curate **14 dungeon completion** checks; define unambiguous clear conditions.
- [x] Implement **16 level milestones** (5, 10, ..., 80), reconciling early milestones with character start mode.
- [x] Curate **12 raid boss** checks; keep these optional and non-progression for the level-80 goal.
- [ ] Ensure starting regions provide roughly **20–35 accessible checks** without needing item unlocks; aim for ~30.
- [ ] Balance locations across cap bands (10, 20, 30, 40, 50, 60, 70, 80), adjusting for expansion access.
- [x] Ensure the majority of useful leveling checks are available **before** reaching level 80.
- [x] Specify party credit rules, first-kill credit, lockouts, playerbot behavior, and multi-character edge cases.
- [x] Support optional raids without placing victory-critical progression exclusively behind them.

## 3. Level caps, XP, expansion access & victory

- [x] Start normal classes at level 1 with a **level cap of 10**.
- [x] Include **7 Progressive Level Cap** items: caps 20, 30, 40, 50, 60, 70, and 80.
- [x] Implement actual server-side XP/level-cap enforcement and preserve cap state across reconnects.
- [x] Implement capped **XP banking** at cap (initial proposal: up to 50% of XP needed for the next level); define the exact award/release behavior.
- [x] Add **Outland Access** as one progression item.
- [x] Add **Northrend Access** as one progression item.
- [ ] Restrict all relevant routes (portals, boats, zeppelins, spells, teleports) in accordance with expansion access flags.
- [ ] Keep ordinary Azeroth travel accessible without randomized continent gating.
- [x] Implement the **level-80 victory event** when the character actually reaches level 80.
- [x] Decide whether Northrend Access is a strict victory prerequisite or merely an optional regional unlock; **current chosen goal is level only**, so don't silently add extra victory requirements.
- [x] Add a separate, valid **Death Knight start mode** (starts at 55, initial cap around 60, mandatory introduction access, adapted cap items/checks) or explicitly exclude Death Knights from v1.

## 4. Riding and flying

- [x] Add **Apprentice Riding** reward (usual level 20 eligibility, 60% ground mount speed).
- [x] Add **Journeyman Riding** reward (usual level 40 eligibility, 100% ground mount speed).
- [x] Add **Expert Riding** reward (usual level 60 eligibility, flying in Outland).
- [x] Add **Artisan Riding** reward (usual level 70 eligibility, faster flying).
- [x] Add **Cold Weather Flying** reward (usual level 77 eligibility, Northrend flying).
- [x] Grant training/use permissions from AP rewards without requiring full standard training fees.
- [x] Preserve normal level eligibility for riding tiers unless a future option explicitly overrides it.
- [x] Add Expert Riding / Cold Weather Flying to access rules **only** for curated flying-dependent checks.
- [ ] Make **ground-accessible** locations completable without mount unlocks.
- [x] Handle flying and mount edge cases when riding items arrive before prerequisites.
- [ ] Verify actual travel and flying restrictions for WotLK 3.3.5a; no ordinary Eastern Kingdoms/Kalimdor flying.

## 5. Talent points (hybrid)

- [x] Preserve the normal WotLK level-80 ceiling of **71 talent points**.
- [x] Reserve **12** normally earned points for Archipelago (proposed reservation levels: 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70).
- [x] Include **12 Talent Point Unlock** items in the item pool.
- [x] Restore one reserved point per AP unlock when the character has reached the corresponding eligibility threshold.
- [x] Bank early-arriving unlocks and release them later when eligible.
- [x] Do not let early AP rewards bypass intended talent tier/level requirements.
- [x] Recalculate available/spent points consistently after level-ups, respecs, relogs, and dual-spec switches.
- [x] Verify special behavior for Death Knights and any modified talent progression.
- [x] Keep talent points **Useful**, not required progression, unless custom checks explicitly gate on them.

## 6. Major class abilities

- [ ] Ensure each class retains a viable baseline rotation, survival tools, and mandatory mechanics.
- [x] Create a class-specific whitelist of **up to 8 independently learned major abilities** per class.
- [x] Exclude talent-granted abilities from the initial ability shuffle; leave them on the talent trees.
- [x] Exclude class-defining prerequisites such as essential stances, Druid forms, baseline pet functionality, and mandatory DK intro spells.
- [x] Review Mage options (e.g., Blink, Frost Nova, Counterspell, Ice Block, Polymorph, Slow Fall, Spellsteal, Invisibility).
- [x] Review Warrior options (e.g., Charge, Intercept, Pummel, Shield Wall, Retaliation, Recklessness, Intimidating Shout, Challenging Shout).
- [x] Review candidate lists for Paladin, Hunter, Rogue, Priest, Death Knight, Shaman, Warlock, and Druid.
- [x] Audit the final list for trainer/rank chains, talent dependencies, class quests, minimum levels, and 3.3.5a compatibility.
- [x] Implement persistent ability-unlock flags; receiving an unlock permits the base spell and normal eligible ranks.
- [ ] Queue early ability rewards until eligible; handle trainers, relogs, specialization changes, and internal spell-learning paths.
- [x] Do **not** require shuffled major abilities for normal quest access or level-80 victory in v1.
- [x] Consider optional future class-specific challenge checks with explicit spell requirements.

## 7. Randomized equipment vendor

### Shop placement, access & inventory

- [x] Add an Archipelago Equipment Merchant to every supported major city for both factions.
- [x] Give each AP slot **one shared personal stock list** visible at every city vendor.
- [x] Generate stock **once per seed/slot**; never reroll it on relog, respec, city change, or daily reset.
- [x] Allow players to inspect the full inventory from level 1, including unpurchased goods and prices.
- [x] Target **60 unique equipment entries** per stock list (configurable, suggested 30–120).
- [x] Choose equipment based on the character's class and all viable specializations; do not force a single current spec.
- [x] Exclude all legendary equipment from vendor stock.
- [x] Include normal weapons, armor, rings, trinkets, and set items across Classic, TBC, and WotLK pools.
- [x] Prefer a native vendor-like UI, but support categorized gossip menus if per-character vendor stock is impractical.
- [x] Replace the simple gossip list with a vendor-style graphical shop showing item icons, hover tooltips, voucher prices and balance, Buy buttons, and SOLD status while retaining personal stock and server-side purchase validation.
- [x] Limit purchases to **one copy per stock entry** by default.
- [x] Display remaining voucher balance and total remaining shop cost.

### Featured sets and weighted completeness

- [x] Select **3 featured class-compatible sets** per stock list by default (configurable 1–4).
- [x] For each piece of a featured set, independently include it with **80% probability** (configurable).
- [x] Do **not** guarantee full sets, but make them substantially likelier than under uniform item-by-item sampling.
- [x] Confirm each featured set's actual piece count; e.g., for an 8-piece set, full inclusion probability is `0.8^8 ≈ 16.8%`.
- [x] Reserve space for selected set pieces and fill remaining slots with other curated equipment.
- [x] Handle inventory-cap overflow if featured-set rolls produce too many items.
- [x] Deduplicate set pieces and other stock entries.
- [x] Shuffle/sort the shop display without altering deterministic seed stock.
- [x] Ensure meaningful representation of different equipment slots, expansions, and class specs.

### Voucher economy

- [x] Create a single persistent **Equipment Voucher** balance per AP slot.
- [x] Define Archipelago rewards: **45 × Voucher +1**, **28 × Voucher +3**, **15 × Voucher +5**.
- [x] Verify total voucher supply: **204 vouchers across 88 AP items**.
- [x] Implement proposed costs: Uncommon 1; Rare 2; Classic raid set piece 3; TBC raid set piece 4; WotLK raid set piece 5; high-end epic weapon 6–8.
- [x] Ensure shop purchase is atomic: check balance, debit once, mark sold, deliver item, and persist all results transactionally.
- [ ] Handle full bags and disconnects without losing vouchers or duplicating purchases.
- [x] Test whether **204 total vouchers** lets the player buy most (but not necessarily all) of a typical 60-item inventory.
- [x] Tune prices/stock generation based on sample seeds; favor meaningful early purchases over permanently unaffordable gear.
- [x] Keep voucher rewards **Useful**, not required progression for level-80 victory.

### Unrestricted equipment behavior

- [ ] Preserve original item stats, procs, set bonuses, visuals, and item identity.
- [x] Bypass **required character level** only for individually authorized Archipelago-awarded item instances.
- [ ] Preserve class, armor-type, weapon-skill/proficiency, and other non-level compatibility rules.
- [ ] Check whether other item/equipment validation paths and unmodified 3.3.5a client behavior need special treatment.
- [ ] Bind AP equipment to the receiving character/slot; block trade, mail transfers, auction house, and other transfer exploits.
- [x] Prevent buying one authorized item from unlocking unrestricted use of ordinary drops with the same item ID.
- [ ] Test low-level characters using high-end procs, stats, sockets, enchants, and set bonuses.
- [x] Compare implementation approaches: core-level instance-specific equipment exemption vs. alternate item templates; prototype the former first.

## 8. Direct legendary rewards

- [x] Place **2 directly awarded named legendary items** per normal seed; make count configurable.
- [x] Pick items from a curated class/weapon-compatible whitelist (e.g., Thunderfury, Sulfuras, Val'anyr, Shadowmourne where compatible).
- [x] Select actual legendary identities deterministically at seed generation, visible in spoiler logs.
- [x] Deliver legendary rewards directly upon receipt of the AP item, without visiting the vendor.
- [x] Apply the same instance-specific level exemption and binding/trade restrictions as vendor gear.
- [x] Queue delivery safely for offline characters or full inventories.
- [ ] Prevent duplicate application after reconnects, AP retransmission, or crashes.
- [ ] Test low-level legendary procs and unusual class/equipment restrictions.
- [x] Keep direct legendaries **Useful**, not prerequisites for any ordinary checks or victory.

## 9. Seed item-pool composition (current proposed 300 items)

- [x] Generate exactly one Archipelago item for each ordinary item-bearing location after accounting for events/prefill.
- [x] Include **7** Progressive Level Cap items — Progression.
- [x] Include **1** Outland Access and **1** Northrend Access — Progression.
- [x] Include **1** Expert Riding and **1** Cold Weather Flying — Progression if required by selected flight-dependent checks.
- [x] Include **3** other riding unlocks — Useful.
- [x] Include **12** Talent Point Unlock items — Useful.
- [x] Include **8** class-specific Major Ability items — Useful (adjust count if a class has fewer safe candidates).
- [x] Include **4** Bag Upgrade items — Useful.
- [x] Include **45** Voucher +1 items — Useful.
- [x] Include **28** Voucher +3 items — Useful.
- [x] Include **15** Voucher +5 items — Useful.
- [x] Include **2** direct named Legendary items — Useful.
- [ ] Include **100** Gold Cache items — Filler.
- [ ] Include **72** Consumable Cache items — Filler.
- [x] **Audit pool arithmetic:** above counts sum to **300** (11 progression + 117 useful + 172 filler).
- [x] Recompute filler counts automatically when check count, class ability count, settings, excluded locations, or prefill changes.
- [x] Scale gold/consumable rewards sensibly to the recipient's current character progression.
- [x] Decide if raid locations use explicit filler-only placement restrictions or Archipelago excluded-location rules.

## 10. APWorld logic and generation

- [x] Model region/access rules primarily from level cap, expansion access, and explicitly flight-gated checks.
- [x] Keep class abilities, talent points, vouchers, equipment, and legendaries out of mandatory victory logic.
- [x] Ensure raids never hold items required for level-80 victory.
- [x] Ensure each cap upgrade can be reached without needing that same cap upgrade.
- [x] Encode starting regions per faction/class and any critical quest chains or travel links.
- [ ] Use conservative logical level thresholds; physically entering a zone does not mean its checks are completable.
- [x] Support configurable `progression_balancing` and accessibility, and test how excluded raid locations interact with those settings.
- [x] Make item generation deterministic for a given seed and settings (including vendor stock and selected legendaries).
- [x] Validate all supported combinations of race, class, faction, and optional check categories.
- [x] Provide location and item names that are meaningful in AP clients and spoiler logs.

## 11. AzerothCore bridge, persistence & UX

- [x] Implement a reliable bridge from the AzerothCore module to an Archipelago client/protocol connection.
- [ ] Send checks only after confirmed quest turn-in, milestone, exploration, boss defeat, dungeon clear, or raid defeat.
- [x] Persist check sends locally until acknowledged; deduplicate after reconnection.
- [x] Persist received items with unique AP indices; apply exactly once.
- [ ] Surface item receipts, cap upgrades, abilities, vouchers, and legendaries clearly in-game.
- [x] Add simple status commands/UI showing AP connection, slot, level cap, riding unlocks, available vouchers, and remaining checks.
- [x] Safely handle absent bridge, unavailable AP server, server restart, logout, and character deletion.
- [x] Restrict privileged APIs and authenticate bridge communications.

## 12. Testing & release criteria

- [x] Unit-test item-pool counts and classification with all optional check categories.
- [x] Unit-test level cap increments, XP banking, talent reservations, and delayed reward eligibility.
- [x] Generate thousands of seeds and verify logical reachability of the level-80 victory event.
- [x] Verify raids and legendary/voucher rewards never accidentally become mandatory.
- [x] Test both factions and every supported class, including exceptional DK handling.
- [x] Simulate shop inventory generation for thousands of seeds; measure set-piece and full-set distributions.
- [x] Verify 80% independent set-piece rolls produce approximately 16.8% complete 8-piece featured sets before stock-cap effects.
- [ ] Test voucher-price economy for realistic early/mid/late check progression.
- [ ] Test simultaneous purchases, crashes during purchases, full bags, rollback, and reconnect idempotency.
- [x] Test equipping high-level raid gear and directly awarded legendaries at low levels without client errors or server-side exploits.
- [ ] Test normal non-AP equipment still obeys all original item requirements.
- [ ] Test every check type on a live 3.3.5a client, including parties and playerbots.
- [ ] Run a complete solo or playerbot-assisted level-1-to-80 playthrough.
- [ ] Run a real multiworld session with at least one other Archipelago game.

## 13. Open decisions / explicit follow-ups

- [x] Finalize raid boss list and whether raid locations should be filler-only or simply non-required by generation logic.
- [x] Finalize the exact 150 quest / 60 zone / 48 boss / 14 dungeon / 16 level / 12 raid location catalogs.
- [x] Decide whether **level only** victory can occur outside Northrend without changing intended difficulty.
- [x] Finalize Death Knight support (adapted progression or excluded in first release).
- [x] Audit the final per-class major-ability lists; the earlier candidates are not yet validated.
- [x] Confirm whether level restrictions are waived only for gear, **not for riding and ability eligibility** (current recommendation).
- [x] Decide if native vendor UI is essential, or categorized gossip inventory is acceptable for MVP.
- [x] Decide whether inventory entries are visible to other players sharing a server but using separate AP slots (recommended: never).
- [x] Confirm stock 60, featured sets 3, piece inclusion 80%, legendary count 2, and voucher pricing after simulations.
- [x] Define treatment of auction-house and normal high-level item acquisition relative to unrestricted AP-awarded equipment.
- [x] Determine whether to introduce optional special class challenges and equipment/riding progression beyond the v1 logic.

## 14. Suggested implementation order

- [x] **M1 — Connectivity:** APWorld skeleton, slot binding, server-side bridge, receipt/check persistence.
- [x] **M2 — Progression vertical slice:** 10–20 curated checks, level caps 10→20→30, level milestone reporting, victory simulation.
- [x] **M3 — Class systems:** expansion access, riding flags, talent reservations, and one tested class's major abilities.
- [x] **M4 — Shop vertical slice:** one city merchant, deterministic stock, vouchers, purchase persistence, unrestricted AP-only equipment.
- [ ] **M5 — Equipment depth:** featured sets, 60-entry catalog, full class compatibility, other city vendors, direct legendaries.
- [ ] **M6 — Full content:** ~300 checks, all supported classes/factions, dungeons, raids, balance testing.
- [ ] **M7 — Release hardening:** exploit protection, crash recovery, reconnect behavior, multiworld testing, documentation and setup scripts.

---

**Principle:** Archipelago changes the character's progression and occasionally awards spectacular power spikes; it must not make the selected level-80 goal depend on rare gear, specific shuffled class abilities, or mandatory raids.
