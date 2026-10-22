#include "APDelivery.h"
#include "APProgression.h"
#include "Bag.h"
#include "Chat.h"
#include "Config.h"
#include "DatabaseEnv.h"
#include "Errors.h"
#include "Item.h"
#include "Log.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Opcodes.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "WorldPacket.h"
#include "WorldSession.h"
#include <chrono>
#include <memory>
#include <set>
#include <sstream>
#include <thread>

namespace WoWPilago
{
namespace
{
bool ready = false;
std::set<uint32> active;

[[noreturn]] void Stop(char const* reason)
{
    LOG_FATAL("module", "WoWPilago delivery stopped before another player save: {}", reason);
    ABORT();
}

// Blocking on the world thread also prevents gameplay/save races. Never retain Player across ticks.
QueryResult Ordered(std::string const& sql)
{
    QueryResult result;
    auto callback = CharacterDatabase.AsyncQuery(sql);
    callback.WithCallback([&result](QueryResult value) { result = value; });
    while (!callback.InvokeIfReady())
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    if (!result)
        Stop("ordered confirmation query failed or required row is absent");
    return result;
}

std::string Quoted(std::string value)
{
    CharacterDatabase.EscapeString(value);
    return "'" + value + "'";
}

bool Available(Player* player)
{
    return ready && player && player->GetSession() && !player->GetSession()->IsBot() &&
        player->GetSession()->GetPlayer() == player && !player->GetSession()->PlayerLoading() &&
        !player->GetSession()->IsSocketClosed() && player->IsInWorld() &&
        !player->IsBeingTeleported() && !player->IsDuringRemoveFromWorld() && IsBoundHuman(player);
}

struct Attempt
{
    uint32 guid;
    bool acquired;
    explicit Attempt(Player* player) : guid(player->GetGUID().GetCounter()), acquired(active.insert(guid).second) { }
    ~Attempt() { if (acquired) active.erase(guid); }
};

struct Candidate
{
    std::unique_ptr<Item> item;
    ItemPosCountVec destination;
    uint32 bagGuid = 0;
    uint8 bag = 0, slot = 0;
    ~Candidate()
    {
        if (item)
            item->RemoveFromUpdateQueueOf(item->GetOwner());
    }
};

bool Prepare(Player* player, uint32 entry, uint32 count, bool gear, Candidate& candidate)
{
    for (uint8 bagSlot : {uint8(INVENTORY_SLOT_BAG_0), uint8(19), uint8(20), uint8(21), uint8(22)})
    {
        Bag* bag = bagSlot == INVENTORY_SLOT_BAG_0 ? nullptr : player->GetBagByPos(bagSlot);
        if (bagSlot != INVENTORY_SLOT_BAG_0 && !bag)
            continue;
        unsigned const begin = bag ? 0 : INVENTORY_SLOT_ITEM_START;
        unsigned const end = bag ? bag->GetBagSize() : INVENTORY_SLOT_ITEM_END;
        for (unsigned slot = begin; slot < end; ++slot)
        {
            if (player->GetItemByPos(bagSlot, slot))
                continue;
            candidate.destination.clear();
            uint16 const pos = uint16(bagSlot) << 8 | slot;
            if (player->CanStoreNewItem(bagSlot, slot, candidate.destination, entry, count) != EQUIP_ERR_OK ||
                candidate.destination.size() != 1 || candidate.destination[0].pos != pos ||
                candidate.destination[0].count != count)
                continue;
            candidate.item.reset(Item::CreateItem(entry, count, player));
            if (!candidate.item || candidate.item->GetCount() != count)
                return false;
            candidate.bag = bagSlot;
            candidate.slot = slot;
            candidate.bagGuid = bag ? bag->GetGUID().GetCounter() : 0;
            Item* item = candidate.item.get();
            if (gear || item->GetTemplate()->Bonding == BIND_WHEN_PICKED_UP ||
                item->GetTemplate()->Bonding == BIND_QUEST_ITEM)
                item->SetBinding(true);
            if (gear)
            {
                item->ClearSoulboundTradeable(player);
                item->SetNotRefundable(player);
            }
            // Random-property creation can queue a detached item. Never let the preceding save see it.
            item->RemoveFromUpdateQueueOf(player);
            return true;
        }
    }
    return false;
}

std::string Charges(Item const* item)
{
    std::ostringstream value;
    for (uint8 i = 0; i < MAX_ITEM_PROTO_SPELLS; ++i)
        value << item->GetSpellCharges(i) << ' ';
    return value.str();
}

std::string Enchantments(Item const* item)
{
    std::ostringstream value;
    for (uint8 i = 0; i < MAX_ENCHANTMENT_SLOT; ++i)
        value << item->GetEnchantmentId(EnchantmentSlot(i)) << ' ' <<
            item->GetEnchantmentDuration(EnchantmentSlot(i)) << ' ' <<
            item->GetEnchantmentCharges(EnchantmentSlot(i)) << ' ';
    return value.str();
}

// GUID, parent GUID, parent slot, destination slot, then all ten serialized metadata fields.
std::string ItemArguments(Candidate const& c)
{
    if (!c.item)
        return "0,0,0,0,0,0,0,'',0,'',0,0,0,''";
    auto item = c.item.get();
    return Acore::StringFormat("{},{},{},{},{},{},{},{},{},{},{},{},{},{}",
        item->GetGUID().GetCounter(), c.bagGuid, c.bag, c.slot,
        item->GetGuidValue(ITEM_FIELD_CREATOR).GetCounter(),
        item->GetGuidValue(ITEM_FIELD_GIFTCREATOR).GetCounter(), item->GetInt32Value(ITEM_FIELD_DURATION),
        Quoted(Charges(item)), item->GetUInt32Value(ITEM_FIELD_FLAGS), Quoted(Enchantments(item)),
        item->GetItemRandomPropertyId(), item->GetUInt32Value(ITEM_FIELD_DURABILITY),
        item->GetUInt32Value(ITEM_FIELD_CREATE_PLAYED_TIME), Quoted(item->GetText()));
}

std::string ItemMatches(Player* player, Item const* item, uint32 parent, uint8 slot)
{
    return Acore::StringFormat(
        "EXISTS(SELECT 1 FROM item_instance i JOIN character_inventory v ON v.item=i.guid "
        "WHERE i.guid={} AND i.owner_guid={} AND i.itemEntry={} AND i.count={} "
        "AND v.guid={} AND v.bag={} AND v.slot={} AND i.creatorGuid={} AND i.giftCreatorGuid={} "
        "AND i.duration={} AND BINARY i.charges=BINARY {} AND i.flags={} "
        "AND BINARY i.enchantments=BINARY {} AND i.randomPropertyId={} AND i.durability={} "
        "AND i.playedTime={} AND BINARY i.text=BINARY {})",
        item->GetGUID().GetCounter(), player->GetGUID().GetCounter(), item->GetEntry(), item->GetCount(),
        player->GetGUID().GetCounter(), parent, slot, item->GetGuidValue(ITEM_FIELD_CREATOR).GetCounter(),
        item->GetGuidValue(ITEM_FIELD_GIFTCREATOR).GetCounter(), item->GetInt32Value(ITEM_FIELD_DURATION),
        Quoted(Charges(item)), item->GetUInt32Value(ITEM_FIELD_FLAGS), Quoted(Enchantments(item)),
        item->GetItemRandomPropertyId(), item->GetUInt32Value(ITEM_FIELD_DURABILITY),
        item->GetUInt32Value(ITEM_FIELD_CREATE_PLAYED_TIME), Quoted(item->GetText()));
}

Delivery::Snapshot ReadSnapshot(Player* player, uint64 binding, uint32 spell)
{
    auto result = Ordered(Acore::StringFormat(
        "SELECT c.level,c.money,c.xp,p.cap_items,p.access_flags,p.riding_flags,p.talent_unlocks,"
        "p.banked_xp,p.vouchers,p.last_level,p.victory,"
        "EXISTS(SELECT 1 FROM mod_archipelago_ability WHERE binding_id=b.id AND base_spell={}) "
        "FROM mod_archipelago_binding b JOIN characters c ON c.guid=b.character_guid "
        "JOIN mod_archipelago_progress p ON p.binding_id=b.id WHERE b.id={} AND c.guid={} "
        "AND b.status<>'archived' AND b.protocol_version=2 AND b.class_id=c.class AND b.race_id=c.race "
        "AND b.character_account=c.account AND c.account={} AND c.class={} AND c.race={}",
        spell, binding, player->GetGUID().GetCounter(), player->GetSession()->GetAccountId(),
        player->getClass(), player->getRace()));
    auto f = result->Fetch();
    return {f[0].Get<uint32>(), f[1].Get<uint32>(), f[2].Get<uint32>(), f[3].Get<uint32>(),
        f[4].Get<uint32>(), f[5].Get<uint32>(), f[6].Get<uint32>(), f[7].Get<uint64>(),
        f[8].Get<uint64>(), f[9].Get<uint32>(), f[10].Get<uint32>(), f[11].Get<uint32>()};
}

Delivery::Snapshot Flush(Player* player, State const& state, uint32 spell)
{
    auto transaction = CharacterDatabase.BeginTransaction();
    player->SaveToDB(transaction, false, false); // Includes APProgression's absolute bank/level save hook.
    auto completion = CharacterDatabase.AsyncCommitTransaction(transaction);
    if (!completion.m_future.get())
        Stop("full player save failed; core may already have cleared dirty item states");
    auto saved = ReadSnapshot(player, state.bindingId, spell);
    if (saved.level != player->GetLevel() || saved.money != player->GetMoney() ||
        saved.xp != player->GetUInt32Value(PLAYER_XP) || saved.bank != state.bankedXP ||
        saved.cap != state.capItems || saved.access != state.accessFlags || saved.riding != state.ridingFlags ||
        saved.talent != state.talentUnlocks || saved.vouchers != state.vouchers ||
        saved.victory != state.victory || saved.lastLevel != player->GetLevel())
        Stop("full player save/progress confirmation disagrees with live state");

    // Confirm every saved item, including equipped parents and bank, not just money or the new slot.
    std::string inventory = "SELECT 1";
    unsigned count = 0;
    auto check = [&](Item* item, uint32 parent, uint8 slot)
    {
        if (item)
        {
            ++count;
            inventory += " AND " + ItemMatches(player, item, parent, slot);
        }
    };
    for (uint8 slot = 0; slot < PLAYER_SLOT_END; ++slot)
        check(player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot), 0, slot);
    for (uint8 slot = INVENTORY_SLOT_BAG_START; slot < BANK_SLOT_BAG_END; ++slot)
    {
        if (slot >= INVENTORY_SLOT_BAG_END && slot < BANK_SLOT_BAG_START)
            continue;
        if (Bag* bag = player->GetBagByPos(slot))
            for (uint8 inner = 0; inner < bag->GetBagSize(); ++inner)
                check(player->GetItemByPos(slot, inner), bag->GetGUID().GetCounter(), inner);
    }
    inventory += Acore::StringFormat(" AND (SELECT COUNT(*) FROM character_inventory WHERE guid={})={}",
        player->GetGUID().GetCounter(), count);
    if (!Ordered(inventory)->Fetch()[0].Get<bool>())
        Stop("full saved inventory differs from live inventory");
    return saved;
}

void VerifyCandidate(Player* player, uint64 binding, Candidate const& c, bool gear, bool applied)
{
    if (!c.item)
        return;
    auto result = Ordered(Acore::StringFormat("SELECT {},"
        "(SELECT COUNT(*) FROM item_instance WHERE guid={}),"
        "(SELECT COUNT(*) FROM character_inventory WHERE item={}),"
        "(SELECT COUNT(*) FROM mod_archipelago_authorized_item WHERE item_guid={}),"
        "EXISTS(SELECT 1 FROM mod_archipelago_authorized_item WHERE item_guid={} AND binding_id={} AND item_entry={})",
        ItemMatches(player, c.item.get(), c.bagGuid, c.slot), c.item->GetGUID().GetCounter(),
        c.item->GetGUID().GetCounter(), c.item->GetGUID().GetCounter(), c.item->GetGUID().GetCounter(),
        binding, c.item->GetEntry()));
    auto f = result->Fetch();
    if (applied ? (!f[0].Get<bool>() || f[1].Get<uint32>() != 1 || f[2].Get<uint32>() != 1 ||
        f[3].Get<uint32>() != unsigned(gear) || f[4].Get<bool>() != gear) :
        (f[1].Get<uint32>() || f[2].Get<uint32>() || f[3].Get<uint32>()))
        Stop("receipt, serialized item, placement or authorization contradicts outcome");
}

void Notify(Player* player, std::string const& message)
{
    WorldPacket packet;
    ChatHandler::BuildChatPacket(packet, CHAT_MSG_WHISPER, LANG_ADDON, player->GetGUID(), player->GetGUID(),
        "WOWPILAGO\t" + message, CHAT_TAG_NONE);
    player->GetSession()->SendPacket(&packet);
}

void Publish(Player* player, Delivery::Snapshot const& saved, Candidate& c)
{
    player->SetMoney(saved.money);
    player->SetUInt32Value(PLAYER_XP, saved.xp); // Never GiveXP: bank release has no multipliers or level gain.
    RefreshState(player);
    if (c.item)
    {
        Item* item = c.item.get();
        if (player->GetItemByPos(c.bag, c.slot) || player->StoreItem(c.destination, item, true) != item)
            Stop("verified destination changed before publication");
        c.item.release();
        item->RemoveFromUpdateQueueOf(player);
        item->SetState(ITEM_UNCHANGED, player);
        player->SendNewItem(item, item->GetCount(), true, false);
    }
    Reconcile(player);
}

Item* OwnedUsable(Player* player, uint32 guid)
{
    if (!Available(player))
        return nullptr;
    Item* item = player->GetItemByGuid(ObjectGuid(HighGuid::Item, guid));
    // Bank access is deliberately not implemented by this command fallback.
    if (!item || !IsAuthorized(player, item) ||
        (!Player::IsInventoryPos(item->GetPos()) && !Player::IsEquipmentPos(item->GetPos())))
        return nullptr;
    return item;
}

class DeliveryWorld final : public WorldScript
{
public:
    DeliveryWorld() : WorldScript("WoWPilagoDelivery", {WORLDHOOK_ON_STARTUP, WORLDHOOK_ON_UPDATE}) { }
    void OnStartup() override
    {
        auto tables = Ordered("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() "
            "AND table_name IN ('characters','character_inventory','item_instance','mod_archipelago_binding',"
            "'mod_archipelago_progress','mod_archipelago_reward','mod_archipelago_allowed_reward',"
            "'mod_archipelago_ability','mod_archipelago_stock','mod_archipelago_purchase',"
            "'mod_archipelago_authorized_item') AND engine='InnoDB'");
        auto routines = Ordered("SELECT "
            "SUM(specific_name='mod_archipelago_v2_apply_reward'),"
            "SUM(specific_name='mod_archipelago_v2_purchase') FROM information_schema.parameters "
            "WHERE specific_schema=DATABASE() AND parameter_mode='IN'");
        if (tables->Fetch()[0].Get<uint32>() != 11 || routines->Fetch()[0].Get<uint32>() != 21 ||
            routines->Fetch()[1].Get<uint32>() != 16 ||
            sConfigMgr->GetOption<uint32>("CharacterDatabase.WorkerThreads", 1) != 1)
            Stop("require v2 InnoDB tables, exact 21/16-argument routines and one character DB worker");
        ready = true;
    }
    void OnUpdate(uint32 diff) override
    {
        if (!ready)
            return;
        if (diff < remaining)
        {
            remaining -= diff;
            return;
        }
        remaining = 5000;
        // shortcut: one realm owns the queue; add a lease before sharing CharacterDatabase across realms.
        auto rows = Ordered("SELECT 0 AS guid,0 AS item_index,0 AS sender UNION ALL "
            "SELECT b.character_guid,r.item_index,r.sender FROM mod_archipelago_reward r "
            "JOIN mod_archipelago_binding b ON b.id=r.binding_id JOIN characters c ON c.guid=b.character_guid "
            "WHERE r.applied=0 AND b.status<>'archived' AND b.protocol_version=2 AND c.online=1 "
            "ORDER BY guid,item_index");
        do
        {
            auto f = rows->Fetch();
            if (f[0].Get<uint32>())
                if (auto player = ObjectAccessor::FindPlayer(ObjectGuid(HighGuid::Player, f[0].Get<uint32>())))
                    if (player->GetSession() && !player->GetSession()->IsBot())
                        ApplyQueuedReward(player, f[1].Get<uint32>(), f[2].Get<uint32>());
        } while (rows->NextRow());
    }
private:
    uint32 remaining = 5000;
};
}

