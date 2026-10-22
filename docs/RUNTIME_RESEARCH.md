# Native runtime research

Research only. No source changes, configuration, builds, realm mutations, or commits were performed. Read the complete TODO.md, docs/IMPLEMENTATION.md, existing native module and SQL, core AGENTS.md, `.agents/docs/{cpp-guidelines,cpp-scripts,build}.md`, and `modules/how_to_make_a_module.md`. No subsystem docs directory exists in this checkout.

Core root `C = ../wow-test/azerothcore`, shown repository-relative; inspected HEAD `9fb906bb7296212ff42fc95ff73a92aaf8554f0d`. Paths below are relative to C unless explicitly marked project-relative. The working tree has existing modifications in InstanceSaveMgr.h, PlayerbotsScript.cpp, ScriptMgr.h and cs_instance.cpp; this is HEAD plus local changes, not a clean-commit audit. None were changed here. Line numbers describe the inspected working files, not hypothetical upstream APIs. V1 means nine non-DK classes, level 1, cap 10, actual-level-80 victory. New APIs below are proposals, not existing hooks.

## Findings that change the implementation

| Concern | Existing hooks sufficient? | Required change |
| --- | --- | --- |
| XP cap and bank, including one huge award | No | Normalize final XP inside `Player::GiveXP`, use wide arithmetic, bound the level loop and its remainder. |
| Selected spell/riding learning and trainers | No | Pre-mutation veto in `_addSpell`; trainer availability veto before money is charged. Existing cast-check hook supplies a second guard. |
| Talents, turn-in, party kills, zone entry, merchant | Yes | Use the hooks listed below. Dungeon completion needs a catalog-defined clear predicate, not an invented universal completion hook. |
| Every-route expansion access | Partly | Teleport veto exists. Add general map permission at login resolution and map admission; do not mistake dungeon-only admission for continent admission. |
| Per-GUID equipment minimum level | No | Pass instance context into common item requirements and skip only its RequiredLevel comparison. |

Also add a transaction-aware player-save hook for crash-consistent bank/progression state. Existing `OnPlayerSave(Player*)` does not expose the transaction. Transfer protection itself can use existing binding and mail/trade hooks; a root trade veto is optional hardening, not needed for the described issuance policy.

## 1. Existing module and persistence boundary

Project-relative `src/mod_archipelago.cpp:43-52` subscribes only to login. `:101-193` delivers item 118 only; `:212-249` polls pending receipts every five seconds. `FindDestination` at `:76-99` validates space for item 118, not arbitrary gear. Replace that hard-coded entry everywhere, including space checks, item creation, durable verification, queue selection, notification, and SQL. Do not merely change `CreateItem`.

Project-relative `sql/inventory.sql:35-112` owns its transaction, locks reward/character/destination rows, and inserts inventory, receipt and delivery state together. It rejects anything other than item 118. Preserve its commit-before-live-publication ordering and the single DB worker requirement in `src/mod_archipelago.cpp:177-181,204-220`. SQL/protocol 1 is not protocol 2; migrate without resetting receipts or slot history. Project-relative `sql/characters.sql:1-35` has no voucher, authorization, check outbox or bank state yet.

Cache immutable catalog data and binding state by character GUID, never a long-lived Player pointer. Preload binding/state/authorized item GUIDs before spell, talent and inventory loading; `OnPlayerLogin` is too late. `PlayerStorage.cpp:5499-5504` calls InitStatsForLevel before OnPlayerLoadFromDB, then loads spells at `:5544`, talents through InitTalentForLevel at `:5573`, inventory at `:5581`. A startup-loaded binding cache plus on-demand loading keyed by the already assigned GUID works without another early-load hook. Unknown state for a known binding must not silently become unrestricted gameplay. Future bindings must enter this cache before login.

`PlayerStorage.cpp:7221-7284` has these existing signatures:

```cpp
void Player::SaveToDB(bool create, bool logout);
void Player::SaveToDB(CharacterDatabaseTransaction trans, bool create, bool logout);
```

The first delegates to the second; `OnPlayerSave(this)` at `:7253` receives no transaction. Propose `void OnPlayerSaveToDB(Player*, CharacterDatabaseTransaction, bool create, bool logout)` inside the transactional overload, adjacent to `_SaveCharacter(create, trans)`. Append bank, release state and pending level/check outbox rows to that same transaction. Do not issue an independent bank UPDATE from OnPlayerSave. A cap receipt, bank release, character XP and applied-index mark must commit together. Keep pending state until commit outcome is known; ambiguous results require reload/stop, not a second live grant. Module delivery can use `player->SaveToDB(trans, false, false)` in its ordered commit path. Never nest the current self-committing stored procedure inside a supposed enclosing transaction.

## 2. XP, cap crossing and actual victory

Existing signatures and hook locations:

```cpp
void Player::GiveXP(uint32 xp, Unit* victim, float group_rate = 1.0f, bool isLFGReward = false);
void Player::GiveLevel(uint8 level);
void OnPlayerGiveXP(Player*, uint32& amount, Unit* victim, uint8 xpSource);
bool OnPlayerCanGiveLevel(Player*, uint8 newLevel);
void OnPlayerLevelChanged(Player*, uint8 oldLevel);
void OnPlayerSetMaxLevel(Player*, uint32& maxPlayerLevel);
```

