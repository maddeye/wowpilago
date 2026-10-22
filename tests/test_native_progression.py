"""Execute production policies and extracted save methods with bounded core/DB stubs.

This does not replace patched-core compilation, real SQL rollback, or realm checks.
"""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def production_method(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


class NativeProgressionTests(unittest.TestCase):
    def run_save_methods(self, assertions):
        compiler = shutil.which("g++") or shutil.which("clang++")
        self.assertIsNotNone(compiler, "a C++17 compiler is required")
        production = (ROOT / "src/APProgression.cpp").read_text()
        extract = lambda signature: production_method(production, signature)
        # Only framework boundaries are replaced. Commit, Reconcile, the save hook,
        # and the deferred world flush execute their unmodified production bodies.
        source = r'''
#include "APProgression.h"
#include "APCatalog.h"
#include <array>
#include <cassert>
#include <future>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
using int64 = std::int64_t;
using namespace WoWPilago;
struct Stopped : std::runtime_error { using std::runtime_error::runtime_error; };
[[noreturn]] void Stop(char const* reason) { throw Stopped(reason); }
struct Snapshot
{
    uint32 level = 79, lastLevel = 79, xp = 123, inventory = 1;
    uint64 bank = 456;
    bool victory = false;
};
struct Transaction
{
    Snapshot staged;
    bool fullSave = false, progress = false;
    void Append(char const* sql, uint64 bank, uint32 level, int victory, uint64 binding)
    {
        assert(std::string(sql) == "UPDATE mod_archipelago_progress SET banked_xp={},last_level={},victory={} WHERE binding_id={}");
        assert(binding == 7);
        staged.bank = bank; staged.lastLevel = level; staged.victory = victory;
        progress = true;
    }
};
using CharacterDatabaseTransaction = std::shared_ptr<Transaction>;
struct Field
{
    uint64 value;
    template<class T> T Get() const { return T(value); }
};
struct Result
{
    std::array<Field, 4> fields;
    Field* Fetch() { return fields.data(); }
    bool NextRow() { return false; }
};
struct Database
{
    Snapshot durable;
    bool success = true, missing = false;
    int corrupt = -1;
    unsigned begins = 0, commits = 0, confirmations = 0;
    CharacterDatabaseTransaction BeginTransaction()
    {
        ++begins;
        auto tx = std::make_shared<Transaction>(); tx->staged = durable; return tx;
    }
    struct Completion { std::future<bool> m_future; };
    Completion AsyncCommitTransaction(CharacterDatabaseTransaction tx)
    {
        ++commits;
        if (success) durable = tx->staged;
        std::promise<bool> done; done.set_value(success); return {done.get_future()};
    }
    std::shared_ptr<Result> Query(char const*)
    {
        auto result = std::make_shared<Result>(); result->fields[0].value = 42; return result;
    }
    std::shared_ptr<Result> Query(char const*, uint32 guid)
    {
        assert(guid == 42); ++confirmations;
        if (missing) return nullptr;
        auto result = std::make_shared<Result>();
        result->fields = {{{durable.level}, {durable.lastLevel}, {durable.bank}, {durable.xp}}};
        if (corrupt >= 0) ++result->fields.at(corrupt).value;
        return result;
    }
} CharacterDatabase;
struct Cache { bool savePending = false; State state; };
enum class HighGuid { Player, Item };
struct ObjectGuid { ObjectGuid(HighGuid, uint32) {} };
constexpr unsigned PLAYER_XP = 1, PLAYER_FIELD_MAX_LEVEL = 2;
struct Item
{
    void SetBinding(bool) {} void ClearSoulboundTradeable(Player*) {} void SetNotRefundable(Player*) {}
};
class Player
{
public:
    Cache cache;
    uint32 level = 79, xp = 123, inventory = 2, zone = 0, area = 0;
    bool bound = true, inventoryDirty = true;
    unsigned saves = 0;
    Player() { cache.state.bindingId = 7; cache.state.capItems = 7; cache.state.bankedXP = 456; }
    uint32 GetLevel() const { return level; }
    uint32 GetUInt32Value(unsigned) const { return xp; }
    void SetUInt32Value(unsigned, unsigned) {} void InitTalentForLevel() {}
    Item* GetItemByGuid(ObjectGuid) { return nullptr; }
    void learnSpell(uint32) {} bool HasSpell(uint32) const { return false; }
    bool GetQuestRewardStatus(uint32) const { return false; }
    uint32 GetZoneId() const { return zone; }
    uint32 GetAreaId() const { return area; }
    void SaveToDB(CharacterDatabaseTransaction tx, bool, bool);
};
Player* online = nullptr;
namespace ObjectAccessor { Player* FindPlayer(ObjectGuid) { return online; } }
Cache* PlayerCache(Player const* player) { return &const_cast<Player*>(player)->cache; }
bool captureMilestone = false;
std::vector<std::pair<uint32, uint32>> milestoneObservations;
namespace WoWPilago
{
State* GetState(Player const* player) { return player->bound ? &PlayerCache(player)->state : nullptr; }
bool IsBoundHuman(Player const* player) { return player && player->bound; }
void RecordCheck(Player* player, int64 location)
{
    if (captureMilestone && location == 919600005 && player->cache.state.enabledChecks.count(location) &&
        !player->cache.state.completedChecks.count(location))
    {
        milestoneObservations.emplace_back(5, CharacterDatabase.durable.level);
        player->cache.state.completedChecks.insert(location);
    }
}
}
std::vector<uint32> explored;
void ZoneChecks(Player*, uint32 area) { explored.push_back(area); }
bool CanLearn(Player const*, uint32) { return false; }
constexpr std::array<uint32, 5> RidingSpells = {33388,33391,34090,34091,54197};
''' + extract("void Commit(") + r'''
struct PlayerScript
{
    virtual ~PlayerScript() = default;
    virtual void OnPlayerSaveToDB(Player*, CharacterDatabaseTransaction, bool, bool) = 0;
    virtual void OnPlayerLevelChanged(Player*, uint8) {}
};
struct SaveHook : PlayerScript
{
''' + extract("void OnPlayerSaveToDB(") + "\n" + extract("void OnPlayerLevelChanged(") + r'''
};
void Player::SaveToDB(CharacterDatabaseTransaction tx, bool, bool)
{
    ++saves; tx->fullSave = true; tx->staged.level = level; tx->staged.xp = xp;
    tx->staged.inventory = inventory;
    // Core clears dirty state while constructing the save, before commit completes.
    inventoryDirty = false;
    SaveHook().OnPlayerSaveToDB(this, tx, false, false);
}
namespace WoWPilago
{
''' + extract("void Reconcile(") + r'''
}
struct WorldScript { virtual ~WorldScript() = default; virtual void OnUpdate(uint32) = 0; };
struct WorldFlush : WorldScript
{
    uint32 _remaining = 5000;
''' + extract("void OnUpdate(") + r'''
};
template<class F> void mustStop(F call, char const* reason)
{
    bool stopped = false;
    try { call(); } catch (Stopped const& error)
    {
        stopped = true; assert(std::string(error.what()).find(reason) != std::string::npos);
    }
    assert(stopped);
}
int main()
{
''' + assertions + "\n}\n"
        with tempfile.TemporaryDirectory(prefix="wowpilago-save-methods-") as directory:
            path = pathlib.Path(directory)
            (path / "check.cpp").write_text(source)
            subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=undefined", "-fno-sanitize-recover=all",
                            "-I", str(ROOT / "src"), str(path / "check.cpp"),
                            "-o", str(path / "check")], check=True)
            subprocess.run([str(path / "check")], check=True)

    def test_level_milestone_waits_for_confirmed_full_save(self):
        self.run_save_methods(r'''
    captureMilestone = true;
    CharacterDatabase.durable.level = CharacterDatabase.durable.lastLevel = 4;
    Player player; online = &player; player.level = 5;
    player.cache.state.enabledChecks.insert(919600005);
    SaveHook().OnPlayerLevelChanged(&player, 4);
    assert(player.cache.savePending);
    assert(milestoneObservations.empty());
    assert(CharacterDatabase.durable.level == 4);
    WorldFlush flush;
    flush.OnUpdate(4999);
    assert(milestoneObservations.empty());
    flush.OnUpdate(1);
    assert(!player.cache.savePending && CharacterDatabase.confirmations == 1);
    assert((milestoneObservations == std::vector<std::pair<uint32,uint32>>{{5,5}}));
''')

    def test_level_milestone_is_not_published_after_failed_save_or_confirmation(self):
        self.run_save_methods(r'''
    captureMilestone = true;
    for (int failure : {-2,-1,0,1,2,3})
    {
        CharacterDatabase = Database();
        CharacterDatabase.durable.level = CharacterDatabase.durable.lastLevel = 4;
        CharacterDatabase.success = failure != -2;
        CharacterDatabase.missing = failure == -1;
        CharacterDatabase.corrupt = failure >= 0 ? failure : -1;
        milestoneObservations.clear();
        Player player; online = &player; player.level = 5;
        player.cache.state.enabledChecks.insert(919600005);
        SaveHook().OnPlayerLevelChanged(&player, 4);
        assert(milestoneObservations.empty());
        WorldFlush flush;
        mustStop([&] { flush.OnUpdate(5000); }, failure == -2 ? "transaction failed" : "not confirmed");
        assert(player.cache.savePending && milestoneObservations.empty());
    }
''')

    def test_milestone_recovers_on_relog_when_logout_precedes_flush(self):
        self.run_save_methods(r'''
    captureMilestone = true;
    CharacterDatabase.durable.level = CharacterDatabase.durable.lastLevel = 4;
    Player player; player.level = 5;
    player.cache.state.enabledChecks.insert(919600005);
    SaveHook().OnPlayerLevelChanged(&player, 4);
    assert(milestoneObservations.empty());
    // Normal logout saves before the five-second publisher runs.
    auto transaction = CharacterDatabase.BeginTransaction();
    player.SaveToDB(transaction, false, true);
    Commit(transaction);
    assert(milestoneObservations.empty() && CharacterDatabase.durable.level == 5);
    Player relogged; relogged.level = CharacterDatabase.durable.level;
    relogged.cache.state.enabledChecks.insert(919600005);
    assert(!relogged.cache.savePending);
    Reconcile(&relogged);
    assert((milestoneObservations == std::vector<std::pair<uint32,uint32>>{{5,5}}));
''')

    def test_reconcile_checks_current_zone_and_distinct_area(self):
        self.run_save_methods(r'''
    Player player; player.zone = 12; player.area = 9;
    Reconcile(&player);
    assert((explored == std::vector<uint32>{12, 9}));
    explored.clear(); player.area = 12;
    Reconcile(&player);
    assert((explored == std::vector<uint32>{12}));
    explored.clear(); player.bound = false;
    Reconcile(&player);
    assert(explored.empty());
''')

    def test_commit_false_stops_before_confirmation_even_when_progress_matches(self):
        self.run_save_methods(r'''
    for (bool success : {false, true})
    {
        CharacterDatabase = Database();
        CharacterDatabase.success = success;
        Player player; online = &player; player.cache.savePending = true;
        WorldFlush flush;
        if (success) flush.OnUpdate(5000);
        else mustStop([&] { flush.OnUpdate(5000); }, "transaction failed");
        assert(player.saves == 1 && CharacterDatabase.commits == 1);
        assert(!player.inventoryDirty);
        assert(CharacterDatabase.durable.level == player.level);
        assert(CharacterDatabase.durable.bank == player.cache.state.bankedXP);
        assert(CharacterDatabase.durable.inventory == (success ? 2u : 1u));
        assert(CharacterDatabase.confirmations == (success ? 1u : 0u));
        assert(player.cache.savePending == !success);
    }
''')

    def test_victory_reconcile_and_atomic_full_save_coordination(self):
        self.run_save_methods(r'''
    for (bool success : {false, true})
    {
        CharacterDatabase = Database(); CharacterDatabase.success = success;
        Player player; online = &player;
        Reconcile(&player);
        assert(!player.cache.state.victory && !player.cache.savePending);
        player.level = 80;
        Reconcile(&player);
        assert(player.cache.state.victory && player.cache.savePending);
        assert(CharacterDatabase.begins == 0 && CharacterDatabase.commits == 0);
        assert(CharacterDatabase.durable.level == 79 && !CharacterDatabase.durable.victory);
        WorldFlush flush;
        flush.OnUpdate(4999);
        assert(player.saves == 0);
        if (success) flush.OnUpdate(1);
        else mustStop([&] { flush.OnUpdate(1); }, "transaction failed");
        assert(CharacterDatabase.durable.level == (success ? 80u : 79u));
        assert(CharacterDatabase.durable.lastLevel == (success ? 80u : 79u));
        assert(CharacterDatabase.durable.victory == success);
        assert(player.cache.savePending == !success);
        unsigned saves = player.saves;
        if (success) { flush.OnUpdate(5000); assert(player.saves == saves); }
    }
    // The save hook uses actual level, not a stale cached victory bit.
    for (unsigned level : {79u, 80u})
    {
        CharacterDatabase = Database(); Player player; player.level = level;
        player.cache.state.victory = level != 80;
        auto tx = CharacterDatabase.BeginTransaction();
        player.SaveToDB(tx, false, false);
        assert(tx->fullSave && tx->progress && tx->staged.victory == (level == 80));
        assert(CharacterDatabase.durable.level == 79 && !CharacterDatabase.durable.victory);
        Commit(tx);
        assert(CharacterDatabase.durable.level == level);
        assert(CharacterDatabase.durable.victory == (level == 80));
    }
    // Missing or contradictory level, last_level, bank, or XP must not clear pending.
    for (int corrupt = -1; corrupt < 4; ++corrupt)
    {
        CharacterDatabase = Database();
        CharacterDatabase.missing = corrupt == -1; CharacterDatabase.corrupt = corrupt;
        Player player; online = &player; player.cache.savePending = true;
        WorldFlush flush;
        mustStop([&] { flush.OnUpdate(5000); }, "save outcome was not confirmed");
        assert(player.cache.savePending && CharacterDatabase.commits == 1);
    }
''')

    def test_cpp_policies(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        self.assertIsNotNone(compiler, "a C++17 compiler is required")
        source = r'''
#include "APProgression.h"
#include "APCatalog.h"
#include <cassert>
#include <limits>
using namespace WoWPilago;
using namespace WoWPilago::Progression;
int main()
{
    auto cost = [](unsigned level) -> std::uint64_t { return level * 100; };
    State state;
    assert(Cap(state) == 10);
    std::uint64_t award = 101;
    NormalizeXP(state, 9, 800, 10, award, cost);
    assert(award == 100 && state.bankedXP == 1);
    award = std::numeric_limits<std::uint64_t>::max();
    NormalizeXP(state, 10, 0, 10, award, cost);
    assert(award == 0 && state.bankedXP == 500);
    award = std::numeric_limits<std::uint64_t>::max();
    NormalizeXP(state, 1, 0, 10, award, cost);
    assert(award == 4500 && state.bankedXP == 500);
    // Final bonuses have already happened. The helper never multiplies either part again.
    state.bankedXP = 0;
    award = 150;
    NormalizeXP(state, 9, 800, 10, award, cost);
    assert(award == 100 && state.bankedXP == 50);
    // Exact crossing has no bank; repeated at-cap awards saturate, never wrap.
    state.bankedXP = 0;
    award = 100;
    NormalizeXP(state, 9, 800, 10, award, cost);
    assert(award == 100 && state.bankedXP == 0);
    for (unsigned i = 0; i < 100; ++i)
    {
        award = 99;
        NormalizeXP(state, 10, 0, 10, award, cost);
        assert(award == 0 && state.bankedXP <= 500);
    }
    assert(state.bankedXP == 500);
    // Reaching 80 discards overflow but does not erase an existing bank on an unrelated event.
    state.capItems = 7;
    award = std::numeric_limits<std::uint64_t>::max();
    NormalizeXP(state, 79, 7800, 80, award, cost);
    assert(award == 100 && state.bankedXP == 500);
    award = 10000;
    NormalizeXP(state, 80, 0, 80, award, cost);
    assert(award == 0 && state.bankedXP == 500);
    for (unsigned caps = 0; caps <= 7; ++caps)
    {
        state.capItems = caps;
        assert(Cap(state) == 10 + caps * 10);
    }
    // Every reservation boundary, all early/late unlock counts, and the 71-point ceiling.
    for (unsigned level = 1; level <= 80; ++level)
        for (unsigned unlocks = 0; unlocks <= 20; ++unlocks)
        {
            unsigned normal = level < 10 ? 0 : level - 9;
            unsigned reserved = 0;
            for (unsigned threshold = 15; threshold <= 70; threshold += 5)
                reserved += level >= threshold;
            assert(TalentPoints(level, unlocks) == normal - reserved + std::min(unlocks, reserved));
            assert(TalentPoints(level, unlocks) <= normal);
        }
    assert(TalentPoints(80, 0) == 59 && TalentPoints(80, 12) == 71);
    state.ridingFlags = 4;
    assert(!RidingEligible(state, 59, 2));
    assert(RidingEligible(state, 60, 0) && RidingEligible(state, 60, 1));
    assert(RidingEligible(state, 60, 2));
    state.ridingFlags = 8 | 16;
    assert(!RidingEligible(state, 80, 3) && !RidingEligible(state, 80, 4));
    state.ridingFlags |= 4;
    assert(!RidingEligible(state, 69, 3) && RidingEligible(state, 70, 3));
    assert(!RidingEligible(state, 76, 4) && RidingEligible(state, 77, 4));
    state.ridingFlags = 1;
    assert(!RidingEligible(state, 19, 0) && RidingEligible(state, 20, 0));
    assert(!RidingEligible(state, 80, 1));
    state.ridingFlags = 2;
    assert(!RidingEligible(state, 40, 1));
    state.ridingFlags |= 1;
    assert(!RidingEligible(state, 39, 1) && RidingEligible(state, 40, 1));
    for (unsigned zone : {3430,3433,3487,3524,3525,3557,4080})
        assert(Azeroth530Zone(zone));
    for (unsigned zone : {0,3483,3518,3519,3521,3522,3523,3703})
        assert(!Azeroth530Zone(zone));
    assert(MapExpansion(0) == 0 && MapExpansion(1) == 0);
    assert(MapExpansion(571) == 2 && MapExpansion(724) == 2);
    assert(MapExpansion(533) == 2 && MapExpansion(610) == 2);
    assert(MapExpansion(647) == 0); // Orgrimmar to Thunder Bluff is ordinary Azeroth travel.
    assert(MapExpansion(269) == 1 && MapExpansion(585) == 1);
    // Every curated instance is covered by the expansion policy.
    for (auto const& check : Checks)
        if (check.kind == CheckKind::Boss || check.kind == CheckKind::Dungeon || check.kind == CheckKind::Raid)
            assert(MapExpansion(check.mapId) == check.expansion);
    assert(Abilities.size() == 72 && Ranks.size() >= Abilities.size());
    for (auto const& ability : Abilities)
    {
        assert(ability.classId != 6);
        auto rank = std::find_if(Ranks.begin(), Ranks.end(), [&](RankDef const& row)
            { return row.spell == ability.baseSpell && row.baseSpell == ability.baseSpell; });
        assert(rank != Ranks.end() && rank->level == ability.level);
    }
}
'''
        with tempfile.TemporaryDirectory(prefix="wowpilago-progression-") as directory:
            path = pathlib.Path(directory)
            (path / "check.cpp").write_text(source)
            subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=undefined", "-I", str(ROOT / "src"),
                            str(path / "check.cpp"), "-o", str(path / "check")], check=True)
            subprocess.run([str(path / "check")], check=True)


if __name__ == "__main__":
    unittest.main()