bool ApplyQueuedReward(Player* player, uint32 index, uint32 sender)
{
    if (!Available(player))
        return false;
    Attempt attempt(player);
    if (!attempt.acquired)
        return false;
    State const state = *GetState(player);
    auto receipt = Ordered(Acore::StringFormat(
        "SELECT COUNT(*),COALESCE(MAX(ap_item),0),COALESCE(MAX(kind),''),COALESCE(MAX(value),0),"
        "COALESCE(MAX(sender),0),COALESCE(MAX(applied),0) FROM mod_archipelago_reward "
        "WHERE binding_id={} AND item_index={}", state.bindingId, index));
    auto f = receipt->Fetch();
    if (!f[0].Get<uint32>())
        return false;
    int64 const ap = f[1].Get<int64>();
    auto reward = Delivery::ValidateReward(ap, f[2].Get<std::string>(), f[3].Get<uint32>(),
        player->getClassMask(), state.allowedRewards.count(ap));
    if (!reward || f[4].Get<uint32>() != sender)
        Stop("queued AP ID, kind/value, sender or class does not match compiled allowed catalog");
    if (f[5].Get<bool>())
        return false; // Durable replay, including a consumed/deleted physical item. No new candidate.
    uint32 entry = 0, count = 0;
    bool const gear = reward->kind == RewardKind::Legendary || reward->kind == RewardKind::Bag;
    switch (reward->kind)
    {
        case RewardKind::Bag: entry = 21841; count = 1; break;
        case RewardKind::Consumable: entry = Delivery::Potion(player->GetLevel()); count = 5; break;
        case RewardKind::Legendary: entry = reward->value; count = 1; break;
        default: break;
    }
    Candidate candidate;
    if (entry && !Prepare(player, entry, count, gear, candidate))
        return false;
    uint32 const spell = reward->kind == RewardKind::Ability ? reward->value : 0;
    auto before = Flush(player, state, spell);
    uint32 const nextXP = sObjectMgr->GetXPForLevel(before.level);
    uint64 applied = 0;
    auto expected = Delivery::Expected(before, *reward, nextXP, applied);
    // CALL owns its transaction. Execute queues one whole idempotent operation, never an outer transaction.
    CharacterDatabase.Execute(Acore::StringFormat("CALL mod_archipelago_v2_apply_reward({},{},{},{},{},{},{},{})",
        state.bindingId, index, before.level, before.money, nextXP, entry, count, ItemArguments(candidate)));
    auto outcome = Ordered(Acore::StringFormat(
        "SELECT applied,applied_value,COALESCE(item_guid,0),applied_at IS NOT NULL,ap_item,kind,value,sender "
        "FROM mod_archipelago_reward WHERE binding_id={} AND item_index={}", state.bindingId, index));
    auto o = outcome->Fetch();
    bool const committed = o[0].Get<bool>();
    uint32 const guid = candidate.item ? candidate.item->GetGUID().GetCounter() : 0;
    if (o[4].Get<int64>() != ap || o[5].Get<std::string>() != Delivery::KindName(reward->kind) ||
        o[6].Get<uint32>() != reward->value || o[7].Get<uint32>() != sender ||
        (committed ? (o[1].Get<uint64>() != applied || o[2].Get<uint32>() != guid || !o[3].Get<bool>()) :
        (o[1].Get<uint64>() || o[2].Get<uint32>() || o[3].Get<bool>())))
        Stop("reward receipt contradicts attempted application");
    auto saved = ReadSnapshot(player, state.bindingId, spell);
    if (!(saved == (committed ? expected : before)))
        Stop("reward character/progress outcome is incomplete or unknown");
    VerifyCandidate(player, state.bindingId, candidate, gear, committed);
    if (!committed)
        return false;
    Publish(player, saved, candidate);
    if (entry)
        Notify(player, Acore::StringFormat("ITEM\t{}\t{}\t{}", index, entry, sender));
    else
    {
        Notify(player, Acore::StringFormat("STATE\t{}\t{}\t{}\t{}", index, ap, applied, sender));
        ChatHandler(player->GetSession()).PSendSysMessage("Archipelago: {} received. Level cap {}, vouchers {}.",
            reward->name, Progression::Cap(*GetState(player)), saved.vouchers);
    }
    return true;
}