Evidence: `Entities/Player/Player.cpp:2404-2476,2480-2585,2624-2626`; declarations `Scripting/ScriptDefines/PlayerScript.h:267,296,485,819`. Important: GiveXP does NOT call OnPlayerGiveXP internally. Its callers do. GiveXP then applies favored-zone XP and rested/RaF bonuses. An early module clamp is therefore wrong. OnPlayerSetMaxLevel changes PLAYER_FIELD_MAX_LEVEL during stats initialization, not GiveXP's local `maxLevel`, which comes from world/trial config at `:2430-2437`.

Required patch proposal: `void OnPlayerBeforeApplyXP(Player*, uint64& totalXP, uint32& maxLevel)` after all XP multipliers and bonus computation, before final XP application and the max-level return relevant to this new limit. Keep existing source hooks in place; do not call them twice. The module lowers maxLevel to `min(world/trial maximum, AP cap)` and normalizes totalXP. Handle an already capped AP character here so its award can reach the bank. Do not globally suppress XP with NO_XP_GAIN, which returns at `:2412` before banking.

For effective cap C below 80, compute in uint64:

```text
room = sum(GetXPForLevel(L), L=currentLevel..C-1) - currentXP
       or 0 if already at C
accepted = min(finalAward, room)
overflow = finalAward - accepted
bank = min(bank + overflow, floor(GetXPForLevel(C) / 2))
```

Only use the subtraction below C and with valid XP state. Reaching the cap leaves PLAYER_XP=0; overflow goes to the bank, never to an uncapped PLAYER_XP field. At 80, discard excess and do not bank. Cap receipt raises C, updates PLAYER_FIELD_MAX_LEVEL and releases the old bank once into ordinary XP, then clears it. Because the old cap held XP=0 and the bank is at most half the old cap's next-level cost, release can set that ordinary XP directly without another level-up or multiplier pass. Save release and receipt atomically. Do not call normal GiveXP on the bank and apply favored/rested XP again.

Core must use uint64 for multiplier/bonus intermediates, including `2 * xp` RaF, `curXP + xp + bonus_xp`, the loop remainder and threshold sums. Promote before multiplication/addition; a later cast cannot repair prior uint32 overflow. In the level loop, stop if GiveLevel did not advance the actual level. Today a veto at `:2486` makes the loop continue subtracting thresholds while level stays unchanged. Merely vetoing level 11 can consume huge XP or leave nonsense XP. Log only accepted XP with representable packet fields. Preserve normal non-AP behavior except the overflow/no-progress safety fix.

Use OnPlayerCanGiveLevel as a defense for direct level grants. Milestones and victory use OnPlayerLevelChanged and `GetLevel()`, never cap count. Emit all crossed 5-level milestones, not only a final multiple. Reconcile actual level on relog, but only publish durable milestone/victory outbox state. Reaching 80 outside Northrend is valid. Receiving cap 80 while level 70 is not victory. No useful item, ability, raid or continent flag enters this predicate.

Direct GiveXP callers are `PlayerQuest.cpp:773`, `KillRewarder.cpp:185`, `Player.cpp:5992` exploration and `:6399` battleground. GiveLevel callers include `Player.cpp:2469`, `Handlers/ReferAFriendHandler.cpp:85`, `scripts/Commands/cs_character.cpp:256`, and bot factory level changes. Bots have a separate `XpGainAction::GiveXP` at `modules/mod-playerbots/src/Ai/Base/Actions/XpGainAction.cpp:56`, not a call to Player::GiveXP. Do not apply the human binding policy to that bot path.

## 3. Selected abilities, internal learning and riding

The existing `void OnPlayerLearnSpell(Player*, uint32 spellID)` runs AFTER `addSpell` succeeds in `Player.cpp:3423-3426`. Unlearning there is not a safe veto. It can leave triggered effects, skill changes or paid training. `learnSpell` also restores ranks and dependent spells at `:3434-3449`.

The common mutation root is:

```cpp
bool Player::_addSpell(uint32 spellId, uint8 addSpecMask, bool temporary, bool learnFromSkill = false);
bool Player::addSpell(uint32 spellId, uint8 addSpecMask, bool updateActive,
                      bool temporary = false, bool learnFromSkill = false);
void Player::learnSpell(uint32 spellId, bool temporary = false, bool learnFromSkill = false);
```

Propose `bool OnPlayerCanAddSpell(Player*, uint32 spellId, uint8 specMask, bool temporary, bool learnFromSkill)` after SpellMgr validation in `_addSpell`, BEFORE packets, map insertion, passive casts or SetSkill. Default true. See `Player.cpp:3234-3380`. Apply only to catalog-selected independent spell chains and riding-training spells; never generalize this into a ban on temporary talent/form/override spells.

Audit chain membership through `sSpellMgr->GetFirstSpellInChain`, `GetPrevSpellInChain`, `GetNextSpellInChain` and catalog `ranks`. An unlocked chain is still subject to each rank's audited trainer level, required skill and prerequisite spells. Do not use `learnSpellHighRank`, which recursively grants every later rank (`Player.cpp:13983-13989`). Early rewards remain pending; level changes and login reconcile them. Grant eligible base ability on receipt, allow normal eligible rank training thereafter. Any automatic eligible-rank grant needs the same audited per-rank conditions, not just SpellInfo::SpellLevel. Exclude talent prerequisites and baseline forms/stances/pets per the implementation contract.

