"""Execute production delivery policy/serialization, without pretending to be a realm test."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def function(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


class NativeDelivery(unittest.TestCase):
    def run_cpp(self, code):
        compiler = shutil.which("g++")
        if not compiler:
            self.skipTest("g++ unavailable")
        with tempfile.TemporaryDirectory(prefix="delivery-test-") as directory:
            source = pathlib.Path(directory) / "test.cpp"
            binary = pathlib.Path(directory) / "test"
            source.write_text(code)
            subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=undefined", "-fno-sanitize-recover=all", "-I", str(ROOT / "src"),
                            str(source), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_catalog_and_effect_policy(self):
        self.run_cpp(r'''
#include "APDelivery.h"
#include <cassert>
#include <limits>
using namespace WoWPilago;
using namespace WoWPilago::Delivery;
int main()
{
    unsigned const classes[] = {1,2,3,4,5,7,8,9,11};
    for (auto const& r : Rewards)
    {
        for (auto c : classes)
        {
            unsigned mask = 1u << (c - 1);
            assert(bool(ValidateReward(r.id, KindName(r.kind), r.value, mask, true)) ==
                (!r.classMask || bool(r.classMask & mask)));
            assert(!ValidateReward(r.id, KindName(r.kind), r.value, mask, false));
            assert(!ValidateReward(r.id, "forged", r.value, mask, true));
            assert(!ValidateReward(r.id, KindName(r.kind), r.value + 1, mask, true));
        }
    }
    assert(!ValidateReward(919000001, "consumable", 1, 1, true));
    assert(!ValidateReward(-1, "gold", 1, 1, true));
    unsigned const thresholds[] = {1,3,12,21,35,45,70};
    unsigned const potions[] = {118,858,929,1710,3928,13446,33447};
    for (unsigned level = 1; level <= 80; ++level)
    {
        unsigned i = 0;
        while (i < 6 && level >= thresholds[i + 1]) ++i;
        assert(Potion(level) == potions[i]);
        assert(Gold(level) == (level < 10 ? 1000u : level < 20 ? 10000u :
            level < 40 ? 50000u : level < 60 ? 200000u : level < 70 ? 500000u : 1000000u));
        for (auto const& r : Rewards)
        {
            Snapshot s;
            s.level = level; s.money = 123; s.xp = 456; s.cap = 7;
            s.bank = 100; s.vouchers = 50; s.lastLevel = level; s.victory = 1;
            std::uint64_t applied = 0;
            auto t = Expected(s, r, 1000, applied);
            assert(t.level == s.level && t.victory == s.victory && t.lastLevel == level);
            assert(t.xp == s.xp);
            assert(t.bank == s.bank); // No unrelated reward may clear the XP bank.
            assert(t.money == s.money + (r.kind == RewardKind::Gold ? Gold(level) : 0));
            assert(t.vouchers == s.vouchers + (r.kind == RewardKind::Vouchers ? r.value : 0));
            assert(t.access == (r.kind == RewardKind::Outland ? 1u : r.kind == RewardKind::Northrend ? 2u : 0u));
            assert(t.riding == (r.kind == RewardKind::Riding ? 1u << r.value : 0u));
            assert(t.talent == (r.kind == RewardKind::Talent ? 1u : 0u));
            assert(t.ability == (r.kind == RewardKind::Ability ? 1u : 0u));
            if (r.kind == RewardKind::Consumable) assert(applied == 5);
            if (r.kind == RewardKind::Bag || r.kind == RewardKind::Legendary) assert(applied == 1);
            if (r.kind == RewardKind::LevelCap) assert(applied == 0);
        }
    }
    auto cap = FindById(Rewards, 919100001);
    auto talent = FindById(Rewards, 919100020);
    for (unsigned n = 0; n <= 7; ++n)
        for (unsigned level : {1u, 10 + 10 * n})
            for (std::uint64_t bank : {0ull, 1ull, 499ull, 500ull, 900ull})
            {
                Snapshot s;
                s.cap = n; s.level = level; s.xp = 37; s.bank = bank;
                std::uint64_t applied;
                auto t = Expected(s, *cap, 1000, applied);
                assert(t.cap == std::min(7u, n + 1));
                assert(t.bank == (n < 7 ? 0 : bank));
                assert(t.xp == (n < 7 && level == 10 + 10 * n ? std::min(bank, std::uint64_t(500)) : 37));
                assert(applied == (n < 7 ? 10 : 0));
            }
    for (unsigned n = 0; n <= 12; ++n)
    {
        Snapshot s; s.talent = n;
        std::uint64_t applied;
        auto t = Expected(s, *talent, 1, applied);
        assert(t.talent == std::min(12u, n + 1));
        assert(applied == (n < 12 ? 1 : 0));
    }
    Snapshot s;
    auto t = s;
    assert(t == s);
    ++t.bank; assert(!(t == s)); t = s;
    ++t.vouchers; assert(!(t == s)); t = s;
    ++t.money; assert(!(t == s)); t = s;
    ++t.xp; assert(!(t == s)); t = s;
    ++t.ability; assert(!(t == s));
}
''')

    def test_actual_serialization_and_zero_item_arguments(self):
        source = (ROOT / "src/APDelivery.cpp").read_text()
        helpers = "\n".join(function(source, signature) for signature in (
            "std::string Quoted(", "std::string Charges(", "std::string Enchantments(",
            "std::string ItemArguments("))
        self.run_cpp(r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <memory>
#include <sstream>
#include <string>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
enum EnchantmentSlot { FIRST };
constexpr unsigned MAX_ITEM_PROTO_SPELLS = 5, MAX_ENCHANTMENT_SLOT = 12;
enum Fields { ITEM_FIELD_CREATOR, ITEM_FIELD_GIFTCREATOR, ITEM_FIELD_DURATION, ITEM_FIELD_FLAGS,
    ITEM_FIELD_DURABILITY, ITEM_FIELD_CREATE_PLAYED_TIME };
struct Guid { unsigned value; unsigned GetCounter() const { return value; } };
struct Item
{
    Guid GetGUID() const { return {11}; }
    Guid GetGuidValue(Fields f) const { return {unsigned(f + 21)}; }
    int GetInt32Value(Fields) const { return -60; }
    unsigned GetUInt32Value(Fields f) const { return f == ITEM_FIELD_FLAGS ? 1 : f + 100; }
    int GetItemRandomPropertyId() const { return -17; }
    int GetSpellCharges(unsigned i) const { return -int(i + 1); }
    unsigned GetEnchantmentId(EnchantmentSlot i) const { return i + 100; }
    unsigned GetEnchantmentDuration(EnchantmentSlot i) const { return i + 200; }
    unsigned GetEnchantmentCharges(EnchantmentSlot i) const { return i + 300; }
    std::string GetText() const { return "apostrophe's"; }
};
struct Candidate { std::unique_ptr<Item> item; unsigned bagGuid = 0; uint8 bag = 0, slot = 0; };
struct DB
{
    void EscapeString(std::string& s)
    {
        auto pos = s.find('\'');
        if (pos != std::string::npos) s.insert(pos, "\\");
    }
} CharacterDatabase;
namespace Acore
{
template<class... Args> std::string StringFormat(std::string pattern, Args const&... args)
{
    std::vector<std::string> values;
    auto add = [&](auto const& value)
    {
        std::ostringstream s;
        // fmt renders uint8 numerically, unlike iostream.
        if constexpr (sizeof(value) == 1) s << unsigned(value); else s << value;
        values.push_back(s.str());
    };
    (add(args), ...);
    for (auto const& value : values) pattern.replace(pattern.find("{}"), 2, value);
    return pattern;
}
}
''' + helpers + r'''
int main()
{
    Candidate c;
    auto zero = ItemArguments(c);
    assert(zero == "0,0,0,0,0,0,0,'',0,'',0,0,0,''");
    assert(std::count(zero.begin(), zero.end(), ',') == 13); // +7 reward / +2 purchase = 21 / 16.
    c.item = std::make_unique<Item>(); c.bagGuid = 55; c.bag = 19; c.slot = 8;
    auto args = ItemArguments(c);
    assert(args.find("11,55,19,8,21,22,-60,'-1 -2 -3 -4 -5 ',1,'") == 0);
    assert(args.find("111 211 311 ") != std::string::npos);
    assert(args.find("',-17,104,105,'apostrophe\\'s'") != std::string::npos);
    assert(std::count(args.begin(), args.end(), ',') == 13);
}
''')

    def test_actual_candidate_outcome_verification(self):
        source = (ROOT / "src/APDelivery.cpp").read_text()
        verify = function(source, "void VerifyCandidate(")
        self.run_cpp(r'''
#include <array>
#include <cassert>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
struct Field
{
    unsigned value;
    template<class T> T Get() const { return T(value); }
};
struct Result
{
    std::array<Field,5> fields;
    Field* Fetch() { return fields.data(); }
};
std::shared_ptr<Result> result = std::make_shared<Result>();
auto Ordered(std::string const&) { return result; }
[[noreturn]] void Stop(char const*) { throw std::runtime_error("fail-stop"); }
namespace Acore
{
template<class... Args> std::string StringFormat(char const*, Args const&...) { return "query"; }
}
struct Player {};
struct Guid { unsigned GetCounter() const { return 42; } };
struct Item { Guid GetGUID() const { return {}; } unsigned GetEntry() const { return 19019; } };
struct Candidate { std::unique_ptr<Item> item; uint32 bagGuid = 0; uint8 slot = 23; };
std::string ItemMatches(Player*, Item const*, uint32, uint8) { return "metadata predicate"; }
''' + verify + r'''
int main()
{
    Player player;
    Candidate c; c.item = std::make_unique<Item>();
    auto check = [&](std::array<unsigned,5> fields, bool gear, bool applied, bool mustStop)
    {
        for (unsigned i = 0; i < 5; ++i) result->fields[i].value = fields[i];
        bool stopped = false;
        try { VerifyCandidate(&player, 7, c, gear, applied); }
        catch (std::runtime_error const&) { stopped = true; }
        assert(stopped == mustStop);
    };
    check({1,1,1,1,1}, true, true, false);
    check({1,1,1,0,0}, false, true, false);
    check({0,0,0,0,0}, true, false, false);
    check({0,0,0,0,0}, false, false, false);
    check({0,1,1,1,1}, true, true, true); // Wrong serialized data or placement.
    check({1,1,1,1,0}, true, true, true); // Authorization belongs to another binding/entry.
    check({1,1,2,1,1}, true, true, true); // Duplicate placement.
    check({1,1,1,0,0}, true, true, true); // Receipt without authorization.
    check({1,1,1,1,1}, false, true, true); // Unexpected authorization for a potion/bag.
    check({0,1,0,0,0}, true, false, true); // Partial item without receipt.
    check({0,0,1,0,0}, true, false, true); // Partial placement without receipt.
    check({0,0,0,1,0}, true, false, true); // Partial authorization without receipt.
}
''')

    def test_ordered_query_executes_callback_and_fails_closed(self):
        source = (ROOT / "src/APDelivery.cpp").read_text()
        ordered = function(source, "QueryResult Ordered(")
        self.run_cpp(r'''
#include <cassert>
#include <chrono>
#include <functional>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
using QueryResult = std::shared_ptr<unsigned>;
[[noreturn]] void Stop(char const*) { throw std::runtime_error("fail-stop"); }
struct Callback
{
    QueryResult value;
    std::function<void(QueryResult)> fn;
    unsigned polls = 0;
    void WithCallback(std::function<void(QueryResult)> f) { fn = f; }
    bool InvokeIfReady() { if (++polls < 3) return false; fn(value); return true; }
};
struct DB
{
    bool fail = false;
    Callback AsyncQuery(std::string const&) { return {fail ? nullptr : std::make_shared<unsigned>(42), {}, 0}; }
} CharacterDatabase;
''' + ordered + r'''
int main()
{
    assert(*Ordered("SELECT durable outcome") == 42);
    CharacterDatabase.fail = true;
    bool stopped = false;
    try { Ordered("SELECT unavailable"); } catch (std::runtime_error const&) { stopped = true; }
    assert(stopped);
}
''')


if __name__ == "__main__":
    unittest.main()
