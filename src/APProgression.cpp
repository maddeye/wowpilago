#include "APProgression.h"
#include "APCatalog.h"
#include "Config.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "DataMap.h"
#include "Errors.h"
#include "InstanceSaveMgr.h"
#include "Item.h"
#include "KillRewarder.h"
#include "Log.h"
#include "Map.h"
#include "MapMgr.h"
#include "ObjectMgr.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "QuestDef.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "World.h"
#include "WorldSession.h"

#ifdef MOD_PLAYERBOTS
#include "PlayerbotMgr.h"
#define WOWPILAGO_PLAYERBOTS 1
#endif

namespace WoWPilago
{
namespace
{
struct Cache final : DataMap::Base
{
    bool initialized = false;
    bool bound = false;
    bool savePending = false;
    State state;
};

Cache* PlayerCache(Player const* player)
{
    // Map workers own each player's gameplay; the world tick joins them before effect application.
    return const_cast<Player*>(player)->CustomData.GetDefault<Cache>("WoWPilago.State");
}

[[noreturn]] void Stop(char const* reason)
{
    LOG_FATAL("module", "WoWPilago progression stopped: {}", reason);
    ABORT();
}

bool Human(Player const* player)
{
    if (!player || !player->GetSession() || player->GetSession()->IsBot())
        return false;
#ifdef WOWPILAGO_PLAYERBOTS
    return !sPlayerbotsMgr.GetPlayerbotAI(const_cast<Player*>(player));
#else
    return true;
#endif
}

void ValidateProfile(Player const* player, State const& state)
{
    auto profile = std::find_if(Profiles.begin(), Profiles.end(), [&](ProfileDef const& row)
    {
        return row.race == state.raceId && row.playerClass == state.classId;
    });
    if (!Human(player) || profile == Profiles.end() || player->getClass() != state.classId ||
        player->getRace() != state.raceId)
        Stop("bound character is a bot, unsupported class/race, or mismatched profile");
}

State Load(uint32 guid)
{
    auto result = CharacterDatabase.Query(
        "SELECT b.id,b.class_id,b.race_id,p.cap_items,p.banked_xp,p.access_flags,p.riding_flags,"
        "p.talent_unlocks,p.vouchers,p.victory,JSON_UNQUOTE(JSON_EXTRACT(b.manifest,'$.catalog_version')) "
        "FROM mod_archipelago_binding b "
        "JOIN mod_archipelago_progress p ON p.binding_id=b.id "
        "WHERE b.character_guid={} AND b.status<>'archived' AND b.protocol_version=2", guid);
    if (!result)
        Stop("known binding state could not be loaded; refusing vanilla fallback");
    auto fields = result->Fetch();
    State state;
    state.characterGuid = guid;
    state.bindingId = fields[0].Get<uint64>();
    state.classId = fields[1].Get<uint8>();
    state.raceId = fields[2].Get<uint8>();
    state.capItems = fields[3].Get<uint8>();
    state.bankedXP = fields[4].Get<uint64>();
    state.accessFlags = fields[5].Get<uint8>();
    state.ridingFlags = fields[6].Get<uint8>();
    state.talentUnlocks = fields[7].Get<uint8>();
    state.vouchers = fields[8].Get<uint32>();
    state.victory = fields[9].Get<bool>();
    if (fields[10].Get<std::string>() != CatalogVersion)
        Stop("generated native catalog differs from the immutable slot manifest");
    // Sentinel rows distinguish empty collections from failed queries.
    auto sets = CharacterDatabase.Query(
        "SELECT 0 AS kind,0 AS value UNION ALL "
        "SELECT 1,ap_item FROM mod_archipelago_allowed_reward WHERE binding_id={} UNION ALL "
        "SELECT 2,location_id FROM mod_archipelago_enabled_check WHERE binding_id={} UNION ALL "
        "SELECT 3,location_id FROM mod_archipelago_check WHERE binding_id={} UNION ALL "
        "SELECT 4,base_spell FROM mod_archipelago_ability WHERE binding_id={}",
        state.bindingId, state.bindingId, state.bindingId, state.bindingId);
    if (!sets)
        Stop("binding collections query failed");
    do
    {
        auto row = sets->Fetch();
        int64 const value = row[1].Get<int64>();
        switch (row[0].Get<uint8>())
        {
            case 1: state.allowedRewards.insert(value); break;
            case 2: state.enabledChecks.insert(value); break;
            case 3: state.completedChecks.insert(value); break;
            case 4: state.abilityUnlocks.insert(uint32(value)); break;
            default: break;
        }
    } while (sets->NextRow());
    auto items = CharacterDatabase.Query(
        "SELECT 0 AS guid,0 AS entry UNION ALL SELECT item_guid,item_entry "
        "FROM mod_archipelago_authorized_item WHERE binding_id={}", state.bindingId);
    if (!items)
        Stop("authorized item query failed before inventory load");
    do
    {
        auto row = items->Fetch();
        if (row[0].Get<uint32>())
            state.authorizedItems.emplace(row[0].Get<uint32>(), row[1].Get<uint32>());
    } while (items->NextRow());
    return state;
}

void Commit(CharacterDatabaseTransaction transaction)
{
    // The one-worker queue orders writes after older character saves.
    auto completion = CharacterDatabase.AsyncCommitTransaction(transaction);
    if (!completion.m_future.get())
        Stop("transaction failed; cleared inventory dirty states make continued saving unsafe");
}

bool ProfileAllows(Player const* player, CheckDef const& check)
{
    uint8 const faction = player->GetTeamId() == TEAM_ALLIANCE ? 1 : 2;
    return (!check.faction || check.faction == faction) &&
        (!check.classMask || (check.classMask & player->getClassMask())) &&
        (!check.raceMask || (check.raceMask & player->getRaceMask()));
}

bool CanAccess(Player const* player, uint32 map, WorldLocation const* destination)
{
    State* state = GetState(player);
    if (!state)
        return true;
    if (map == 609 || map == 451 || map == 573 || map == 606)
        return false; // DK introduction and development maps are not supported play areas.
    unsigned expansion = Progression::MapExpansion(map);
    if (map == 530)
    {
        if (!destination)
            return true; // Mixed-map admission; teleport and saved-login checks supply coordinates.
        uint32 const zone = sMapMgr->GetZoneId(player->GetPhaseMask(), *destination);
        if (!zone)
            return false;
        expansion = Progression::Azeroth530Zone(zone) ? 0 : 1;
    }
    return !expansion || (state->accessFlags & (1u << (expansion - 1)));
}

constexpr std::array<uint32, 5> RidingSpells = {33388, 33391, 34090, 34091, 54197};

bool CanLearn(Player const* player, uint32 spellId)
{
    State* state = GetState(player);
    if (!state)
        return true;
    auto riding = std::find(RidingSpells.begin(), RidingSpells.end(), spellId);
    if (riding != RidingSpells.end())
        return Progression::RidingEligible(*state, player->GetLevel(), riding - RidingSpells.begin());
    auto rank = std::find_if(Ranks.begin(), Ranks.end(), [spellId](RankDef const& row)
    {
        return row.spell == spellId;
    });
    if (rank == Ranks.end())
        return true; // Baseline class spells, talents, forms and pets keep core behavior.
    bool const loading = player->GetSession()->PlayerLoading();
    if (!(rank->classMask & player->getClassMask()) || !state->abilityUnlocks.count(rank->baseSpell) ||
        player->GetLevel() < rank->level || (!loading && rank->requiredSpell && !player->HasSpell(rank->requiredSpell)) ||
        (rank->requiredSkill && player->GetBaseSkillValue(rank->requiredSkill) < rank->requiredSkillRank))
        return false;
    auto ability = std::find_if(Abilities.begin(), Abilities.end(), [&](AbilityDef const& row)
    {
        return row.baseSpell == rank->baseSpell;
    });
    if (ability == Abilities.end())
        return false;
    // Saved spells have no dependency order. Cast/trainer checks enforce prerequisites after loading.
    for (uint8 i = 0; !loading && i < ability->prerequisiteCount; ++i)
        if (!player->HasSpell(ability->prerequisites[i]))
            return false;
    uint32 const previous = sSpellMgr->GetPrevSpellInChain(spellId);
    return loading || !previous || player->HasSpell(previous);
}

bool CanTrain(Player const* player, uint32 spellId)
{
    if (!CanLearn(player, spellId))
        return false;
    if (auto info = sSpellMgr->GetSpellInfo(spellId))
        for (auto const& effect : info->GetEffects())
            if (effect.Effect == SPELL_EFFECT_LEARN_SPELL && effect.TriggerSpell &&
                !CanLearn(player, effect.TriggerSpell))
                return false;
    return true;
}

bool ProtectedItem(Player const* player, Item const* item)
{
    if (!item)
        return false;
    State* state = GetState(player);
    return state && state->authorizedItems.count(item->GetGUID().GetCounter());
}

void ZoneChecks(Player* player, uint32 zone)
{
    if (!IsBoundHuman(player) || !player->IsAlive() || player->IsInFlight())
        return;
    WorldLocation const position(player->GetMapId(), player->GetPositionX(), player->GetPositionY(),
        player->GetPositionZ(), player->GetOrientation());
    if (!CanAccess(player, player->GetMapId(), &position))
        return;
    for (auto const& check : Checks)
        if (check.kind == CheckKind::Exploration && check.wowId == zone && check.mapId == player->GetMapId())
            RecordCheck(player, check.id);
}

void BossCredit(Player* player, KillRewarder* rewarder)
{
    if (!IsBoundHuman(player) || !rewarder || !rewarder->GetVictim())
        return;
    Creature* victim = rewarder->GetVictim()->ToCreature();
    // KillRewarder runs before setDeathState; its callback, not IsAlive(), confirms the kill.
    if (!victim || player->GetMap() != victim->GetMap() ||
        !player->IsAtGroupRewardDistance(victim) || (!player->IsAlive() && player->GetCorpse()))
        return;
    Map* map = victim->GetMap();
    // Catalog encounters are normal difficulty. Heroic aliases need separate curation.
    if (!map->IsRegularDifficulty() &&
        !(map->IsRaid() && map->GetDifficulty() == RAID_DIFFICULTY_25MAN_NORMAL))
        return;
    State* state = GetState(player);
    for (auto const& check : Checks)
    {
        if (check.mapId != map->GetId())
            continue;
        if ((check.kind == CheckKind::Boss || check.kind == CheckKind::Raid) && check.wowId == victim->GetEntry())
            RecordCheck(player, check.id);
        if (check.kind != CheckKind::Dungeon || !state->enabledChecks.count(check.id) ||
            !ProfileAllows(player, check) || state->completedChecks.count(check.id) ||
            std::find(check.bosses.begin(), check.bosses.begin() + check.bossCount, victim->GetEntry()) ==
                check.bosses.begin() + check.bossCount)
            continue;
        auto save = sInstanceSaveMgr->GetInstanceSave(map->GetInstanceId());
        if (!save || !map->GetInstanceId())
            continue;
        // Instance IDs can be reused; retain the save's reset identity as well.
        uint64 const epoch = uint64(save->GetResetTime());
        if (!epoch)
            continue;
        auto transaction = CharacterDatabase.BeginTransaction();
        transaction->Append(
            "INSERT IGNORE INTO mod_archipelago_boss_credit "
            "(binding_id,map_id,boss_id,instance_id,reset_epoch) VALUES ({},{},{},{},{})",
            state->bindingId, map->GetId(), victim->GetEntry(), map->GetInstanceId(), epoch);
        Commit(transaction);
        // Restrict the count to this catalog's required IDs, never arbitrary creatures in the map.
        unsigned count = 0;
        for (uint8 i = 0; i < check.bossCount; ++i)
        {
            auto found = CharacterDatabase.Query(
                "SELECT COUNT(*) FROM mod_archipelago_boss_credit WHERE binding_id={} AND map_id={} "
                "AND boss_id={} AND instance_id={} AND reset_epoch={}", state->bindingId,
                map->GetId(), check.bosses[i], map->GetInstanceId(), epoch);
            if (!found)
                Stop("dungeon credit durability query failed");
            uint32 const persisted = found->Fetch()[0].Get<uint32>();
            if (check.bosses[i] == victim->GetEntry() && persisted != 1)
                Stop("current boss credit insert was not durable");
            count += persisted;
        }
        if (count == check.bossCount)
            RecordCheck(player, check.id);
    }
}

class ProgressionPlayer final : public PlayerScript
{
public:
    ProgressionPlayer() : PlayerScript("WoWPilagoProgression", {
        PLAYERHOOK_ON_LOAD_FROM_DB, PLAYERHOOK_ON_LOGIN,
        PLAYERHOOK_BEFORE_APPLY_XP, PLAYERHOOK_ON_CAN_GIVE_LEVEL, PLAYERHOOK_ON_SET_MAX_LEVEL,
        PLAYERHOOK_ON_LEVEL_CHANGED, PLAYERHOOK_ON_CALCULATE_TALENTS_POINTS,
        PLAYERHOOK_CAN_ADD_SPELL, PLAYERHOOK_CAN_TRAIN_SPELL, PLAYERHOOK_CAN_ACCESS_MAP,
        PLAYERHOOK_CHECK_ITEM_LEVEL, PLAYERHOOK_SAVE_TO_DB, PLAYERHOOK_ON_PLAYER_COMPLETE_QUEST,
        PLAYERHOOK_ON_REWARD_KILL_REWARDER, PLAYERHOOK_ON_UPDATE_ZONE, PLAYERHOOK_ON_UPDATE_AREA,
        PLAYERHOOK_ON_CAN_PLAYER_FLY_IN_ZONE, PLAYERHOOK_CAN_SET_TRADE_ITEM,
        PLAYERHOOK_CAN_SEND_MAIL, PLAYERHOOK_CAN_SELL_ITEM, PLAYERHOOK_ON_DELETE_FROM_DB,
        PLAYERHOOK_ON_LEARN_SPELL}) { }

