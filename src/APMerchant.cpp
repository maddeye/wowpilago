#include "APMerchant.h"
#include "APCatalog.h"
#include "APDelivery.h"
#include "APProgression.h"
#include "Chat.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "ScriptedGossip.h"
#include "WorldSession.h"
#include <sstream>

namespace WoWPilago
{
namespace
{
using namespace Acore::ChatCommands;
enum MenuAction : uint32 { Home = 1, Status = 2, Navigate = 100 };
char const* const CategoryNames[] = {"Weapons / shields / held items", "Armor / cloaks", "Jewelry / trinkets", "Set pieces"};

bool CanInteract(Player* player, Creature* creature)
{
    return creature && creature->GetEntry() == Merchant::Entry && IsBoundHuman(player) &&
        player->GetNPCIfCanInteractWith(creature->GetGUID(), UNIT_NPC_FLAG_GOSSIP) == creature;
}

bool LoadStock(Player* player, std::vector<Merchant::Stock>& stock, uint32& balance)
{
    State const* state = GetState(player);
    if (!state || !IsBoundHuman(player))
        return false;
    // Module statements cannot extend core prepared-statement enums. All substitutions are server-owned integers.
    QueryResult result = CharacterDatabase.Query(
        "SELECT s.stock_index,s.item_entry,s.price,s.sold,p.vouchers FROM mod_archipelago_stock s "
        "JOIN mod_archipelago_binding b ON b.id=s.binding_id "
        "JOIN mod_archipelago_progress p ON p.binding_id=b.id "
        "WHERE b.id={} AND b.character_guid={} AND b.status<>'archived' AND b.protocol_version=2 "
        "ORDER BY s.stock_index", state->bindingId, player->GetGUID().GetCounter());
    if (!result)
        return false;
    do
    {
        Field* fields = result->Fetch();
        uint16 const index = fields[0].Get<uint16>();
        uint32 const entry = fields[1].Get<uint32>();
        ItemTemplate const* item = sObjectMgr->GetItemTemplate(entry);
        auto gear = std::find_if(Gear.begin(), Gear.end(), [entry](GearDef const& row) { return row.entry == entry; });
        // Fail the entire view closed on tampering, rather than hiding an invalid entry in an otherwise usable shop.
        if (index >= 120 || !item || item->Quality == ITEM_QUALITY_LEGENDARY ||
            gear == Gear.end() || gear->quality == ITEM_QUALITY_LEGENDARY ||
            !(gear->classMask & (1u << (player->getClass() - 1))) ||
            fields[2].Get<uint8>() != gear->price)
            return false;
        stock.push_back({index, entry, fields[2].Get<uint8>(),
            Merchant::Category(item->InventoryType, item->ItemSet), fields[3].Get<bool>()});
        balance = fields[4].Get<uint32>();
    } while (result->NextRow());
    return stock.size() >= 30 && stock.size() <= 120;
}

std::string ItemLink(uint32 entry)
{
    ItemTemplate const* item = sObjectMgr->GetItemTemplate(entry);
    if (!item || item->Quality > ITEM_QUALITY_HEIRLOOM)
        return "Unknown item " + std::to_string(entry);
    std::ostringstream link;
    link << "|c" << std::hex << ItemQualityColors[item->Quality] << "|Hitem:" << std::dec << entry
        << ":0:0:0:0:0:0:0:0|h[" << item->Name1 << "]|h|r";
    return link.str();
}

void ShowMenu(Player* player, Creature* creature, unsigned category = Merchant::Categories, unsigned page = 0)
{
    ClearGossipMenuFor(player);
    if (!CanInteract(player, creature))
    {
        CloseGossipMenuFor(player);
        return;
    }
    std::vector<Merchant::Stock> stock;
    uint32 balance = 0;
    if (!LoadStock(player, stock, balance))
    {
        ChatHandler(player->GetSession()).SendSysMessage("Personal stock unavailable or invalid. No purchase was made.");
        CloseGossipMenuFor(player);
        return;
    }
    AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Vouchers: " + std::to_string(balance) +
        " | Remaining total cost: " + std::to_string(Merchant::RemainingCost(stock)), Home, Home);
    if (category >= Merchant::Categories)
    {
        for (unsigned i = 0; i < Merchant::Categories; ++i)
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, CategoryNames[i], Home, Navigate + i * 10);
        AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Archipelago status / command help", Home, Status);
    }
    else
    {
        AddGossipItemFor(player, GOSSIP_ICON_CHAT, std::string(CategoryNames[category]) + " | Page " +
            std::to_string(page + 1) + " | Back to categories", Home, Home);
        for (auto const& row : Merchant::Page(stock, category, page))
        {
            std::string const label = "#" + std::to_string(row.index) + " " + ItemLink(row.entry) +
                " | " + std::to_string(row.price) + " vouchers" + (row.sold ? " | SOLD" : " | Buy one");
            if (row.sold)
                AddGossipItemFor(player, GOSSIP_ICON_CHAT, label, Home, Navigate + category * 10 + page);
            else
                AddGossipItemFor(player, GOSSIP_ICON_CHAT, label, Home, Merchant::BuyAction + row.index,
                    "Buy one for " + std::to_string(row.price) + " vouchers?", 0, false);
        }
        if (page)
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Previous page", Home, Navigate + category * 10 + page - 1);
        if (!Merchant::Page(stock, category, page + 1).empty())
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Next page", Home, Navigate + category * 10 + page + 1);
    }
    SendGossipMenuFor(player, DEFAULT_GOSSIP_MESSAGE, creature->GetGUID());
}