Trainer root has NO existing module veto:

```cpp
Trainer::SpellState Trainer::Trainer::GetSpellState(Player const*, Trainer::Spell const*) const;
bool Trainer::Trainer::CanTeachSpell(Player const*, Trainer::Spell const*) const;
void Trainer::Trainer::TeachSpell(Creature*, Player*, uint32 spellId);
```

See `Entities/Creature/Trainer.cpp:133-210`. Propose `bool OnPlayerCanTrainSpell(Player const*, uint32 trainerSpellId)` in GetSpellState before returning Available. It must inspect SPELL_EFFECT_LEARN_SPELL trigger IDs as well as the trainer spell ID. This keeps list status and purchase eligibility consistent. TeachSpell checks CanTeachSpell at `:92` before ModifyMoney at `:106`; root learning veto alone would charge money and report success. Trainer list/purchase enter through `Handlers/NPCHandler.cpp:94-135`. Preserve all normal class/race, skill, prerequisite, rank, money and trainer requirements.

Existing secondary enforcement is `void AllSpellScript::OnSpellCheckCast(Spell*, bool strict, SpellCastResult& res)` at `Scripting/ScriptDefines/AllSpellScript.h:57`, invoked `Spells/Spell.cpp:5675`. Deny unauthorized selected ability casts and unauthorized riding-training/skill-grant casts here. Do not overwrite an existing failure with success. This also gives a mount-use guard without SQL bindings for every mount spell. Identify riding skill-step/skill effects and mounted/flying auras from spell data, including class mounts and flight forms; allow unrelated quest vehicles and temporary transport effects explicitly rather than treating all speed auras as riding.

Riding source data: `data/sql/base/db_world/trainer_spell.sql:2463-2471` records apprentice 33388 level 20, journeyman 33391 level 40, expert 34090 level 60, artisan 34091 level 70, cold weather 54197 level 77. Riding skill is 762. Skills require 0/75/150/225 and cold weather 225 respectively. These are shipped base rows, not proof of the currently imported DB revision.

Grant training through `player->learnSpell(trainingSpell)` after AP flag, level and prior riding eligibility checks. `_addSpell` handles SPELL_EFFECT_SKILL_STEP by casting it and returning false (`Player.cpp:3329-3333`), so do not interpret a false add result or absence of a learned-spell packet as failure. Verify `GetPureSkillValue(SKILL_RIDING)` / actual spell state. Early artisan must wait for expert; cold weather requires expert, not artisan. Do not charge trainer fees for AP delivery.

Use `bool OnPlayerCanFlyInZone(Player*, uint32 mapId, uint32 zoneId, SpellInfo const* bySpell)` (`PlayerScript.h:762`, `Player.cpp:13963-13980`) to require the applicable AP flags and normal eligibility. Keep core location checks: `SpellInfo.cpp:1520-1533` tests AreaTable::IsFlyable and no-fly zones; ordinary EK/Kalimdor remain non-flyable. Ground mount use must likewise require unlocked eligible tiers. Handle Druid flight and racial/class mount skill grants so normal training cannot recreate an unowned riding permission. Riding's OnPlayerSetSkill hook is post-change and not a veto (`PlayerScript.h:800`); use cast/trainer prevention and login reconciliation, not recursive correction in that callback.

## 4. Talents and dual spec

Use `void OnPlayerCalculateTalentsPoints(Player const*, uint32& talentPointsForLevel)` at `PlayerScript.h:237`; implementation `Player.cpp:13938-13960`. Pin Rate.Talent=1 and no extra bonus talents for supported runs, or explicitly reject incompatible configuration. The hook runs BEFORE RATE_TALENT multiplication. DK quest talent logic is out of v1.

For level L, let E be the number of reservation levels 15,20,...,70 already reached and U the number of AP talent unlocks, capped at 12. Set total available earned points to `max(0,L-9) - E + min(U,E)`, bounded by normal level allowance and 71. Do not add AP points on top of 71 or subtract reservations twice. Early U is banked naturally.

Call `InitTalentForLevel()` after eligible receipts. It calculates total, compares spent count, and derives free count at `Player.cpp:2593-2614`. Respec recalculates the same function at `:3875`, and ActivateSpec counts the new spec's spent talents then calls InitTalentForLevel at `:15635-15636`. Loading does so at `PlayerStorage.cpp:5573`. No dual-spec patch is needed. Existing talent tier/spend/dependency checks in `Player::LearnTalent(uint32,uint32,bool command=false)`, `Player.cpp:14268-14366`, remain intact. OnPlayerCanLearnTalent is available for defense, not required to implement the total. OnPlayerTalentsReset fires before the reset and must not serve as a post-reset recalculation callback.

## 5. Expansion access on every route

`Player::TeleportTo(uint32,float,float,float,float,uint32 options=0,Unit* target=nullptr,bool newInstance=false)` is the shared route root (`Player.cpp:1401`, `Player.h:1107-1110`). Existing hook:

```cpp
bool OnPlayerBeforeTeleport(Player*, uint32 mapid, float x, float y, float z,
                            float orientation, uint32 options, Unit* target);
```