    void OnPlayerLoadFromDB(Player* player) override { GetState(player); }
    void OnPlayerLogin(Player* player) override
    {
        RefreshState(player);
        Reconcile(player);
    }

    void OnPlayerBeforeApplyXP(Player* player, uint64& finalXP, uint32& maxLevel) override
    {
        if (auto state = GetState(player))
        {
            maxLevel = std::min<uint32>(maxLevel, Progression::Cap(*state));
            uint64 const oldBank = state->bankedXP;
            Progression::NormalizeXP(*state, player->GetLevel(), player->GetUInt32Value(PLAYER_XP), maxLevel,
                finalXP, [](unsigned level) { return sObjectMgr->GetXPForLevel(level); });
            if (state->bankedXP != oldBank)
                PlayerCache(player)->savePending = true;
        }
    }

    bool OnPlayerCanGiveLevel(Player* player, uint8 level) override
    {
        auto state = GetState(player);
        return !state || (level >= player->GetLevel() && level <= Progression::Cap(*state));
    }

    void OnPlayerSetMaxLevel(Player* player, uint32& level) override
    {
        if (auto state = GetState(player))
            level = std::min<uint32>(level, Progression::Cap(*state));
    }

    void OnPlayerCalculateTalentsPoints(Player const* player, uint32& points) override
    {
        if (auto state = GetState(player))
        {
            uint32 const normal = player->GetLevel() < 10 ? 0 : player->GetLevel() - 9;
            if (points != normal)
                Stop("bound character has incompatible bonus talent points or talent module");
            points = Progression::TalentPoints(player->GetLevel(), state->talentUnlocks);
        }
    }

