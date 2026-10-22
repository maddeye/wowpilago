"""Compiled production check producers with core/DB boundary stubs, not realm evidence."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from test_native_progression import production_method

ROOT = pathlib.Path(__file__).resolve().parents[1]


class NativeCheckCreditTests(unittest.TestCase):
    def run_credit(self, assertions):
        compiler = shutil.which("g++") or shutil.which("clang++")
        self.assertIsNotNone(compiler, "a C++17 compiler is required")
        production = (ROOT / "src/APProgression.cpp").read_text()
        extract = lambda signature: production_method(production, signature)
        source = r'''
#include "APProgression.h"
#include "APCatalog.h"
#include <cassert>
#include <future>
#include <memory>
#include <stdexcept>
#include <string>
#include <tuple>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
using int64 = std::int64_t;
using namespace WoWPilago;
struct Stopped : std::runtime_error { using std::runtime_error::runtime_error; };
[[noreturn]] void Stop(char const* reason) { throw Stopped(reason); }
constexpr unsigned TEAM_ALLIANCE = 0, RAID_DIFFICULTY_25MAN_NORMAL = 1;
struct Map
{
    uint32 id = 556, instance = 17, difficulty = 0;
    bool regular = true, raid = false;
    uint32 GetId() const { return id; }
    uint32 GetInstanceId() const { return instance; }
    uint32 GetDifficulty() const { return difficulty; }
    bool IsRegularDifficulty() const { return regular; }
    bool IsRaid() const { return raid; }
};
struct Creature
{
    Map* map;
    uint32 entry = 18473;
    bool alive = true, creature = true;
    Creature* ToCreature() { return creature ? this : nullptr; }
    Map* GetMap() const { return map; }
    uint32 GetEntry() const { return entry; }
    bool IsAlive() const { return alive; }
};
struct KillRewarder
{
    Creature* victim;
    Creature* GetVictim() const { return victim; }
};
struct Session { bool bot = false; bool IsBot() const { return bot; } };
class Player
{
public:
    State state;
    Session session;
    Map* map = nullptr;
    bool bound = true, connected = true, aiBot = false, alive = true, corpse = false, near = true;
    unsigned team = TEAM_ALLIANCE, classMask = 1, raceMask = 1;
    std::set<uint32> rewarded;
    Player() { state.bindingId = 7; state.characterGuid = 42; }
    Session const* GetSession() const { return connected ? &session : nullptr; }
    unsigned GetTeamId() const { return team; }
    unsigned getClassMask() const { return classMask; }
    unsigned getRaceMask() const { return raceMask; }
    Map* GetMap() const { return map; }
    bool IsAlive() const { return alive; }
    bool GetCorpse() const { return corpse; }
    bool IsAtGroupRewardDistance(Creature*) const { return near; }
    bool GetQuestRewardStatus(uint32 id) const { return rewarded.count(id); }
};
#define WOWPILAGO_PLAYERBOTS 1
struct BotManager { bool GetPlayerbotAI(Player* player) const { return player->aiBot; } } sPlayerbotsMgr;
namespace WoWPilago
{
State* GetState(Player const* player)
{
    return player && player->bound ? &const_cast<Player*>(player)->state : nullptr;
}
''' + extract("bool Human(") + "\n" + extract("bool IsBoundHuman(") + r'''
}
struct Quest { uint32 id; uint32 GetQuestId() const { return id; } };
struct Save { uint64 epoch = 1000; uint64 GetResetTime() const { return epoch; } };
struct SaveManager
{
    Save save;
    bool present = true;
    Save* GetInstanceSave(uint32) { return present ? &save : nullptr; }
} saves;
auto sInstanceSaveMgr = &saves;
using CheckKey = std::pair<uint64, int64>;
using BossKey = std::tuple<uint64, uint32, uint32, uint32, uint64>;
struct Transaction
{
    std::set<CheckKey> checks;
    std::set<BossKey> bosses;
    void Append(char const*, uint64 binding, int64 location, uint32 guid)
    {
        assert(guid == 42 || guid == 43);
        checks.emplace(binding, location);
    }
    void Append(char const*, uint64 binding, uint32 map, uint32 boss, uint32 instance, uint64 epoch)
    {
        bosses.emplace(binding, map, boss, instance, epoch);
    }
};
using CharacterDatabaseTransaction = std::shared_ptr<Transaction>;
struct Field { uint32 value; template<class T> T Get() const { return T(value); } };
struct Result { Field field; Field* Fetch() { return &field; } };
struct Database
{
    std::set<CheckKey> checks;
    std::set<BossKey> bosses;
    bool success = true, acceptCheck = true, acceptBoss = true;
    bool missingCheck = false, missingBoss = false;
    int checkCount = -1, bossCount = -1;
    unsigned begins = 0, commits = 0, checkQueries = 0, bossQueries = 0;
    CharacterDatabaseTransaction BeginTransaction()
    {
        ++begins; return std::make_shared<Transaction>();
    }
    struct Completion { std::future<bool> m_future; };
    Completion AsyncCommitTransaction(CharacterDatabaseTransaction tx)
    {
        ++commits;
        if (success)
        {
            if (acceptCheck) checks.insert(tx->checks.begin(), tx->checks.end());
            if (acceptBoss) bosses.insert(tx->bosses.begin(), tx->bosses.end());
        }
        std::promise<bool> done; done.set_value(success); return {done.get_future()};
    }
    std::shared_ptr<Result> Query(char const*, uint64 binding, int64 location)
    {
        ++checkQueries;
        if (missingCheck) return nullptr;
        return std::make_shared<Result>(Result{{checkCount < 0 ?
            uint32(checks.count({binding, location})) : uint32(checkCount)}});
    }
    std::shared_ptr<Result> Query(char const*, uint64 binding, uint32 map, uint32 boss,
        uint32 instance, uint64 epoch)
    {
        ++bossQueries;
        if (missingBoss) return nullptr;
        return std::make_shared<Result>(Result{{bossCount < 0 ?
            uint32(bosses.count({binding, map, boss, instance, epoch})) : uint32(bossCount)}});
    }
} CharacterDatabase;
''' + extract("void Commit(") + "\n" + extract("bool ProfileAllows(") + r'''
namespace WoWPilago
{
''' + extract("void RecordCheck(") + r'''
}
''' + extract("void BossCredit(") + r'''
struct PlayerScript
{
    virtual ~PlayerScript() = default;
    virtual void OnPlayerCompleteQuest(Player*, Quest const*) = 0;
};
struct QuestHook : PlayerScript
{
''' + extract("void OnPlayerCompleteQuest(") + r'''
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
void kill(Player& player, Creature& victim, uint32 entry)
{
    victim.entry = entry;
    KillRewarder rewarder{&victim}; BossCredit(&player, &rewarder);
}
int main()
{
''' + assertions + "\n}\n"
        with tempfile.TemporaryDirectory(prefix="wowpilago-check-credit-") as directory:
            path = pathlib.Path(directory)
            (path / "check.cpp").write_text(source)
            subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=undefined", "-fno-sanitize-recover=all",
                            "-I", str(ROOT / "src"), str(path / "check.cpp"),
                            "-o", str(path / "check")], check=True)
            subprocess.run([str(path / "check")], check=True)

    def test_quest_turn_in_and_record_check_durability(self):
        self.run_credit(r'''
    Player player; Quest quest{317}; QuestHook hook;
    player.state.enabledChecks = {919500317};
    // The callback can run for completed objectives before reward status is set.
    hook.OnPlayerCompleteQuest(&player, &quest);
    hook.OnPlayerCompleteQuest(&player, nullptr);
    assert(CharacterDatabase.begins == 0 && player.state.completedChecks.empty());
    player.rewarded.insert(317);
    Quest unknown{999999}; hook.OnPlayerCompleteQuest(&player, &unknown);
    RecordCheck(&player, 999999);
    assert(CharacterDatabase.begins == 0);
    for (unsigned gate = 0; gate < 6; ++gate)
    {
        Player denied = player;
        if (gate == 0) denied.bound = false;
        if (gate == 1) denied.session.bot = true;
        if (gate == 2) denied.aiBot = true;
        if (gate == 3) denied.connected = false;
        if (gate == 4) denied.team = 1;
        if (gate == 5) denied.state.enabledChecks.clear();
        hook.OnPlayerCompleteQuest(&denied, &quest);
        RecordCheck(&denied, 919500317);
        assert(denied.state.completedChecks.empty() && CharacterDatabase.begins == 0);
    }
    RecordCheck(nullptr, 919500317);
    hook.OnPlayerCompleteQuest(nullptr, &quest);
    // Use a real race-restricted quest, including its successful profile.
    Player draenei; draenei.rewarded = {9279}; draenei.state.enabledChecks = {919509279};
    Quest raceQuest{9279}; hook.OnPlayerCompleteQuest(&draenei, &raceQuest);
    assert(CharacterDatabase.begins == 0);
    draenei.raceMask = 1024; hook.OnPlayerCompleteQuest(&draenei, &raceQuest);
    assert((draenei.state.completedChecks == std::set<int64>{919509279}));
    // The catalog currently has no class-restricted check; exercise the real helper.
    CheckDef restricted = *FindById(Checks, 919500317); restricted.classMask = 2;
    assert(!ProfileAllows(&player, restricted));
    player.classMask = 2; assert(ProfileAllows(&player, restricted));
    CharacterDatabase = Database();
    hook.OnPlayerCompleteQuest(&player, &quest);
    assert((player.state.completedChecks == std::set<int64>{919500317}));
    assert((CharacterDatabase.checks == std::set<CheckKey>{{7, 919500317}}));
    hook.OnPlayerCompleteQuest(&player, &quest);
    assert(CharacterDatabase.commits == 1 && CharacterDatabase.checkQueries == 1);
    // Lost live cache after a committed insert retries INSERT IGNORE and confirms it.
    player.state.completedChecks.clear(); hook.OnPlayerCompleteQuest(&player, &quest);
    assert(CharacterDatabase.checks.size() == 1 && CharacterDatabase.commits == 2);
    assert(player.state.completedChecks.count(919500317) == 1);
    Player other = player; other.state.bindingId = 8; other.state.characterGuid = 43;
    other.state.completedChecks.clear(); hook.OnPlayerCompleteQuest(&other, &quest);
    assert((CharacterDatabase.checks == std::set<CheckKey>{{7, 919500317}, {8, 919500317}}));
    for (unsigned failure = 0; failure < 5; ++failure)
    {
        CharacterDatabase = Database(); player.state.completedChecks.clear();
        if (failure == 0) CharacterDatabase.success = false;
        if (failure == 1) CharacterDatabase.missingCheck = true;
        if (failure == 2) CharacterDatabase.acceptCheck = false;
        if (failure == 3) CharacterDatabase.checkCount = 0;
        if (failure == 4) CharacterDatabase.checkCount = 2;
        mustStop([&] { hook.OnPlayerCompleteQuest(&player, &quest); },
            failure == 0 ? "transaction failed" : "check outbox insert was not durable");
        assert(player.state.completedChecks.empty());
        assert(CharacterDatabase.commits == 1);
        assert(CharacterDatabase.checkQueries == (failure == 0 ? 0u : 1u));
        CharacterDatabase.success = true; CharacterDatabase.missingCheck = false;
        CharacterDatabase.acceptCheck = true; CharacterDatabase.checkCount = -1;
        hook.OnPlayerCompleteQuest(&player, &quest);
        assert((player.state.completedChecks == std::set<int64>{919500317}));
        assert((CharacterDatabase.checks == std::set<CheckKey>{{7, 919500317}}));
    }
''')

    def test_boss_and_dungeon_credit(self):
        self.run_credit(r'''
    Map map; Creature victim{&map}; Player player; player.map = &map;
    player.state.enabledChecks = {919818473, 919818472, 919900556};
    KillRewarder rewarder{&victim}, absent{nullptr};
    BossCredit(nullptr, &rewarder); BossCredit(&player, nullptr); BossCredit(&player, &absent);
    assert(CharacterDatabase.begins == 0);
    for (unsigned gate = 0; gate < 10; ++gate)
    {
        Player denied = player; Creature target = victim; Map elsewhere = map;
        if (gate == 0) denied.bound = false;
        if (gate == 1) denied.session.bot = true;
        if (gate == 2) denied.aiBot = true;
        if (gate == 3) denied.connected = false;
        if (gate == 4) target.creature = false;
        if (gate == 5) denied.map = &elsewhere; // Same map ID, different map object.
        if (gate == 6) denied.near = false;
        if (gate == 7) { denied.alive = false; denied.corpse = true; }
        if (gate == 8) { elsewhere.regular = false; target.map = denied.map = &elsewhere; }
        if (gate == 9) { elsewhere.id = 558; target.map = denied.map = &elsewhere; }
        kill(denied, target, 18473);
        assert(denied.state.completedChecks.empty() && CharacterDatabase.begins == 0);
    }
    // KillRewarder confirms the kill even before the victim's death state changes.
    assert(victim.IsAlive()); kill(player, victim, 18473);
    assert((player.state.completedChecks == std::set<int64>{919818473}));
    assert((CharacterDatabase.bosses == std::set<BossKey>{{7, 556, 18473, 17, 1000}}));
    kill(player, victim, 18473);
    assert(CharacterDatabase.checks.size() == 1 && CharacterDatabase.bosses.size() == 1);
    // Another instance/reset still cannot award the individual boss twice per binding.
    map.instance = 18; saves.save.epoch = 2000; kill(player, victim, 18473);
    assert(CharacterDatabase.checks.size() == 1);
    Player bossSlot = player; bossSlot.state.bindingId = 8; bossSlot.state.characterGuid = 43;
    bossSlot.state.completedChecks.clear(); bossSlot.state.enabledChecks = {919818473};
    kill(bossSlot, victim, 18473); kill(bossSlot, victim, 18473);
    assert((bossSlot.state.completedChecks == std::set<int64>{919818473}));
    assert((CharacterDatabase.checks == std::set<CheckKey>{{7, 919818473}, {8, 919818473}}));
    // Dead without a corpse remains eligible under core's reward rules.
    player.alive = false; kill(player, victim, 18472);
    assert((player.state.completedChecks == std::set<int64>{919818473, 919818472, 919900556}));
    unsigned commits = CharacterDatabase.commits;
    kill(player, victim, 18472); assert(CharacterDatabase.commits == commits);
    // Isolate all component identity fields, with three unrelated stored components.
    CharacterDatabase = Database(); player = Player(); player.map = &map;
    player.state.enabledChecks = {919900556}; map.instance = 17; saves.save.epoch = 1000;
    CharacterDatabase.bosses = {{7, 558, 18473, 17, 1000}, {7, 556, 18473, 18, 1000},
        {7, 556, 18473, 17, 999}, {8, 556, 18473, 17, 1000}};
    kill(player, victim, 18472);
    assert(player.state.completedChecks.empty() && CharacterDatabase.bosses.size() == 5);
    kill(player, victim, 999999);
    assert(CharacterDatabase.commits == 1); // Arbitrary creatures do not add components.
    kill(player, victim, 18473);
    assert((player.state.completedChecks == std::set<int64>{919900556}));
    assert((CharacterDatabase.checks == std::set<CheckKey>{{7, 919900556}}));
    Player other = player; other.state.bindingId = 9; other.state.characterGuid = 43;
    other.state.completedChecks.clear(); kill(other, victim, 18472);
    assert(other.state.completedChecks.empty());
    kill(other, victim, 18473);
    assert((CharacterDatabase.checks == std::set<CheckKey>{{7, 919900556}, {9, 919900556}}));
    // No save, zero instance, or zero reset cannot generate dungeon components.
    for (unsigned gate = 0; gate < 3; ++gate)
    {
        CharacterDatabase = Database(); player.state.completedChecks.clear();
        saves.present = gate != 0; map.instance = gate == 1 ? 0 : 17;
        saves.save.epoch = gate == 2 ? 0 : 1000;
        kill(player, victim, 18473);
        assert(CharacterDatabase.begins == 0 && player.state.completedChecks.empty());
    }
    saves = SaveManager(); map.instance = 17;
    // Boss and dungeon categories are independently enabled, including both off.
    for (unsigned category = 0; category < 3; ++category)
    {
        CharacterDatabase = Database(); player.state.completedChecks.clear();
        player.state.enabledChecks = category == 0 ? std::set<int64>{919818473} :
            category == 1 ? std::set<int64>{919900556} : std::set<int64>{};
        kill(player, victim, 18473); kill(player, victim, 18472);
        if (category == 0)
        {
            assert((player.state.completedChecks == std::set<int64>{919818473}));
            assert(CharacterDatabase.bosses.empty());
        }
        if (category == 1)
            assert((player.state.completedChecks == std::set<int64>{919900556}));
        if (category == 2) assert(CharacterDatabase.begins == 0);
    }
    for (unsigned failure = 0; failure < 4; ++failure)
    {
        CharacterDatabase = Database(); player.state.completedChecks.clear();
        player.state.enabledChecks = {919900556};
        if (failure == 0) CharacterDatabase.success = false;
        if (failure == 1) CharacterDatabase.missingBoss = true;
        if (failure == 2) CharacterDatabase.acceptBoss = false;
        if (failure == 3) CharacterDatabase.bossCount = 2;
        mustStop([&] { kill(player, victim, 18473); }, failure == 0 ? "transaction failed" :
            failure == 1 ? "durability query failed" : "current boss credit insert was not durable");
        assert(player.state.completedChecks.empty() && CharacterDatabase.checks.empty());
        assert(CharacterDatabase.bossQueries == (failure == 0 ? 0u : 1u));
        CharacterDatabase.success = true; CharacterDatabase.missingBoss = false;
        CharacterDatabase.acceptBoss = true; CharacterDatabase.bossCount = -1;
        kill(player, victim, 18473); kill(player, victim, 18472);
        assert((player.state.completedChecks == std::set<int64>{919900556}));
        assert(CharacterDatabase.bosses.size() == 2 && CharacterDatabase.checks.size() == 1);
    }
    // A clear's final RecordCheck must also wait for durable outbox confirmation.
    CharacterDatabase = Database(); player.state.completedChecks.clear();
    kill(player, victim, 18473); CharacterDatabase.missingCheck = true;
    mustStop([&] { kill(player, victim, 18472); }, "check outbox insert was not durable");
    assert(player.state.completedChecks.empty() && CharacterDatabase.bosses.size() == 2);
    CharacterDatabase.missingCheck = false; kill(player, victim, 18472);
    assert((player.state.completedChecks == std::set<int64>{919900556}));
    // Normal 10/25 raids accepted; both heroic raid modes and heroic dungeons denied.
    for (unsigned difficulty : {0u, 1u, 2u, 3u})
    {
        CharacterDatabase = Database(); player.state.completedChecks.clear();
        player.state.enabledChecks = {920012118}; map.id = 409; map.raid = true;
        map.difficulty = difficulty; map.regular = difficulty == 0;
        kill(player, victim, 12118);
        if (difficulty < 2)
            assert((player.state.completedChecks == std::set<int64>{920012118}));
        else assert(CharacterDatabase.begins == 0 && player.state.completedChecks.empty());
    }
''')


if __name__ == "__main__":
    unittest.main()