It runs at `Player.cpp:1498`, even for TELE_TO_GM_MODE. It is late: taxi/vehicle cleanup, transport detachment, movement/aura changes and duel loss occur at `:1456-1496`. Module-only rejection prevents arrival but does not undo those changes. Prefer a new early general permission hook rather than moving a hook whose existing consumers may depend on its timing:

```cpp
bool OnPlayerCanAccessMap(Player const*, uint32 mapId,
                         WorldLocation const* destination, bool loginCheck); // proposed, default true
```

Call it with the destination location after valid map lookup and before teleport side effects. Login supplies its resolved location. Also call it with destination=nullptr in `MapMgr::PlayerCannotEnter(uint32,Player*,bool)` before the non-dungeon and GM returns (`Maps/MapMgr.cpp:136-177`). Keep the old dungeon hook unchanged. `OnPlayerCanEnterMap(Player*, MapEntry const*, InstanceTemplate const*, MapDifficulty const*, bool)` is dungeon-only today. Do not move it above the early return with null arguments and break existing modules.

Login does not go through TeleportTo. Add the general permission check to `Player::LoadFromDB(ObjectGuid, CharacterDatabaseQueryHolder const&)` after resolving saved/transport/taxi map and before creating/adopting that map (`PlayerStorage.cpp:5275-5415`). If denied, clear transport passenger state and saved taxi, discard any already selected map pointer/instance ID, relocate to an explicitly permitted safe starting location, and validate that fallback too. A locked homebind is not a safe fallback. Transport code can create a map before this point, so ensure the final adopted map, not merely the original saved map ID, is checked. `CheckInstanceLoginValid()` at `PlayerStorage.cpp:7123-7149` returns early on world maps. `CharacterHandler.cpp:911` adds the player before that check. OnPlayerLogin at `:1131` cannot be the sole protection.

Route evidence into TeleportTo: portals/teleport spells `Spells/SpellEffects.cpp:1203,1238`; summons `Player.cpp:12704`; resurrection `:13122`; graveyard/homebind `:5034,5046`; taxi cross-map `Handlers/TaxiHandler.cpp:237` and `Player.cpp:10579`; boats/zeppelins `Entities/Transport/Transport.cpp:702,706`; area triggers `Handlers/MiscHandler.cpp:807`; LFG `DungeonFinding/LFGMgr.cpp:2291`; SmartAI `AI/SmartScripts/SmartScript.cpp:1712`; script teleports `Scripting/MapScripts.cpp:489`; GM tele/summon in `scripts/Commands/cs_{tele,go,misc}.cpp`. Denied transport crossing must detach/reset both passenger structures and land the character safely on the departure side; transport currently erases failed passengers at `Transport.cpp:706-707` without itself supplying that landing. Test logout aboard a moving boat.

Use a catalog-audited map/zone policy, NOT `Expansion()!=0` as an Outland test. Map 530 also contains Blood Elf/Draenei starting areas and their cities, which must remain ordinary Azeroth travel. Partition 530 by destination zone/coordinates; include its dungeons and all Northrend instances through explicit catalog map classification. MapEntry expansion remains the client's entitlement, not the AP regional permission. For map 530 resolve the supplied destination with `Map::GetZoneAndAreaId(uint32 phaseMask,uint32& zoneid,uint32& areaid,float x,float y,float z) const` (`Maps/Map.h:256`) on `sMapMgr->CreateBaseMap(mapId)`. A null destination permits mixed map 530 at map-only admission; teleport/login must perform the position-aware decision before arrival. Unknown target area must fail closed for the bound human rather than unlocking all of map 530. Recheck zone transitions through OnPlayerUpdateZone/Area, but an after-entry correction is defense, not the whole gate. Playerbot teleports must not transport a locked human along with them.

## 6. Curated checks and human party credit

| Check | Existing API and evidence | Rule |
| --- | --- | --- |
| Quest turn-in | `void OnPlayerCompleteQuest(Player*, Quest const*)`, PlayerScript.h:249; `PlayerQuest.cpp:903` | This checkout calls it at the END of RewardQuest, after SetRewardedQuest at :849 and SaveToDB at :884. Correct despite its name. Never report merely QUEST_STATUS_COMPLETE at :623. |
| Boss / raid | `void OnPlayerRewardKillRewarder(Player*, KillRewarder*, bool isDungeon, float& rate)`, PlayerScript.h:518; KillRewarder.cpp:229 | Per eligible group member before XP, including gray kills. Use `rewarder->GetVictim()` and GetKiller(), validate creature/map/difficulty and participant rule. Do not modify rate. |
| Zone entry | `void OnPlayerUpdateZone(Player*, uint32 newZone, uint32 newArea)` and `OnPlayerUpdateArea(Player*, uint32 oldArea,uint32 newArea)`, PlayerScript.h:361,364 | IMPLEMENTATION defines entering a zone, not full exploration. Use the supplied new IDs. Guard loading, invalid maps, dead/flight policy and access. Reconcile actual zone after login. |
| Dungeon clear | `void GlobalScript::OnAfterUpdateEncounterState(Map*, EncounterCreditType, uint32 creditEntry, Unit* source, Difficulty, DungeonEncounterList const*, uint32 dungeonCompleted, bool updated)`, GlobalScript.cpp:77 | Optional corroboration for configured encounter credit. Catalog boss-set tracking is required for legacy dungeons and participant eligibility. |
| Level / victory | OnPlayerLevelChanged plus durable reconciliation | Actual level only, as above. |

