#pragma once
#include <algorithm>
#include <cstdint>
#include <vector>

class Player;

namespace WoWPilago
{
void ShowStatus(Player* player);
void RegisterMerchantScripts();

namespace Merchant
{
inline constexpr std::uint32_t Entry = 900500;
inline constexpr unsigned PageSize = 12;
inline constexpr unsigned Categories = 4;
inline constexpr std::uint32_t BuyAction = 1000;
struct Stock
{
    std::uint16_t index;
    std::uint32_t entry;
    unsigned price, category;
    bool sold;
};

inline unsigned Category(unsigned inventoryType, unsigned itemSet)
{
    if (itemSet)
        return 3;
    switch (inventoryType)
    {
        case 2: case 11: case 12:
            return 2;
        case 13: case 14: case 15: case 17: case 21: case 22: case 23: case 25: case 26: case 28:
            return 0;
        default:
            return 1;
    }
}

inline std::vector<Stock> Page(std::vector<Stock> const& stock, unsigned category, unsigned page)
{
    std::vector<Stock> rows;
    if (category >= Categories || page >= 10)
        return rows;
    unsigned skipped = 0;
    for (auto const& row : stock)
        if (row.category == category && skipped++ >= page * PageSize && rows.size() < PageSize)
            rows.push_back(row);
    return rows;
}

inline std::uint64_t RemainingCost(std::vector<Stock> const& stock)
{
    std::uint64_t total = 0;
    for (auto const& row : stock)
        if (!row.sold)
            total += row.price;
    return total;
}

inline Stock const* Selection(std::vector<Stock> const& stock, std::uint32_t action)
{
    if (action < BuyAction || action >= BuyAction + 120)
        return nullptr;
    auto it = std::find_if(stock.begin(), stock.end(), [action](Stock const& row)
        { return row.index == action - BuyAction; });
    return it == stock.end() || it->sold ? nullptr : &*it;
}
}
}