    void OnPlayerLevelChanged(Player* player, uint8 /*oldLevel*/) override
    {
        if (GetState(player))
            PlayerCache(player)->savePending = true;
        Reconcile(player);
    }
    void OnPlayerLearnSpell(Player* player, uint32 spell) override
    {
        if (player->GetSession()->PlayerLoading())
            return;
        // Only baseline prerequisites trigger this path; shuffled abilities are independent chains.
        for (auto const& ability : Abilities)
            if (std::find(ability.prerequisites.begin(), ability.prerequisites.begin() +
                ability.prerequisiteCount, spell) != ability.prerequisites.begin() + ability.prerequisiteCount)
            {
                Reconcile(player);
                return;
            }
    }
    bool OnPlayerCanAddSpell(Player* player, uint32 spell, uint8, bool, bool) override
    {
        return CanLearn(player, spell);
    }
    bool OnPlayerCanTrainSpell(Player const* player, uint32 spell) override { return CanTrain(player, spell); }
    bool OnPlayerCanAccessMap(Player const* player, uint32 map, WorldLocation const* position, bool) override
    {
        return CanAccess(player, map, position);
    }
    void OnPlayerCheckItemLevel(Player const* player, Item const* item, bool& ignore) override
    {
        // Never turn a template-only or mismatched instance into an exemption.
        if (IsAuthorized(player, item))
            ignore = true;
    }
    void OnPlayerSaveToDB(Player* player, CharacterDatabaseTransaction transaction, bool, bool) override
    {
        if (auto state = GetState(player))
            transaction->Append(
                "UPDATE mod_archipelago_progress SET banked_xp={},last_level={},victory={} WHERE binding_id={}",
                state->bankedXP, player->GetLevel(), player->GetLevel() == 80 ? 1 : 0, state->bindingId);
    }
    void OnPlayerCompleteQuest(Player* player, Quest const* quest) override
    {
        if (!quest || !IsBoundHuman(player) || !player->GetQuestRewardStatus(quest->GetQuestId()))
            return;
        for (auto const& check : Checks)
            if (check.kind == CheckKind::Quest && check.wowId == quest->GetQuestId())
                RecordCheck(player, check.id);
    }
    void OnPlayerUpdateZone(Player* player, uint32 zone, uint32) override { ZoneChecks(player, zone); }
    void OnPlayerUpdateArea(Player* player, uint32, uint32 area) override
    {
        // Core updates the cached area after this callback.
        ZoneChecks(player, area);
    }
    void OnPlayerRewardKillRewarder(Player* player, KillRewarder* rewarder, bool, float&) override
    {
        BossCredit(player, rewarder);
    }
    bool OnPlayerCanFlyInZone(Player* player, uint32 map, uint32 zone, SpellInfo const*) override
    {
        auto state = GetState(player);
        if (!state)
            return true;
        if (map == 530)
            return !Progression::Azeroth530Zone(zone) && (state->accessFlags & 1) &&
                Progression::RidingEligible(*state, player->GetLevel(), 2);
        return map == 571 && (state->accessFlags & 2) &&
            Progression::RidingEligible(*state, player->GetLevel(), 4);
    }
    bool OnPlayerCanSetTradeItem(Player* player, Item* item, uint8) override
    {
        return !ProtectedItem(player, item);
    }
    bool OnPlayerCanSendMail(Player* player, ObjectGuid, ObjectGuid, std::string&, std::string&,
        uint32, uint32, Item* item) override { return !ProtectedItem(player, item); }
    bool OnPlayerCanSellItem(Player* player, Item* item, Creature*) override
    {
        return !ProtectedItem(player, item);
    }
    void OnPlayerDeleteFromDB(CharacterDatabaseTransaction transaction, uint32 guid) override
    {
        // Core queues DELETE first; capture the ID before its FK clears character_guid.
        QueryResult binding = CharacterDatabase.Query(
            "SELECT id FROM mod_archipelago_binding WHERE character_guid={}", guid);
        // Legacy-schema fallback; the schema's BEFORE DELETE trigger archives without this read.
        if (binding)
            transaction->Append("UPDATE mod_archipelago_binding SET status='archived',character_guid=NULL "
                "WHERE id={}", binding->Fetch()[0].Get<uint64>());
    }
};

class ProgressionSpells final : public AllSpellScript
{
public:
    ProgressionSpells() : AllSpellScript("WoWPilagoProgressionSpells", {ALLSPELLHOOK_ON_SPELL_CHECK_CAST}) { }
    void OnSpellCheckCast(Spell* spell, bool, SpellCastResult& result) override
    {
        Player* player = spell->GetCaster()->ToPlayer();
        if (!player || result != SPELL_CAST_OK)
            return;
        State* state = GetState(player);
        if (!state)
            return;
        SpellInfo const* info = spell->GetSpellInfo();
        if (!CanTrain(player, info->Id))
        {
            result = SPELL_FAILED_SPELL_UNAVAILABLE;
            return;
        }
        for (auto const& effect : info->GetEffects())
            if ((effect.Effect == SPELL_EFFECT_SKILL || effect.Effect == SPELL_EFFECT_SKILL_STEP) &&
                effect.MiscValue == SKILL_RIDING)
            {
                auto tier = std::find(RidingSpells.begin(), RidingSpells.end(), info->Id);
                if (tier == RidingSpells.end() || !Progression::RidingEligible(*state, player->GetLevel(),
                    tier - RidingSpells.begin()))
                    result = SPELL_FAILED_SPELL_UNAVAILABLE;
            }
        if (info->HasAura(SPELL_AURA_MOUNTED) &&
            !Progression::RidingEligible(*state, player->GetLevel(), 0))
            result = SPELL_FAILED_SPELL_UNAVAILABLE;
        for (auto const& effect : info->GetEffects())
        {
            if (effect.ApplyAuraName == SPELL_AURA_MOD_INCREASE_MOUNTED_SPEED && effect.CalcValue(player) >= 100 &&
                !Progression::RidingEligible(*state, player->GetLevel(), 1))
                result = SPELL_FAILED_SPELL_UNAVAILABLE;
            if ((effect.ApplyAuraName == SPELL_AURA_MOD_INCREASE_MOUNTED_FLIGHT_SPEED ||
                effect.ApplyAuraName == SPELL_AURA_MOD_INCREASE_FLIGHT_SPEED) && effect.CalcValue(player) >= 280 &&
                !Progression::RidingEligible(*state, player->GetLevel(), 3))
                result = SPELL_FAILED_SPELL_UNAVAILABLE;
        }
        if ((info->HasAura(SPELL_AURA_FLY) || info->HasAura(SPELL_AURA_MOD_INCREASE_MOUNTED_FLIGHT_SPEED)) &&
            !player->canFlyInZone(player->GetMapId(), player->GetZoneId(), info))
            result = SPELL_FAILED_NOT_HERE;
    }
};

class ProgressionWorld final : public WorldScript
{
public:
    ProgressionWorld() : WorldScript("WoWPilagoProgressionWorld",
        {WORLDHOOK_ON_STARTUP, WORLDHOOK_ON_AFTER_CONFIG_LOAD, WORLDHOOK_ON_UPDATE}) { }
    void OnAfterConfigLoad(bool) override
    {
        if (sConfigMgr->GetOption<uint32>("CharacterDatabase.WorkerThreads", 1) != 1 ||
            sWorld->getRate(RATE_TALENT) != 1.0f ||
            sWorld->getIntConfig(CONFIG_MAX_PLAYER_LEVEL) != 80)
            Stop("require one character DB worker, Rate.Talent=1, no bonus talents, and MaxPlayerLevel=80");
    }
    void OnStartup() override
    {
        OnAfterConfigLoad(false);
        auto result = CharacterDatabase.Query(
            "SELECT 0 AS guid,0 AS binding_id UNION ALL SELECT character_guid,id FROM mod_archipelago_binding "
            "WHERE character_guid IS NOT NULL AND status<>'archived'");
        if (!result)
            Stop("cannot preload protocol-2 binding registry");
        do
        {
            uint32 const guid = result->Fetch()[0].Get<uint32>();
            if (guid)
                Load(guid);
        } while (result->NextRow());
    }