bool Purchase(Player* player, Creature* creature, uint32 action)
{
    if (!CanInteract(player, creature))
        return false;
    std::vector<Merchant::Stock> stock;
    uint32 balance = 0;
    if (!LoadStock(player, stock, balance))
        return false;
    auto const* row = Merchant::Selection(stock, action);
    if (!row || balance < row->price)
    {
        ChatHandler(player->GetSession()).SendSysMessage("Entry sold, invalid, or not enough vouchers.");
        return false;
    }
    // Delivery owns all locking, revalidation, debit and grant operations.
    bool const bought = BuyStock(player, row->index);
    ChatHandler(player->GetSession()).SendSysMessage(bought ? "Purchase complete. Reopen the merchant for updated stock." :
        "Purchase not completed. Check bag space, vouchers and item requirements, then reopen the merchant.");
    return bought;
}

class ArchipelagoMerchant final : public CreatureScript
{
public:
    ArchipelagoMerchant() : CreatureScript("archipelago_merchant") { }
    bool OnGossipHello(Player* player, Creature* creature) override
    {
        ShowMenu(player, creature);
        return true;
    }
    bool OnGossipSelect(Player* player, Creature* creature, uint32 sender, uint32 action) override
    {
        if (sender != Home || !CanInteract(player, creature))
        {
            CloseGossipMenuFor(player);
            return true;
        }
        if (action == Status)
            ShowStatus(player);
        else if (action >= Navigate && action < Navigate + Merchant::Categories * 10)
        {
            ShowMenu(player, creature, (action - Navigate) / 10, (action - Navigate) % 10);
            return true;
        }
        else if (action >= Merchant::BuyAction)
        {
            Purchase(player, creature, action);
            // Delivery may finish asynchronously. A fresh interaction reloads the durable stock.
            CloseGossipMenuFor(player);
            return true;
        }
        ShowMenu(player, creature);
        return true;
    }
};

class ArchipelagoCommands final : public CommandScript
{
public:
    ArchipelagoCommands() : CommandScript("archipelago_personal_commands") { }
    ChatCommandTable GetCommands() const override
    {
        static ChatCommandTable const personal =
        {
            {"status", HandleStatus, SEC_PLAYER, Console::No},
            {"equip", HandleEquip, SEC_PLAYER, Console::No},
            {"use", HandleUse, SEC_PLAYER, Console::No},
            {"buy", HandleBuy, SEC_PLAYER, Console::No},
            {"", HandleStatus, SEC_PLAYER, Console::No}
        };
        static ChatCommandTable const commands = {{"archipelago", personal}};
        return commands;
    }
    static bool HandleStatus(ChatHandler* handler)
    {
        ShowStatus(handler->GetPlayer());
        return true;
    }
    static bool HandleEquip(ChatHandler* handler, uint32 itemGUID, uint8 equipmentSlot)
    {
        if (!IsBoundHuman(handler->GetPlayer()))
            return false;
        if (!EquipAuthorized(handler->GetPlayer(), itemGUID, equipmentSlot))
            handler->SendSysMessage("Equip failed. Use an owned authorized item GUID and slot 0..18. Normal proficiency and gear rules still apply.");
        return true;
    }
    static bool HandleUse(ChatHandler* handler, uint32 itemGUID)
    {
        if (!IsBoundHuman(handler->GetPlayer()))
            return false;
        if (!UseAuthorized(handler->GetPlayer(), itemGUID))
            handler->SendSysMessage("Use failed. Use an owned authorized item GUID. Normal target, cooldown and combat rules still apply.");
        return true;
    }
    static bool HandleBuy(ChatHandler* handler, uint16 stockIndex)
    {
        Player* player = handler->GetPlayer();
        Unit* selected = player->GetSelectedUnit();
        if (!selected || stockIndex >= 120 || !CanInteract(player, selected->ToCreature()))
            handler->SendSysMessage("Select a nearby Archipelago merchant and use .archipelago buy <stock index>.");
        else
            Purchase(player, selected->ToCreature(), Merchant::BuyAction + stockIndex);
        return true;
    }
};
}