`KillRewarder.cpp:266-291` iterates group members with `IsAtGroupRewardDistance(victim)` even if dead; `_RewardKillCredit` at `:205-212` narrows quest credit to alive or without corpse for group members. Reuse that latter predicate for curated kill credit if choosing normal quest-like party rules. `_RewardPlayer` at `:215-246` invokes the hook even when XP=0. Require creature victim, PvE, correct map/difficulty, bound human participant and this eligibility. Its isDungeon argument is false for a solo kill at `:325`, so derive map type from victim->GetMap(), not that boolean alone. Do not require XP gain or a killing blow. Permanent dedup is by binding/location, not by spawn.

`OnPlayerCreatureKill` and pet-kill hooks (`Unit.cpp:14306,14105`) are killing-blow notifications, not authoritative party eligibility. `KilledMonsterCredit` is a quest-objective mechanism with aliases and scripted calls (`PlayerQuest.cpp:2001-2030`), not proof a curated boss actually died.

Dungeon clear proposal: all catalog boss_ids killed on the permitted map/difficulty in the same instance/reset epoch, with the human eligible at every required kill. Persist participant boss bits and instance/reset identity; report once per binding after the final required bit. This is an explicit full-clear definition, not merely killing a final boss or accumulating unrelated runs. If a catalog chooses another rule, encode it explicitly and test it. Multi-phase/alias boss entries need per-dungeon evidence before use.

`Map.cpp:2929-2972` returns without a hook when DungeonEncounterList is absent; `dungeonCompleted` means a lastEncounterDungeon match, not necessarily every boss defeated. `InstanceScript::SetBossState(uint32,EncounterState)` calls OnBeforeSetBossState BEFORE loading/duplicate/alive-minion rejection (`InstanceScript.cpp:400-424`). Reporting DONE from that pre-hook would award false clears. A deferred read of committed state can corroborate, but the catalog kill-set approach needs no SetBossState patch. Non-kill completion events must be curated separately, never guessed from every DONE value.

### Playerbots without bot-owned human AP bindings

Playerbots API: `modules/mod-playerbots/src/Script/Playerbots.h:31` defines GET_PLAYERBOT_AI through `sPlayerbotsMgr.GetPlayerbotAI(Player*)`; implementation `Bot/PlayerbotMgr.cpp:1782-1800`. `PlayerbotAI::GetMaster()` is in `Bot/PlayerbotAI.h:540`. `IsRealPlayer(Player*)` at `Bot/PlayerbotAI.cpp:4410-4415` means non-null and no AI, including exclusion of selfbots. `WorldSession::IsBot()` is also used by the bot XP hook at `Script/Playerbots.cpp:267-292`.

Recipient policy: a human AP binding AND not a bot session AND no attached bot AI. Do not infer humanity from an AP binding, account ID, real-looking name, or being group leader. Use a tiny module-local adapter when playerbots is present; without it, session bot exclusion is the fallback. Do not add a playerbots dependency to core. Automated selfbots are not release evidence for a human-controlled client unless explicitly separately labeled.

A bot may be the loot/tag killer. KillRewarder still iterates the actual nearby human group members. Credit those humans from their own per-recipient callback, even though the killer has no AP binding. Never reject the entire event because the killer is unbound, and never forward every bot quest/zone/level event to its master. Quests require the human's own confirmed turn-in; exploration requires the human's position; clear bits require the human's own eligibility. Two humans in one bot-assisted party can each get their own location exactly once. Bot-only parties, offline masters and out-of-range humans receive nothing.

## 7. Instance-specific equipment authorization

Existing roots:

```cpp
InventoryResult Player::CanUseItem(Item* pItem, bool not_loading = true) const;
InventoryResult Player::CanUseItem(ItemTemplate const* proto) const;
InventoryResult Player::CanEquipItem(uint8 slot, uint16& dest, Item*, bool swap,
                                    bool not_loading = true) const;
```

`PlayerStorage.cpp:2322-2376` validates alive/ownership, calls the template overload, then checks actual weapon/armor proficiency and reputation. `:2378-2438` checks faction, class/race, required skill/rank, required spell, required LEVEL, holiday and module veto. `OnPlayerCanUseItem(Player*,ItemTemplate const*,InventoryResult&)` at `:2432` runs AFTER the level rejection at `:2419-2422` and has no instance. OnPlayerCanEquipItem at `:1912` can only deny, not override subsequent validation. Neither hook can safely implement this exemption.

Small patch: preserve both public signatures. Extract the template validator into a private overload `InventoryResult CanUseItem(ItemTemplate const* proto, Item const* instance) const`; public template calls it with nullptr, instance overload calls it with pItem. Add proposed `void OnPlayerCheckItemLevel(Player const*, Item const*, bool& ignoreRequiredLevel)` only at the RequiredLevel branch, initialized false. Require matching template, owner and durable `(seed/team/slot/character GUID,item GUID)` authorization before setting true. Template-only callers, including ammo and bot loot appraisal, remain ordinary. Do NOT catch EQUIP_ERR_CANT_EQUIP_LEVEL_I and return OK from CanEquipItem: that skips later holiday, proficiency and reputation checks.