bool BuyStock(Player* player, uint16 stockIndex)
{
    if (!Available(player))
        return false;
    Attempt attempt(player);
    if (!attempt.acquired)
        return false;
    State const state = *GetState(player);
    auto stock = Ordered(Acore::StringFormat(
        "SELECT COUNT(*),COALESCE(MAX(item_entry),0),COALESCE(MAX(price),0),COALESCE(MAX(sold),0),"
        "(SELECT COUNT(*) FROM mod_archipelago_purchase p JOIN mod_archipelago_stock s "
        "ON s.binding_id=p.binding_id AND s.stock_index=p.stock_index AND s.item_entry=p.item_entry "
        "AND s.price=p.price WHERE p.binding_id={} AND p.stock_index={}) "
        "FROM mod_archipelago_stock WHERE binding_id={} AND stock_index={}",
        state.bindingId, stockIndex, state.bindingId, stockIndex));
    auto f = stock->Fetch();
    if (!f[0].Get<uint32>())
        return false;
    uint32 const entry = f[1].Get<uint32>(), price = f[2].Get<uint32>();
    auto gear = std::find_if(Gear.begin(), Gear.end(), [entry](GearDef const& row) { return row.entry == entry; });
    if (gear == Gear.end() || gear->quality == 5 || !(gear->classMask & player->getClassMask()) ||
        price != gear->price || !price || price > 8 || f[3].Get<bool>() != bool(f[4].Get<uint32>()))
        Stop("stock catalog/profile/price or purchase receipt is inconsistent");
    if (f[3].Get<bool>() || state.vouchers < price)
        return false;
    Candidate candidate;
    if (!Prepare(player, entry, 1, true, candidate))
        return false;
    auto before = Flush(player, state, 0);
    auto expected = before;
    expected.vouchers -= price;
    CharacterDatabase.Execute(Acore::StringFormat("CALL mod_archipelago_v2_purchase({},{},{})",
        state.bindingId, stockIndex, ItemArguments(candidate)));
    auto outcome = Ordered(Acore::StringFormat(
        "SELECT s.sold,COALESCE(p.item_guid,0),COALESCE(p.item_entry,0),COALESCE(p.price,0),s.item_entry,s.price "
        "FROM mod_archipelago_stock s LEFT JOIN mod_archipelago_purchase p "
        "ON p.binding_id=s.binding_id AND p.stock_index=s.stock_index "
        "WHERE s.binding_id={} AND s.stock_index={}", state.bindingId, stockIndex));
    auto o = outcome->Fetch();
    bool const committed = o[0].Get<bool>();
    if (o[4].Get<uint32>() != entry || o[5].Get<uint32>() != price ||
        (committed ? (o[1].Get<uint32>() != candidate.item->GetGUID().GetCounter() ||
        o[2].Get<uint32>() != entry || o[3].Get<uint32>() != price) :
        (o[1].Get<uint32>() || o[2].Get<uint32>() || o[3].Get<uint32>())))
        Stop("purchase receipt contradicts attempted application");
    auto saved = ReadSnapshot(player, state.bindingId, 0);
    if (!(saved == (committed ? expected : before)))
        Stop("purchase debit/character/progress outcome is incomplete or unknown");
    VerifyCandidate(player, state.bindingId, candidate, true, committed);
    if (!committed)
        return false;
    Publish(player, saved, candidate);
    Notify(player, Acore::StringFormat("SHOP\t{}\t{}", stockIndex, entry));
    return true;
}