void ShowStatus(Player* player)
{
    ChatHandler chat(player->GetSession());
    State const* state = GetState(player);
    if (!state || !IsBoundHuman(player))
    {
        chat.SendSysMessage("Archipelago: no active personal binding. Ask the bridge operator to bind this character.");
        return;
    }
    QueryResult binding = CharacterDatabase.Query(
        "SELECT seed_name,team,slot,status,(heartbeat >= NOW() - INTERVAL 30 SECOND) "
        "FROM mod_archipelago_binding WHERE id={} AND character_guid={} AND status<>'archived'",
        state->bindingId, player->GetGUID().GetCounter());
    if (binding)
    {
        Field* row = binding->Fetch();
        chat.PSendSysMessage("Archipelago seed {} | team {} slot {} | bridge {} | heartbeat {}",
            row[0].Get<std::string>(), row[1].Get<uint32>(), row[2].Get<uint32>(),
            row[3].Get<std::string>(), row[4].Get<bool>() ? "recent" : "stale / offline");
    }
    chat.PSendSysMessage("Level {} / cap {} | XP bank {} | talent unlocks {} / 12 | earned talent points {}",
        player->GetLevel(), Progression::Cap(*state), state->bankedXP, state->talentUnlocks,
        Progression::TalentPoints(player->GetLevel(), state->talentUnlocks));
    char const* const riding[] = {"Apprentice", "Journeyman", "Expert", "Artisan", "Cold Weather"};
    std::string available, pending;
    for (unsigned tier = 0; tier < 5; ++tier)
        if (Progression::RidingEligible(*state, player->GetLevel(), tier))
            available += std::string(riding[tier]) + "; ";
        else if (state->ridingFlags & (1u << tier))
            pending += std::string(riding[tier]) + "; ";
    chat.PSendSysMessage("Riding available: {} | received but pending level / prerequisite: {}",
        available.empty() ? "none" : available, pending.empty() ? "none" : pending);
    unsigned const normalPoints = player->GetLevel() < 10 ? 0 : player->GetLevel() - 9;
    unsigned const reservations = normalPoints - Progression::TalentPoints(player->GetLevel(), 0);
    chat.PSendSysMessage("Talent unlocks pending level eligibility: {}",
        state->talentUnlocks > reservations ? state->talentUnlocks - reservations : 0);
    unsigned remaining = 0;
    for (auto check : state->enabledChecks)
        remaining += !state->completedChecks.count(check);
    QueryResult rewards = CharacterDatabase.Query(
        "SELECT COUNT(*) FROM mod_archipelago_reward WHERE binding_id={} AND applied=0", state->bindingId);
    std::vector<Merchant::Stock> stock;
    uint32 balance = 0;
    if (LoadStock(player, stock, balance))
        chat.PSendSysMessage("Vouchers {} | remaining shop cost {} | remaining checks {} | pending deliveries {}",
            balance, Merchant::RemainingCost(stock), remaining,
            rewards ? std::to_string((*rewards)[0].Get<uint32>()) : "unknown");
    else
        chat.PSendSysMessage("Personal stock unavailable | cached vouchers {} | remaining checks {} | pending deliveries {}",
            state->vouchers, remaining, rewards ? std::to_string((*rewards)[0].Get<uint32>()) : "unknown");
    chat.SendSysMessage(".archipelago status | buy <stock index> at selected merchant | equip <item GUID> <slot 0..18> | use <item GUID>");
    for (auto const& item : state->authorizedItems)
        chat.PSendSysMessage("Authorized item GUID {}: {}", item.first, ItemLink(item.second));
}

void RegisterMerchantScripts()
{
    new ArchipelagoMerchant();
    new ArchipelagoCommands();
}
}