Load authorization before `_LoadInventory`. It calls CanEquipItem with not_loading=false at `PlayerStorage.cpp:5998` and mails failed items at `:6056`; login-only authorization would wrongly unequip/mail the reward. Do not use OnPlayerCheckItemInSlotAtLoadInventory to bypass the entire equipment validator.

Keep item entry, ItemSet, stat fields, proc spells and visuals intact. Stat application `_ApplyItemMods` at `Player.cpp:6744-6778`, set effects `Entities/Item/Item.cpp:33-116`, combat procs `Player.cpp:7453-7495` already use the original template. No blanket proc/SpellLevel lowering. Preserve normal enchantment and socket requirements: `PlayerStorage.cpp:4425-4429` independently blocks enchantments below their own requiredLevel/skill; the task waives ITEM RequiredLevel only. Measure resulting low-level effects, including proc scaling and set activation, on the real client/server rather than promising all high-level enchants become active.

### Transfer prohibitions without another core patch

Issue every AP item with `Item::SetBinding(true)` (`Item.h:235`), no BOP-trade window, and no refundable state. Existing cleanup APIs are `ClearSoulboundTradeable(Player*)` and `SetNotRefundable(Player*,bool changestate=true,CharacterDatabaseTransaction* trans=nullptr)` (`Item.h:343,357`); do not open a loot trade window during issuance. Retain authorization outside its current inventory position. Ordinary drops with the same entry have no authorization. `Item::CanBeTraded(bool mail=false,bool trade=false) const` at `Item.cpp:795-820` blocks soulbound gear, but mail has an account-wide exception and trade has a BOP-window exception.

Use existing `bool OnPlayerCanSetTradeItem(Player*,Item*,uint8 tradeSlot)` (`PlayerScript.h:638`, `TradeHandler.cpp:915`) to reject AP items in all trade slots, including non-transferred enchant slots if interpreting the prohibition strictly. Use `bool OnPlayerCanSendMail(Player*,ObjectGuid receiver,ObjectGuid mailbox,std::string& subject,std::string& body,uint32 money,uint32 COD,Item*)` (`PlayerScript.h:512`, `MailHandler.cpp:281`) to reject AP attachments even on the same account. Normal mail, trade, auction listing and guild-bank deposits also consult CanBeTraded. Soulbound, non-BOP-tradable AP items therefore cannot be auctioned or deposited in guild banks. A root proposed `bool OnItemCanBeTraded(Item const*,bool mail,bool trade)` is optional fail-closed defense if other modules can alter binding; it is not an existing hook.

Audit other transformations too: vendor sale/buyback, wrapping, refund, item replacement and destruction must never mint authorization for a different GUID or permit cross-character recovery. Use existing `bool OnPlayerCanSellItem(Player*,Item*,Creature*)` (`PlayerScript.h:510`, `Handlers/ItemHandler.cpp:604`) to reject AP vendor sales, avoiding a buyback transfer/recovery path. No authorization by item entry, creator GUID alone, or purchased-stock flag. Bank storage on the same character is allowed. On deletion archive binding/receipt history using OnPlayerDeleteFromDB's transaction (`PlayerScript.h:522`), not cascading away history.

## 8. Real client equipment and on-use fallback

Server evidence, not a claim about disassembled client behavior: `Handlers/ItemHandler.cpp:389-432` answers CMSG_ITEM_QUERY_SINGLE by ITEM ENTRY and sends RequiredLevel from the template. It has no per-instance minimum-level field. A modified server validator cannot force the stock client to submit a right-click/drag equip request. No real client equipment test was performed in this research.

Reliable equipment fallback that does not spoof item templates: personal gossip or `.archipelago equip <owned item GUID> <equipment slot>` resolves the player's actual item, checks AP authorization and the allowed destination, then calls `Player::SwapItem(uint16 src,uint16 dst)` (`Player.h:1375`, `PlayerStorage.cpp:3632 onward`). That existing path runs CanEquipItem/CanUnequipItem, storage/swap, combat, unique and offhand validation. Never call EquipItem/QuickEquipItem directly to dodge checks. A normal chat/gossip request reaches the server independently of the client's local item-equip precheck. Allow re-equipping already purchased AP equipment, not only equipping at initial delivery. Test two ring/trinket slots and full-bag swaps.

For ON-USE effects, an equip command alone is insufficient if the client also refuses UseInventoryItem. Expose a separate authorized item-use command through the same addon/chat interface. Reuse `WorldSession::HandleUseItemOpcode(WorldPacket&)` (`WorldSession.h:951`) with a server-constructed packet from the owned item and current player-selected target, rather than casting the item's spell with TRIGGERED_FULL_MASK. Layout is `bag:uint8,slot:uint8,castCount:uint8,spellId:uint32,itemGUID:uint64,glyphIndex:uint32,castFlags:uint8`, then `SpellCastTargets::Write(ByteBuffer&)` (`Spell.h:127,136`). Use a valid zero glyph index and no client movement/cast flags; select only actual item ON_USE spells. Resolve all IDs and targets server-side, apply authorization/rate limits, and test queuing/cooldowns and target requirements. If integrating this into production, extracting a validated handler helper avoids packet construction but requires an additional small core refactor.

