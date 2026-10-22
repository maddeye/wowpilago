#pragma once
#include <algorithm>
#include <cstdint>
#include <map>
#include <set>

class Player;
class Item;

namespace WoWPilago
{
struct State
{
    std::uint64_t bindingId = 0;
    std::uint32_t characterGuid = 0;
    std::uint8_t classId = 0, raceId = 0, capItems = 0;
    std::uint64_t bankedXP = 0;
    std::uint8_t accessFlags = 0, ridingFlags = 0, talentUnlocks = 0;
    std::uint32_t vouchers = 0;
    bool victory = false;
    std::set<std::int64_t> allowedRewards, enabledChecks, completedChecks;
    std::set<std::uint32_t> abilityUnlocks;
    std::map<std::uint32_t, std::uint32_t> authorizedItems;
};

State* GetState(Player const* player);
void RefreshState(Player* player);
bool IsBoundHuman(Player const* player);
bool IsAuthorized(Player const* player, Item const* item);
void RecordCheck(Player* player, std::int64_t location);
void Reconcile(Player* player);
void RegisterProgressionScripts();

namespace Progression
{
inline unsigned Cap(State const& state) { return 10 + 10 * std::min<unsigned>(7, state.capItems); }

// finalXP has already received rested, RaF and regional bonuses.
template<class XPForLevel>
void NormalizeXP(State& state, unsigned level, std::uint64_t currentXP, unsigned cap,
    std::uint64_t& finalXP, XPForLevel xpForLevel)
{
    cap = std::min(cap, Cap(state));
    std::uint64_t room = 0;
    if (level < cap)
    {
        for (unsigned next = level; next < cap; ++next)
            room += xpForLevel(next);
        room -= std::min(room, currentXP);
    }
    std::uint64_t const accepted = std::min(finalXP, room);
    if (cap < 80 && level <= cap)
    {
        std::uint64_t const limit = xpForLevel(cap) / 2;
        state.bankedXP = std::min(state.bankedXP, limit);
        state.bankedXP += std::min(finalXP - accepted, limit - state.bankedXP);
    }
    finalXP = accepted;
}

inline unsigned TalentPoints(unsigned level, unsigned unlocks)
{
    unsigned const normal = level < 10 ? 0 : std::min(71u, level - 9);
    unsigned const reserved = level < 15 ? 0 : std::min(12u, (level - 10) / 5);
    return normal - reserved + std::min(unlocks, reserved);
}

inline bool RidingEligible(State const& state, unsigned level, unsigned tier)
{
    if (tier > 4)
        return false;
    unsigned const levels[] = {20, 40, 60, 70, 77};
    if (level < levels[tier])
        return false;
    // Expert supplies its ground prerequisites, without making useful rewards mandatory.
    bool const expert = level >= 60 && (state.ridingFlags & 4);
    if (tier < 2 && expert)
        return true;
    return (state.ridingFlags & (1u << tier)) && (tier != 1 || (state.ridingFlags & 1)) &&
        (tier < 3 || expert);
}

inline bool Azeroth530Zone(unsigned zone)
{
    switch (zone)
    {
        case 3430: case 3433: case 3487: case 3524: case 3525: case 3557: case 4080:
            return true;
        default:
            return false;
    }
}

inline unsigned MapExpansion(unsigned map)
{
    switch (map)
    {
        case 269: case 532: case 534: case 540: case 542: case 543: case 544: case 545:
        case 546: case 547: case 548: case 550: case 552: case 553: case 554: case 555:
        case 556: case 557: case 558: case 560: case 564: case 565: case 566: case 568: case 580:
        case 585: case 598:
            return 1;
        case 533: case 571: case 574: case 575: case 576: case 578: case 592: case 594:
        case 595: case 596: case 599: case 600: case 601: case 602: case 603: case 604:
        case 607: case 608: case 610: case 612: case 613: case 614: case 615: case 616:
        case 619: case 620: case 621: case 622: case 623: case 624: case 628: case 631:
        case 632: case 641: case 642: case 649: case 650: case 658: case 668: case 672:
        case 673: case 712: case 713: case 718: case 724:
            return 2;
        default:
            return 0;
    }
}
}
}
