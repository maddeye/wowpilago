#pragma once
#include "APCatalog.h"
#include <cstdint>
#include <string_view>

class Player;

namespace WoWPilago
{
// World-thread only. True means a new, verified application or an accepted core action.
// Already applied/sold work returns false and never issues another item or notification.
bool BuyStock(Player* player, std::uint16_t stockIndex);
bool EquipAuthorized(Player* player, std::uint32_t itemGuid, std::uint8_t equipmentSlot);
bool UseAuthorized(Player* player, std::uint32_t itemGuid);
bool ApplyQueuedReward(Player* player, std::uint32_t index, std::uint32_t sender);
void RegisterDeliveryScripts();

namespace Delivery
{
inline std::string_view KindName(RewardKind kind)
{
    switch (kind)
    {
        case RewardKind::LevelCap: return "level_cap";
        case RewardKind::Outland: return "outland";
        case RewardKind::Northrend: return "northrend";
        case RewardKind::Riding: return "riding";
        case RewardKind::Talent: return "talent";
        case RewardKind::Ability: return "ability";
        case RewardKind::Vouchers: return "vouchers";
        case RewardKind::Bag: return "bag";
        case RewardKind::Gold: return "gold";
        case RewardKind::Consumable: return "consumable";
        case RewardKind::Legendary: return "legendary";
    }
    return "";
}

inline RewardDef const* ValidateReward(std::int64_t id, std::string_view kind, std::uint32_t value,
    std::uint32_t classMask, bool allowed)
{
    auto row = FindById(Rewards, id);
    return allowed && row && KindName(row->kind) == kind && row->value == value &&
        (!row->classMask || (row->classMask & classMask)) ? row : nullptr;
}

inline unsigned Potion(unsigned level)
{
    return level < 3 ? 118 : level < 12 ? 858 : level < 21 ? 929 : level < 35 ? 1710 :
        level < 45 ? 3928 : level < 70 ? 13446 : 33447;
}

inline unsigned Gold(unsigned level)
{
    return level < 10 ? 1000 : level < 20 ? 10000 : level < 40 ? 50000 :
        level < 60 ? 200000 : level < 70 ? 500000 : 1000000;
}

struct Snapshot
{
    std::uint32_t level = 0, money = 0, xp = 0, cap = 0, access = 0, riding = 0, talent = 0;
    std::uint64_t bank = 0, vouchers = 0;
    std::uint32_t lastLevel = 0, victory = 0, ability = 0;

    bool operator==(Snapshot const& b) const
    {
        return level == b.level && money == b.money && xp == b.xp && cap == b.cap &&
            access == b.access && riding == b.riding && talent == b.talent && bank == b.bank &&
            vouchers == b.vouchers && lastLevel == b.lastLevel && victory == b.victory && ability == b.ability;
    }
};

inline Snapshot Expected(Snapshot s, RewardDef const& reward, unsigned nextXP, std::uint64_t& applied)
{
    applied = reward.value;
    switch (reward.kind)
    {
        case RewardKind::LevelCap:
            applied = s.cap < 7 ? 10 : 0;
            if (s.cap < 7)
            {
                if (s.level == 10 + 10 * s.cap)
                    s.xp = static_cast<std::uint32_t>(std::min<std::uint64_t>(s.bank, nextXP / 2));
                ++s.cap;
                s.bank = 0;
            }
            break;
        case RewardKind::Outland: s.access |= 1; break;
        case RewardKind::Northrend: s.access |= 2; break;
        case RewardKind::Riding: s.riding |= 1u << reward.value; break;
        case RewardKind::Talent:
            applied = s.talent < 12 ? 1 : 0;
            s.talent = std::min(12u, s.talent + 1);
            break;
        case RewardKind::Ability: s.ability = 1; break;
        case RewardKind::Vouchers: s.vouchers += reward.value; break;
        case RewardKind::Gold:
            applied = Gold(s.level);
            s.money += static_cast<std::uint32_t>(applied);
            break;
        case RewardKind::Bag: case RewardKind::Legendary: applied = 1; break;
        case RewardKind::Consumable: applied = 5; break;
    }
    s.lastLevel = s.level;
    return s;
}
}
}