`SpellHandler.cpp:58-206` enforces mover state, owned slot/GUID, equipped status, CanUseItem, arena/combat restrictions, binding, targets and OnItemUse before CastItemUseSpell. `Player.cpp:7585-7671` alone does NOT reproduce all those checks. Calling it directly from chat without the handler checks is unsafe. Do not promise arbitrary ground-targeted item use until the command supplies its valid destination targeting; catalog-test supported on-use equipment and extend targeting as required rather than silently dropping the feature.

Do not globally lower item_template.RequiredLevel. Per-player query spoofing is also entry-scoped, changes ordinary copies' client display and depends on cache invalidation. Alternate templates change original identity and complicate sets/procs, contrary to the chosen approach. The command fallback keeps the unmodified client and original item identity. A client addon may provide buttons/chat, but cannot be assumed to override protected native equipment checks.

## 9. Private city merchant and other rewards

Existing merchant APIs:

```cpp
bool CreatureScript::OnGossipHello(Player*, Creature*);
bool CreatureScript::OnGossipSelect(Player*, Creature*, uint32 sender, uint32 action);
void ClearGossipMenuFor(Player*);
void AddGossipItemFor(Player*, uint32 icon, std::string const& text, uint32 sender, uint32 action);
void SendGossipMenuFor(Player*, uint32 npcTextID, ObjectGuid const& guid);
void CloseGossipMenuFor(Player*);
```

Declarations `CreatureScript.h:33-36`, `AI/ScriptedAI/ScriptedGossip.h:85-101`; dispatch `Handlers/NPCHandler.cpp:137-203`. Spawn one custom ScriptName-bound gossip creature in every supported major city for both factions. The shared personal stock comes from binding/catalog data, not npc_vendor rows. Paginate/categories for all 60 entries, include unbought prices from level 1, voucher balance and total remaining cost. Never broadcast or put personal stock into shared creature state.

Selection is untrusted. Resolve the menu action to this player's stable stock entry; recheck NPC interaction, seed/binding, entry, sold status and balance regardless of previously sent menu. A row-locked purchase commits debit, sold marker, item GUID authorization, inventory rows and receipt once before live publication. Full bags leave everything unspent. Deterministic featured sets, independent 80% piece rolls, price totals, class/proficiency compatibility and named legendaries belong to the shared catalogs/APWorld, not separate C++ randomness. All city instances read the same durable stock.

Direct legendaries use the same safe delivery/authorization path without a merchant. Bag upgrades, gold and consumables need their own received-index effects; do not mark them applied merely because a chat notification was sent. For gold, save character money and receipt together and bound against the core gold cap. For bag upgrades, use existing storage/equip checks and never overwrite a nonempty bag. Queue offline/full-bag rewards and derive scaling from the recorded application policy. Voucher arithmetic remains 204 across 88 receipt items. All remain useful/filler and cannot gate level victory.

The complete scope still includes protocol authentication/outbox ACK/replay, catalog/live-data validation, all legal faction/class/race profiles, deterministic seed stock/legendaries, the exact pool/filler adjustment, 300 baseline definitions, optional filler-only raids and the TODO release gates. This note does not claim those data/bridge/APWorld tasks implemented or verified.

## 10. Caller audit for shared validation roots

Searched C/src plus the installed playerbots and enchanter source trees, including headers and direct internal calls. The sets below are why a root change is required. Unrelated same-name Pet, Ticket, Item, InstanceScript and PlayerbotAI methods are not Player methods. Existing module callers inherit default behavior unless explicitly AP-bound humans.

| Root | All direct production core call sites, excluding definitions/declarations |
| --- | --- |
| Player::GiveXP | PlayerQuest.cpp:773; KillRewarder.cpp:185; Player.cpp:5992,6399. |
| Player::_addSpell | Player.cpp:3121 talent effect, :3149 addSpell, :3267 nested temporary learn; Spells/Auras/SpellAuraEffects.cpp:2278 form spells, :5885 override spells. |
| Trainer::GetSpellState | Trainer.cpp:67 list and :135 CanTeachSpell. |
| Trainer::CanTeachSpell | Trainer.cpp:92 purchase; scripts/Commands/cs_learn.cpp:141; playerbots `Ai/World/Rpg/Action/RpgSubActions.cpp:300`, `Bot/Factory/PlayerbotFactory.cpp:3248`, `Ai/Base/Actions/TrainerAction.cpp:112`, `Ai/Base/Value/BudgetValues.cpp:122`. |
| Player::CanUseItem | PlayerStorage.cpp:940 BotCanUseItem template, :1973 equip instance, :2179 bank instance, :2340 instance-to-template bridge, :2582 ammo template; Handlers/SpellHandler.cpp:146 item use; Handlers/ItemHandler.cpp:559 item reading. |