    void OnUpdate(uint32 diff) override
    {
        if (diff < _remaining)
        {
            _remaining -= diff;
            return;
        }
        _remaining = 5000;
        auto online = CharacterDatabase.Query(
            "SELECT 0 AS guid UNION ALL SELECT b.character_guid FROM mod_archipelago_binding b "
            "JOIN characters c ON c.guid=b.character_guid WHERE c.online=1 AND b.status<>'archived'");
        if (!online)
            Stop("online progression registry query failed");
        do
        {
            uint32 const guid = online->Fetch()[0].Get<uint32>();
            Player* player = guid ? ObjectAccessor::FindPlayer(ObjectGuid(HighGuid::Player, guid)) : nullptr;
            if (!player || !IsBoundHuman(player) || !PlayerCache(player)->savePending)
                continue;
            auto transaction = CharacterDatabase.BeginTransaction();
            player->SaveToDB(transaction, false, false);
            Commit(transaction);
            auto state = GetState(player);
            auto saved = CharacterDatabase.Query(
                "SELECT c.level,p.last_level,p.banked_xp,c.xp FROM characters c "
                "JOIN mod_archipelago_binding b ON b.character_guid=c.guid "
                "JOIN mod_archipelago_progress p ON p.binding_id=b.id WHERE c.guid={}", guid);
            if (!saved || saved->Fetch()[0].Get<uint8>() != player->GetLevel() ||
                saved->Fetch()[1].Get<uint8>() != player->GetLevel() ||
                saved->Fetch()[2].Get<uint64>() != state->bankedXP ||
                saved->Fetch()[3].Get<uint32>() != player->GetUInt32Value(PLAYER_XP))
                Stop("progression save outcome was not confirmed");
            PlayerCache(player)->savePending = false;
            Reconcile(player);
        } while (online->NextRow());
    }

private:
    uint32 _remaining = 5000;
};
}

State* GetState(Player const* player)
{
    if (!player || !player->GetGUID())
        return nullptr;
    uint32 const guid = player->GetGUID().GetCounter();
    Cache* cache = PlayerCache(player);
    if (!cache->initialized)
    {
        // An aggregate always returns one row, including for a genuinely unbound human.
        auto probe = CharacterDatabase.Query(
            "SELECT COUNT(*) FROM mod_archipelago_binding WHERE character_guid={} AND status<>'archived'", guid);
        if (!probe)
            Stop("binding lookup failed; cannot distinguish unbound from unavailable");
        if (!probe->Fetch()[0].Get<uint32>())
        {
            cache->initialized = true;
            cache->bound = false;
            return nullptr;
        }
        cache->state = Load(guid);
        cache->initialized = true;
        cache->bound = true;
    }
    if (!cache->bound)
        return nullptr;
    ValidateProfile(player, cache->state);
    return &cache->state;
}

void RefreshState(Player* player)
{
    if (!player)
        return;
    Cache* cache = PlayerCache(player);
    uint64 const bank = cache->bound ? cache->state.bankedXP : 0;
    uint8 const cap = cache->bound ? cache->state.capItems : 0;
    cache->initialized = false;
    // Only a committed cap receipt can release bank. Failed/unrelated receipts retain live overflow.
    if (auto state = GetState(player))
    {
        if (state->capItems == cap)
            state->bankedXP = std::max(state->bankedXP, bank);
        else
            cache->savePending = false;
    }
}

bool IsBoundHuman(Player const* player) { return Human(player) && GetState(player); }

bool IsAuthorized(Player const* player, Item const* item)
{
    if (!item || !player || item->GetOwnerGUID() != player->GetGUID())
        return false;
    State* state = GetState(player);
    if (!state)
        return false;
    auto found = state->authorizedItems.find(item->GetGUID().GetCounter());
    return found != state->authorizedItems.end() && found->second == item->GetEntry();
}

void RecordCheck(Player* player, int64 location)
{
    if (!IsBoundHuman(player))
        return;
    State* state = GetState(player);
    auto check = FindById(Checks, location);
    if (!check || !state->enabledChecks.count(location) || state->completedChecks.count(location) ||
        !ProfileAllows(player, *check))
        return;
    auto transaction = CharacterDatabase.BeginTransaction();
    transaction->Append(
        "INSERT IGNORE INTO mod_archipelago_check (binding_id,location_id) "
        "SELECT e.binding_id,e.location_id FROM mod_archipelago_enabled_check e "
        "JOIN mod_archipelago_binding b ON b.id=e.binding_id "
        "WHERE e.binding_id={} AND e.location_id={} AND b.character_guid={} AND b.status<>'archived'",
        state->bindingId, location, state->characterGuid);
    Commit(transaction);
    auto confirmed = CharacterDatabase.Query(
        "SELECT COUNT(*) FROM mod_archipelago_check WHERE binding_id={} AND location_id={}",
        state->bindingId, location);
    if (!confirmed || confirmed->Fetch()[0].Get<uint32>() != 1)
        Stop("check outbox insert was not durable");
    state->completedChecks.insert(location);
}

void Reconcile(Player* player)
{
    if (!IsBoundHuman(player))
        return;
    State* state = GetState(player);
    player->SetUInt32Value(PLAYER_FIELD_MAX_LEVEL, Progression::Cap(*state));
    player->InitTalentForLevel();
    for (auto const& entry : state->authorizedItems)
        if (auto item = player->GetItemByGuid(ObjectGuid(HighGuid::Item, entry.first)))
        {
            item->SetBinding(true);
            item->ClearSoulboundTradeable(player);
            item->SetNotRefundable(player);
        }
    for (uint8 tier = 0; tier < RidingSpells.size(); ++tier)
        if (Progression::RidingEligible(*state, player->GetLevel(), tier))
            player->learnSpell(RidingSpells[tier]);
    for (auto const& ability : Abilities)
        if (ability.classId == state->classId && state->abilityUnlocks.count(ability.baseSpell) &&
            !player->HasSpell(ability.baseSpell) && CanLearn(player, ability.baseSpell))
            player->learnSpell(ability.baseSpell);
    for (auto const& check : Checks)
        // Pending level changes become checks only after the full save is confirmed.
        if ((check.kind == CheckKind::Level && !PlayerCache(player)->savePending &&
                player->GetLevel() >= check.wowId) ||
            (check.kind == CheckKind::Quest && player->GetQuestRewardStatus(check.wowId)))
            RecordCheck(player, check.id);
    ZoneChecks(player, player->GetZoneId());
    if (player->GetAreaId() != player->GetZoneId())
        ZoneChecks(player, player->GetAreaId());
    if (player->GetLevel() == 80 && !state->victory)
    {
        state->victory = true;
        PlayerCache(player)->savePending = true;
    }
}

void RegisterProgressionScripts()
{
    new ProgressionWorld();
    new ProgressionPlayer();
    new ProgressionSpells();
}
}