bool EquipAuthorized(Player* player, uint32 itemGuid, uint8 equipmentSlot)
{
    Item* item = OwnedUsable(player, itemGuid);
    if (!item || equipmentSlot >= EQUIPMENT_SLOT_END)
        return false;
    uint16 const destination = uint16(INVENTORY_SLOT_BAG_0) << 8 | equipmentSlot;
    player->SwapItem(item->GetPos(), destination); // Patched CanUseItem waives required level only.
    return player->GetItemByPos(INVENTORY_SLOT_BAG_0, equipmentSlot) == item;
}

bool UseAuthorized(Player* player, uint32 itemGuid)
{
    Item* item = OwnedUsable(player, itemGuid);
    if (!item)
        return false;
    auto error = player->CanUseItem(item);
    if (error != EQUIP_ERR_OK)
    {
        player->SendEquipError(error, item, nullptr);
        return false;
    }
    if (item->GetTemplate()->InventoryType != INVTYPE_NON_EQUIP && !item->IsEquipped())
        return false;
    uint32 spell = 0;
    for (auto const& effect : item->GetTemplate()->Spells)
        if (effect.SpellId > 0 && effect.SpellTrigger == ITEM_SPELLTRIGGER_ON_USE)
        {
            auto info = sSpellMgr->GetSpellInfo(effect.SpellId);
            if (!info)
                return false;
            if (info->GetExplicitTargetMask() & ~(TARGET_FLAG_UNIT_MASK))
            {
                ChatHandler(player->GetSession()).SendSysMessage(
                    "Archipelago item use supports unit/self targets only. Ground/item targets need catalog support.");
                return false;
            }
            if (!spell)
                spell = effect.SpellId;
        }
    if (!spell)
        return false;
    Unit* target = player->GetSelectedUnit();
    if (!target)
        target = player;
    SpellCastTargets targets;
    targets.SetUnitTarget(target);
    WorldPacket packet(CMSG_USE_ITEM);
    packet << uint8(item->GetBagSlot()) << uint8(item->GetSlot()) << uint8(0) << spell << item->GetGUID() <<
        uint32(0) << uint8(0);
    targets.Write(packet);
    player->GetSession()->HandleUseItemOpcode(packet); // Normal checks, cooldowns, charges, targets and item scripts.
    return true; // Submitted to core, not a promise that CheckCast succeeded.
}

void RegisterDeliveryScripts() { new DeliveryWorld(); }
}