Playerbot instance CanUseItem callers: `Bot/PlayerbotAI.cpp:6122`; `Ai/Raid/TK/TKActions.cpp:1728,1741,1754,1762`; `Ai/Raid/SSC/SSCActions.cpp:2611`; `Ai/Raid/ICC/Action/ICCActions_SG.cpp:502`, `ICCActions_GSB.cpp:857`; `Ai/Base/Actions/GenericSpellActions.cpp:525`, `UseItemAction.cpp:68`. Template callers remain ordinary: `Bot/PlayerbotAI.cpp:5114,5444,5459`; `Mgr/Item/ItemVisitors.cpp:12`; `Ai/Base/Value/ItemUsageValue.cpp:79,143,904`; `Ai/Base/Actions/{GiveItemAction.cpp:34,BuffAction.cpp:19,GenericSpellActions.cpp:170,TrainerAction.cpp:480}`. The bot AI duplicates CanEquipItem but still calls the instance CanUseItem root.

All CanBeTraded direct callers: `Handlers/{AuctionHouseHandler.cpp:216,MailHandler.cpp:256,TradeHandler.cpp:307,325,896}`, `Guilds/Guild.cpp:776`, `TC9Sidecar/TC9GrpcHandler.cpp:69`; playerbots `Ai/Base/Actions/{TradeValues.cpp:32,TradeAction.cpp:72}` and `Ai/World/Rpg/Action/RpgSubActions.cpp:389`. NONTRADED trade slot skips CanBeTraded but reaches OnPlayerCanSetTradeItem. This is why the separate trade hook matters.

All PlayerCannotEnter direct callers: `Handlers/MiscHandler.cpp:770`, `Player.cpp:1563`, `PlayerStorage.cpp:7149`. All preserve existing downstream instance checks. TeleportTo's coordinate overload is also reached by its inline WorldLocation wrapper at `Player.h:1108-1110`; full route families and representative callers are documented above. No caller-specific expansion patches are needed once the destination root and saved-login route are fixed.

For the transaction-aware SaveToDB hook, relevant core Player callers include `Globals/ObjectAccessor.cpp:292`, `Server/WorldSession.cpp:830,1649`, `Handlers/{CharacterHandler.cpp:577,MailHandler.cpp:344,AuctionHouseHandler.cpp:326,400}`, `Entities/Player/{Player.cpp:1691,4745,12768,PlayerUpdates.cpp:331,2446,PlayerQuest.cpp:884,PlayerStorage.cpp:6206,6256,7225,7532,7557}`, player command saves and playerbot saves. Callers that supply an existing transaction must retain ownership of its commit. Do not hook similarly named Item/Pet/InstanceScript SaveToDB methods.

## 11. Verification plan, not verification evidence

1. Pin and record the effective source diff, imported DB revision, extracted DBC/client build 12340, module revisions and realm settings. Project `tests/Dockerfile:10` pins a DIFFERENT upstream revision, d5e818f; its old object compile is not evidence against 9fb906 or a linked playerbots worldserver. The adjacent realm README says bots are absent despite playerbots source being present. Verify loaded modules in worldserver startup logs before claiming bot coverage. No build/run was requested here.

2. On isolated fixtures, cover exact cap crossing, multi-cap-sized award, UINT32_MAX award, rested/RaF/favored-zone bonus, repeated awards at cap, capped bank saturation, crash before/after release, relog and every XP source. Assert no level above cap, no phantom milestones and no victory on cap receipt. Exercise spell trainer wrapper/ranks, quest learn effects, restored spells, early riding rewards/class mounts and no-fly areas. Test talents before/after each reservation, all 12 early unlocks, 71 at 80, paid/free respec and both specs. Fault tests require transaction rollback and receipt replay, not just happy-path assertions.

3. Use an unmodified 12340 GUI client for low-level ordinary versus AP copies of the same entry, right-click/drag/command re-equip, stats/set/proc/on-use, full bags, offhand/unique/class/proficiency rejection, enchants/gems, trade/mail same-account/AH/guildbank and relog while equipped. Record whether the stock client emitted equipment/use requests before implementing any client workaround claims. Test travel matrix for portal, summon, boat/zeppelin, taxi, hearth/resurrection, LFG, saved login/transport and starter cities in map 530. Repeat each denied route after its AP unlock to demonstrate it works.

4. Complete a real human-controlled level-1-to-80 run using ordinary questing, exploration, combat and dungeon bosses, with same-level playerbot assistance if desired. No .levelup, .quest complete, kill commands, synthetic location reports, bot factory leveling or direct XP writes on this character. Baseline rates and bot levels must be recorded; no level-80 carry group as a substitute for intended leveling. AP rewards must come from the generated seed and acknowledged checks. Record level/cap/bank at every band, quest IDs, party membership/credit, clear bits, receipts, restart/reconnect checkpoints and actual level-80 event. If a seed cap-blocks ordinary play, fix logic/content rather than inject an unlock. A complete run is a multi-session playthrough, not a headless smoke test. `tests/realm_client.py:1-10` explicitly has no movement/gameplay emulation.

5. Separate from that one playthrough, exercise both factions and all nine supported classes and every live check category, bot killing blow/pet/gray kill/dead/range/two-human/no-human groups, persistence failures and simultaneous purchases. Run a real multiworld containing at least one other game, demonstrate cross-game item delivery/check ACK/victory and restart recovery. Keep seed-generation reachability/distribution/economy simulations and live DB catalog validation as separate required artifacts. Do not mark TODO release gates complete from this source research or a scripted level-80 simulation.

Next implementation action: agree the new hook contracts and the position-aware map-530 policy before editing core. Runtime, client behavior, live DB correctness and full playthrough remain unverified.
