"""Patch application and executable checks of functions extracted from patched core.

CORE_PATCH_SOURCE may point to another local clone containing the pinned commit.
No writes are made to that clone. All patching happens under TemporaryDirectory.
"""

import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("apply_core_patch", PROJECT / "tools/apply_core_patch.py")
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)
SOURCE = Path(os.environ.get("CORE_PATCH_SOURCE", PROJECT.parent / "wow-test/azerothcore"))


def function(text, signature):
    start = text.index(signature)
    brace = text.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


class CorePatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_dir():
            raise unittest.SkipTest("set CORE_PATCH_SOURCE to a local pinned core clone")
        cls.temp = tempfile.TemporaryDirectory(prefix="wowpilago-patch-test-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.archive = cls.root / "archive"
        cls.archive.mkdir()
        archive = subprocess.run(
            ["git", "-C", str(SOURCE), "archive", patcher.COMMIT],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        )
        subprocess.run(["tar", "-x", "-C", str(cls.archive)], input=archive.stdout, check=True)

    def setUp(self):
        self.work = self.root / self._testMethodName
        self.work.mkdir()
        for name in patcher.FINGERPRINTS:
            target = self.work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.archive / name, target)

    def snapshot(self):
        return {name: hashlib.sha256((self.work / name).read_bytes()).hexdigest()
                for name in patcher.FINGERPRINTS}

    def test_archive_apply_and_reapply(self):
        self.assertFalse((self.work / ".git").exists())
        self.assertEqual(patcher.apply(self.work), "applied")
        before = self.snapshot()
        self.assertEqual(patcher.apply(self.work), "already applied")
        self.assertEqual(before, self.snapshot())
        self.assertEqual(before, {p: h["patched"] for p, h in patcher.FINGERPRINTS.items()})
        subprocess.run(["git", "-C", str(self.work), "apply", "--reverse", str(patcher.PATCH)], check=True)
        self.assertEqual(self.snapshot(), {p: h["original"] for p, h in patcher.FINGERPRINTS.items()})

    def test_modified_source_fails_without_writes(self):
        path = self.work / next(iter(patcher.FINGERPRINTS))
        path.write_text(path.read_text() + "\n// unrelated local change\n")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "modified core source"):
            patcher.apply(self.work)
        self.assertEqual(before, self.snapshot())

    def test_modified_applied_source_is_not_already_applied(self):
        patcher.apply(self.work)
        path = self.work / next(iter(patcher.FINGERPRINTS))
        path.write_text(path.read_text() + "\n// unrelated local change\n")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "modified core source"):
            patcher.apply(self.work)
        self.assertEqual(before, self.snapshot())

    def test_wrong_git_commit_fails_even_with_matching_sources(self):
        # A synthetic unrelated commit ID, with no commit creation or host changes.
        subprocess.run(["git", "init", "-q", str(self.work)], check=True)
        (self.work / ".git/HEAD").write_text("0" * 40 + "\n")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "wrong core commit"):
            patcher.apply(self.work)
        self.assertEqual(before, self.snapshot())

    def compile_and_run(self, source):
        if not shutil.which("c++"):
            self.skipTest("c++ compiler required for extracted-core behavior tests")
        program = self.work / "behavior.cpp"
        program.write_text(source)
        binary = self.work / "behavior"
        subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                        str(program), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)

    def test_actual_transaction_engine(self):
        patcher.apply(self.work)
        database = self.work / "src/server/database/Database"
        connection = (database / "MySQLConnection.cpp").read_text()
        header = (database / "MySQLConnection.h").read_text()
        member = next(line for line in header.splitlines() if "bool m_inTransaction" in line)
        methods = "\n".join(function(connection, signature) for signature in (
            "bool MySQLConnection::Execute(std::string_view",
            "bool MySQLConnection::Execute(PreparedStatementBase*",
            "void MySQLConnection::BeginTransaction(",
            "void MySQLConnection::RollbackTransaction(",
            "void MySQLConnection::CommitTransaction(",
            "int MySQLConnection::ExecuteTransaction(",
            "uint32 MySQLConnection::GetLastError(",
            "void MySQLConnection::Ping(",
            "std::size_t MySQLConnection::EscapeString(",
            "bool MySQLConnection::_HandleMySQLErrno(",
        ))
        transaction = (database / "Transaction.cpp").read_text()
        methods += "\n" + function(transaction, "bool TransactionTask::Execute(")
        methods += "\n" + function(transaction, "bool TransactionWithResultTask::Execute(")
        pool = (database / "DatabaseWorkerPool.cpp").read_text()
        methods += "\ntemplate<class T>\n" + function(pool, "void DatabaseWorkerPool<T>::DirectCommitTransaction(")
        self.compile_and_run(TRANSACTION_STUBS.replace("// transaction member", member) +
                             methods + TRANSACTION_CHECKS)

    def test_actual_hook_dispatch_and_registration(self):
        patcher.apply(self.work)
        scripting = self.archive / "src/server/game/Scripting"
        macros = (scripting / "ScriptMgrMacros.h").read_text()
        macros = macros[macros.index("#define CALL_ENABLED_HOOKS"):macros.index("#endif")]
        defines = self.work / "src/server/game/Scripting/ScriptDefines"
        header = (defines / "PlayerScript.h").read_text()
        source = (defines / "PlayerScript.cpp").read_text()
        names = ("OnPlayerBeforeApplyXP", "OnPlayerCanAddSpell", "OnPlayerCanTrainSpell",
                 "OnPlayerCanAccessMap", "OnPlayerCheckItemLevel", "OnPlayerSaveToDB")
        virtuals = []
        dispatch = []
        for name in names:
            ret = "bool" if name.startswith("OnPlayerCan") else "void"
            virtuals.append(function(header, f"virtual {ret} {name}("))
            dispatch.append(function(source, f"{ret} ScriptMgr::{name}("))
        declarations = "\n".join(method.split("{", 1)[0].replace("ScriptMgr::", "") + ";"
                                 for method in dispatch)
        program = DISPATCH_STUBS + function(header, "enum PlayerHook") + ";\n"
        program += "struct PlayerScript : ScriptObject {\nusing ScriptObject::ScriptObject;\n"
        program += "PlayerScript(char const*, std::vector<uint16> = {});\n" + "\n".join(virtuals) + "\n};\n"
        program += "struct ScriptMgr {\n" + declarations + "\n};\n" + macros
        program += function(source, "PlayerScript::PlayerScript(") + "\n" + "\n".join(dispatch)
        self.compile_and_run(program + DISPATCH_CHECKS)

    def test_actual_login_fallback(self):
        patcher.apply(self.work)
        storage = (self.work / "src/server/game/Entities/Player/PlayerStorage.cpp").read_text()
        check = function(storage, "auto CheckLoginMapAccess =")
        self.compile_and_run(LOGIN_STUBS + "\nbool Player::check() {\n" + check +
                             "; return CheckLoginMapAccess(); }\n" + LOGIN_CHECKS)

    def test_actual_trainer_state(self):
        patcher.apply(self.work)
        trainer = (self.work / "src/server/game/Entities/Creature/Trainer.cpp").read_text()
        state = function(trainer, "SpellState Trainer::GetSpellState(")
        teach = function(trainer, "bool Trainer::CanTeachSpell(")
        self.compile_and_run(TRAINER_STUBS + "\nnamespace Trainer {\n" + state + "\n" + teach +
                             "\n}\n" + TRAINER_CHECKS)

    def test_actual_xp_and_item_validators(self):
        if not shutil.which("c++"):
            self.skipTest("c++ compiler required for extracted-core behavior tests")
        patcher.apply(self.work)
        player = (self.work / "src/server/game/Entities/Player/Player.cpp").read_text()
        storage = (self.work / "src/server/game/Entities/Player/PlayerStorage.cpp").read_text()
        methods = function(player, "void Player::GiveXP(")
        methods += "\n" + function(storage, "InventoryResult Player::CanUseItem(ItemTemplate const* proto) const")
        methods += "\n" + function(storage, "InventoryResult Player::CanUseItem(ItemTemplate const* proto, Item const* instance) const")
        self.compile_and_run(CPP_STUBS + methods + CPP_CHECKS)


CPP_STUBS = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <vector>
using uint8 = uint8_t; using uint32 = uint32_t; using uint64 = uint64_t;
enum { AREA_HELLFIRE_PENINSULA, AREA_HELLFIRE_RAMPARTS, AREA_MAGTHERIDONS_LAIR,
       AREA_THE_BLOOD_FURNACE, AREA_THE_SHATTERED_HALLS, PLAYER_XP, PLAYER_NEXT_LEVEL_XP,
       PLAYER_FLAGS_NO_XP_GAIN, PLAYER_FLAGS_NO_PLAY_TIME, PLAYER_FLAGS_PARTIAL_PLAY_TIME,
       CONFIG_MAX_PLAYER_LEVEL, CONFIG_TRIAL_LEVEL_CAP, ITEM_FLAG2_FACTION_HORDE,
       ITEM_FLAG2_FACTION_ALLIANCE, TEAM_HORDE, TEAM_ALLIANCE };
enum InventoryResult { EQUIP_ERR_OK, EQUIP_ERR_ITEM_NOT_FOUND, EQUIP_ERR_YOU_CAN_NEVER_USE_THAT_ITEM,
    EQUIP_ERR_NO_REQUIRED_PROFICIENCY, EQUIP_ERR_CANT_EQUIP_SKILL, EQUIP_ERR_CANT_EQUIP_LEVEL_I,
    EQUIP_ERR_CANT_DO_RIGHT_NOW };
using HolidayIds = uint32;
bool holidayActive = true;
bool IsHolidayActive(HolidayIds) { return holidayActive; }
struct Item {};
struct ItemTemplate {
    uint32 AllowableClass = 1, AllowableRace = 1, RequiredSkill = 0, RequiredSkillRank = 0;
    uint32 RequiredSpell = 0, RequiredLevel = 1, HolidayId = 0;
    bool HasFlag2(int) const { return false; }
};
struct Unit {
    bool IsCreature() { return true; } Unit* ToCreature() { return this; }
    bool hasLootRecipient() { return true; }
};
struct Session { bool trial = false; bool IsTrialAccount() { return trial; } };
struct World {
    uint32 max = 80, trial = 0;
    uint32 getIntConfig(int key) { return key == CONFIG_MAX_PLAYER_LEVEL ? max : trial; }
} world, *sWorld = &world;
struct Player {
    uint8 level = 1; uint32 xp = 0, threshold = 100, rest = 0, logged = 0;
    bool raf = false, favored = false, partial = false, veto = false;
    uint32 skill = 0; Session session;
    bool IsAlive() { return true; } uint32 GetBattlegroundId() { return 0; }
    bool HasPlayerFlag(int flag) { return flag == PLAYER_FLAGS_PARTIAL_PLAY_TIME && partial; }
    uint8 GetLevel() const { return level; } uint32 GetZoneId() { return AREA_HELLFIRE_PENINSULA; }
    bool HasAnyAuras(int, int) { return favored; } Session* GetSession() { return &session; }
    bool GetsRecruitAFriendBonus(bool) { return raf; }
    uint32 GetXPRestBonus(uint32 value) { auto used = std::min(rest, value); rest -= used; return used; }
    void SendLogXPGain(uint32 base, Unit*, uint32 bonus, bool, float) { logged = base + bonus; }
    uint32 GetUInt32Value(int field) { return field == PLAYER_XP ? xp : threshold; }
    void SetUInt32Value(int, uint32 value) { xp = value; }
    void GiveLevel(uint8 value) { if (!veto) level = value; }
    uint32 GetTeamId(bool) const { return TEAM_ALLIANCE; }
    uint32 getClassMask() const { return 1; } uint32 getRaceMask() const { return 1; }
    uint32 GetSkillValue(uint32) const { return skill; } bool HasSpell(uint32) const { return false; }
    void GiveXP(uint32, Unit*, float = 1, bool = false);
    InventoryResult CanUseItem(ItemTemplate const*) const;
    InventoryResult CanUseItem(ItemTemplate const*, Item const*) const;
};
struct Scripts {
    uint32 cap = 80; uint64 bank = 0, seen = 0; int calls = 0, itemCalls = 0;
    bool normalize = false, ignoreLevel = false, allowItem = true;
    void OnPlayerBeforeGetLevelForXPGain(Player*, uint8&) {}
    void OnPlayerBeforeApplyXP(Player* p, uint64& finalXP, uint32& maxLevel) {
        ++calls; seen = finalXP; maxLevel = std::min(cap, maxLevel);
        if (p->level >= maxLevel) { bank += finalXP; finalXP = 0; }
        else if (normalize) {
            uint64 room = uint64(maxLevel - p->level) * p->threshold - p->xp;
            bank += finalXP - std::min(finalXP, room); finalXP = std::min(finalXP, room);
        }
    }
    void OnPlayerCheckItemLevel(Player const*, Item const*, bool& ignore) { ++itemCalls; ignore = ignoreLevel; }
    bool OnPlayerCanUseItem(Player*, ItemTemplate const*, InventoryResult& result) {
        result = EQUIP_ERR_CANT_DO_RIGHT_NOW; return allowItem;
    }
} scripts, *sScriptMgr = &scripts;
'''

CPP_CHECKS = r'''
void reset() { scripts = Scripts{}; world = World{}; holidayActive = true; }
int main() {
    Unit victim;
    reset(); { Player p; p.GiveXP(250, nullptr); assert(p.level == 3 && p.xp == 50 && p.logged == 250); }
    reset(); { Player p; p.level = 9; p.xp = 75; scripts.cap = 10; scripts.normalize = true;
        p.GiveXP(1000, nullptr); assert(p.level == 10 && p.xp == 0 && scripts.bank == 975 && p.logged == 25);
        p.GiveXP(20, nullptr); assert(p.level == 10 && p.xp == 0 && scripts.bank == 995); }
    reset(); { Player p; p.level = 9; p.xp = 75; scripts.cap = 10;
        p.GiveXP(1000, nullptr); assert(p.level == 10 && p.xp == 0 && scripts.bank == 975 && scripts.calls == 2 && p.logged == 25); }
    reset(); { Player p; scripts.cap = 2; p.GiveXP(100, nullptr);
        assert(p.level == 2 && p.xp == 0 && scripts.bank == 0 && scripts.calls == 1); }
    reset(); { Player p; p.veto = true; p.xp = 30; p.GiveXP(250, nullptr);
        assert(p.level == 1 && p.xp == 280); }
    reset(); { Player p; p.raf = true; scripts.cap = 1; p.GiveXP(UINT32_MAX, &victim);
        assert(scripts.seen == uint64(UINT32_MAX) * 3 && scripts.bank == scripts.seen && p.xp == 0); }
    reset(); { Player p; p.favored = true; p.rest = 1000; scripts.cap = 1;
        p.GiveXP(100, &victim); assert(scripts.seen == 210 && p.rest == 895); }
    reset(); { Player p; p.partial = true; scripts.cap = 1; p.GiveXP(101, nullptr); assert(scripts.seen == 50); }
    reset(); { Player p; world.trial = 2; p.session.trial = true; p.GiveXP(10000, nullptr);
        assert(p.level == 2 && p.xp == 0); }
    reset(); { Player p; p.level = 79; p.GiveXP(UINT32_MAX, nullptr); assert(p.level == 80 && p.xp == 0); }
    reset(); { Player p; Item item; ItemTemplate proto; proto.RequiredLevel = 80;
        scripts.ignoreLevel = true;
        assert(p.CanUseItem(&proto) == EQUIP_ERR_CANT_EQUIP_LEVEL_I && scripts.itemCalls == 0);
        assert(p.CanUseItem(&proto, &item) == EQUIP_ERR_OK && scripts.itemCalls == 1);
        scripts.ignoreLevel = false;
        assert(p.CanUseItem(&proto, &item) == EQUIP_ERR_CANT_EQUIP_LEVEL_I);
        scripts.ignoreLevel = true; proto.AllowableClass = 2;
        assert(p.CanUseItem(&proto, &item) == EQUIP_ERR_YOU_CAN_NEVER_USE_THAT_ITEM);
        proto.AllowableClass = 1; proto.RequiredSkill = 1;
        assert(p.CanUseItem(&proto, &item) == EQUIP_ERR_NO_REQUIRED_PROFICIENCY);
        p.skill = 1; proto.RequiredSkillRank = 2;
        assert(p.CanUseItem(&proto, &item) == EQUIP_ERR_CANT_EQUIP_SKILL);
        p.skill = 2; proto.RequiredSpell = 1;
        assert(p.CanUseItem(&proto, &item) == EQUIP_ERR_NO_REQUIRED_PROFICIENCY);
        proto.RequiredSpell = 0; proto.HolidayId = 1; holidayActive = false;
        assert(p.CanUseItem(&proto, &item) == EQUIP_ERR_CANT_DO_RIGHT_NOW);
        holidayActive = true; scripts.allowItem = false;
        assert(p.CanUseItem(&proto, &item) == EQUIP_ERR_CANT_DO_RIGHT_NOW);
    }
}
'''


DISPATCH_STUBS = r'''
#include <cassert>
#include <cstdint>
#include <utility>
#include <vector>
using uint8 = uint8_t; using uint16 = uint16_t; using uint32 = uint32_t; using uint64 = uint64_t;
using CharacterDatabaseTransaction = int;
struct Player {}; struct Item {}; struct WorldLocation {};
struct ScriptObject { ScriptObject(char const*, int) {} };
template<class T> struct ScriptRegistry {
    static inline std::vector<T*> EnabledHooks[1024];
    static void AddScript(T* script, std::vector<uint16> hooks) {
        for (auto hook : hooks) EnabledHooks[hook].push_back(script);
    }
    static void clear() { for (auto& hooks : EnabledHooks) hooks.clear(); }
};
'''
DISPATCH_CHECKS = r'''
struct Deny : PlayerScript {
    Deny(std::vector<uint16> flags = {}) : PlayerScript("deny", flags) {}
    bool OnPlayerCanAddSpell(Player*, uint32 id, uint8 mask, bool temporary, bool skill) override {
        assert(id == 123 && mask == 3 && temporary && skill); return false;
    }
    bool OnPlayerCanTrainSpell(Player const*, uint32) override { return false; }
    bool OnPlayerCanAccessMap(Player const*, uint32, WorldLocation const*, bool) override { return false; }
    void OnPlayerBeforeApplyXP(Player*, uint64& xp, uint32& cap) override { xp = 5; cap = 10; }
    void OnPlayerCheckItemLevel(Player const*, Item const*, bool& ignore) override { ignore = true; }
    void OnPlayerSaveToDB(Player*, CharacterDatabaseTransaction trans, bool create, bool logout) override {
        assert(trans == 42 && create && logout); ++saves;
    }
    int saves = 0;
};
int main() {
    ScriptMgr mgr; Player player; Item item; WorldLocation dest;
    uint64 xp = 20; uint32 cap = 80; bool ignore = false;
    PlayerScript vanilla("vanilla");
    assert(mgr.OnPlayerCanAddSpell(&player, 123, 3, true, true));
    assert(mgr.OnPlayerCanTrainSpell(&player, 123));
    assert(mgr.OnPlayerCanAccessMap(&player, 530, &dest, true));
    mgr.OnPlayerBeforeApplyXP(&player, xp, cap); mgr.OnPlayerCheckItemLevel(&player, &item, ignore);
    assert(xp == 20 && cap == 80 && !ignore);
    Deny deny;
    assert(!mgr.OnPlayerCanAddSpell(&player, 123, 3, true, true));
    assert(!mgr.OnPlayerCanTrainSpell(&player, 123));
    assert(!mgr.OnPlayerCanAccessMap(&player, 530, &dest, true));
    mgr.OnPlayerBeforeApplyXP(&player, xp, cap); mgr.OnPlayerCheckItemLevel(&player, &item, ignore);
    mgr.OnPlayerSaveToDB(&player, 42, true, true);
    assert(xp == 5 && cap == 10 && ignore && deny.saves == 1);
    ScriptRegistry<PlayerScript>::clear();
    Deny selective({PLAYERHOOK_CAN_ACCESS_MAP});
    assert(!mgr.OnPlayerCanAccessMap(&player, 530, nullptr, false));
    assert(mgr.OnPlayerCanTrainSpell(&player, 123));
    assert(mgr.OnPlayerCanAddSpell(&player, 123, 3, true, true));
}
'''

LOGIN_STUBS = r'''
#include <cassert>
#include <cstdint>
#include <string>
using uint32 = uint32_t;
enum { MOVEMENTFLAG_ONTRANSPORT = 1 };
struct WorldLocation {
    uint32 mapId; float x, y, z, o;
    WorldLocation(uint32 m, float a, float b, float c, float d) : mapId(m), x(a), y(b), z(c), o(d) {}
};
struct Map { uint32 id = 571; uint32 GetId() { return id; } } savedMap;
struct PlayerInfo { uint32 mapId = 0; float positionX = 1, positionY = 2, positionZ = 3; } start;
struct ObjectMgr { PlayerInfo const* GetPlayerInfo(int, int) { return &start; } } objects, *sObjectMgr = &objects;
struct MapMgr { static bool IsValidMapCoord(uint32, float, float, float, float) { return true; } };
struct Player;
struct Transport { int removed = 0; void RemovePassenger(Player*) { ++removed; } } transport;
struct Taxi { bool active = true; void ClearTaxiDestinations() { active = false; } };
struct Entry { bool active = true; void ClearTaxiPath() { active = false; } };
struct Movement {
    struct Data { bool active = true; void Reset() { active = false; } } transport;
    bool onTransport = true; void RemoveMovementFlag(int) { onTransport = false; }
};
struct Player {
    Map* map = &savedMap; uint32 mapId = 530, instanceId = 9;
    float x = 100, y = 200, z = 300, o = 1;
    Transport* m_transport = &transport; Movement m_movementInfo; Taxi m_taxi; Entry m_entryPointData;
    std::string taxi_nodes = "old route";
    int getRace(bool) { return 1; } int getClass() { return 1; }
    float GetPositionX() { return x; } float GetPositionY() { return y; }
    float GetPositionZ() { return z; } float GetOrientation() { return o; }
    void Relocate(float a, float b, float c, float d) { x=a; y=b; z=c; o=d; }
    bool check();
};
struct Scripts {
    bool denyStart = false, allowSaved = false; uint32 seen = 0; float seenX = 0;
    bool OnPlayerCanAccessMap(Player const*, uint32 mapId, WorldLocation const* dest, bool login) {
        assert(login && dest && dest->mapId == mapId); seen = mapId; seenX = dest->x;
        return mapId == start.mapId ? !denyStart : allowSaved;
    }
} scripts, *sScriptMgr = &scripts;
'''
LOGIN_CHECKS = r'''
int main() {
    { Player p; assert(p.check()); assert(p.map == nullptr && p.mapId == start.mapId && p.instanceId == 0);
      assert(!p.m_transport && !p.m_movementInfo.transport.active && !p.m_movementInfo.onTransport);
      assert(!p.m_taxi.active && !p.m_entryPointData.active && p.taxi_nodes.empty());
      assert(transport.removed == 1 && scripts.seen == start.mapId && scripts.seenX == start.positionX); }
    { Player p; scripts.denyStart = true; assert(!p.check()); assert(!p.m_transport && !p.m_taxi.active); }
    { Player p; scripts.allowSaved = true; assert(p.check());
      assert(scripts.seen == savedMap.id && scripts.seenX == 100 && p.map == &savedMap && p.instanceId == 9); }
    { Player p; p.map = nullptr; assert(p.check()); assert(scripts.seen == 530); }
}
'''

TRAINER_STUBS = r'''
#include <cassert>
#include <cstdint>
#include <utility>
#include <vector>
using uint32 = uint32_t; using int32 = int32_t;
enum { SPELL_EFFECT_LEARN_SPELL = 36 };
struct Player {
    uint32 level = 10, skill = 50; bool fit = true, known = false; uint32 professions = 1;
    bool HasSpell(uint32) const { return known; }
    bool IsSpellFitByClassAndRace(uint32) const { return fit; }
    uint32 GetBaseSkillValue(uint32) const { return skill; }
    uint32 GetLevel() const { return level; }
    uint32 GetFreePrimaryProfessionPoints() const { return professions; }
};
struct SpellEffectInfo {
    uint32 TriggerSpell = 2; bool learn = false;
    bool IsEffect(int) const { return learn; }
};
struct SpellInfo {
    std::vector<SpellEffectInfo> effects; bool profession = false;
    auto const& GetEffects() const { return effects; }
    bool IsPrimaryProfessionFirstRank() const { return profession; }
};
struct SpellMgr {
    SpellInfo info; uint32 previous = 0; std::vector<std::pair<uint32,uint32>> required;
    SpellInfo const* AssertSpellInfo(uint32) { return &info; }
    SpellInfo const* GetSpellInfo(uint32) { return &info; }
    uint32 GetPrevSpellInChain(uint32) { return previous; }
    auto const& GetSpellsRequiredForSpellBounds(uint32) { return required; }
} spells, *sSpellMgr = &spells;
struct Scripts {
    bool allow = true; int calls = 0; uint32 seen = 0;
    bool OnPlayerCanTrainSpell(Player const*, uint32 id) { ++calls; seen = id; return allow; }
} scripts, *sScriptMgr = &scripts;
namespace Trainer {
    enum class SpellState { Known, Unavailable, Available };
    struct Spell { uint32 SpellId = 123, ReqSkillLine = 1, ReqSkillRank = 50, ReqLevel = 10;
        std::vector<int32> ReqAbility; };
    struct Trainer {
        SpellState GetSpellState(Player const*, Spell const*) const;
        bool CanTeachSpell(Player const*, Spell const*) const;
    };
}
'''
TRAINER_CHECKS = r'''
int main() {
    Player p; Trainer::Trainer trainer; Trainer::Spell spell;
    assert(trainer.GetSpellState(&p, &spell) == Trainer::SpellState::Available && scripts.seen == 123);
    scripts.allow = false;
    assert(!trainer.CanTeachSpell(&p, &spell));
    scripts.allow = true; p.level = 9; scripts.calls = 0;
    assert(!trainer.CanTeachSpell(&p, &spell) && scripts.calls == 0);
    p.level = 10; p.skill = 49; assert(!trainer.CanTeachSpell(&p, &spell));
    p.skill = 50; p.fit = false; assert(!trainer.CanTeachSpell(&p, &spell));
    p.fit = true; spells.previous = 1; assert(!trainer.CanTeachSpell(&p, &spell));
    spells.previous = 0; spells.required = {{123, 5}}; assert(!trainer.CanTeachSpell(&p, &spell));
    spells.required.clear(); spells.info.effects = {{2, true}}; spells.info.profession = true;
    p.professions = 0; assert(!trainer.CanTeachSpell(&p, &spell));
    p.professions = 1; assert(trainer.CanTeachSpell(&p, &spell));
}
'''


TRANSACTION_STUBS = r'''
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <future>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <string_view>
#include <thread>
#include <variant>
#include <vector>
using namespace std::chrono_literals;
using uint8 = uint8_t; using uint32 = uint32_t;
using Milliseconds = std::chrono::milliseconds;
template<class... T> void testLog(T const&...) {}
#define LOG_INFO(...) testLog(__VA_ARGS__)
#define LOG_DEBUG(...) testLog(__VA_ARGS__)
#define LOG_WARN(...) testLog(__VA_ARGS__)
#define LOG_ERROR(...) testLog(__VA_ARGS__)
#define LOG_FATAL(...) testLog(__VA_ARGS__)
#define ASSERT(x, ...) assert(x)
#define ABORT(...) std::abort()
constexpr uint32 CR_SERVER_GONE_ERROR = 2006;
enum { CR_UNKNOWN_ERROR = 2000, CR_SERVER_LOST = 2013,
       CR_SERVER_LOST_EXTENDED = 2055, CR_CONN_HOST_ERROR = 2003, ER_LOCK_DEADLOCK = 1213,
       ER_WRONG_VALUE_COUNT = 1136, ER_DUP_ENTRY = 1062, ER_BAD_FIELD_ERROR = 1054,
       ER_NO_SUCH_TABLE = 1146, ER_PARSE_ERROR = 1064, CONNECTION_ASYNC = 1,
       SQL_ELEMENT_RAW, SQL_ELEMENT_PREPARED };
struct MYSQL { bool connected = true, transaction = false; uint32 error = 0; int pending = 0; } db;
using MySQLHandle = MYSQL;
struct MYSQL_STMT {} statement;
struct MYSQL_BIND {} binding;
struct Fault { std::string sql; uint32 error; bool committed = false; };
std::vector<Fault> faults;
std::vector<std::string> calls;
int durable = 0, opens = 0, clears = 0;
uint32 getMSTime() { return 0; }
uint32 getMSTimeDiff(uint32, uint32) { return 0; }
Milliseconds GetTimeMS() { return 0ms; }
Milliseconds GetMSTimeDiffToNow(Milliseconds) { static int tick = 0; return Milliseconds(++tick); }
constexpr Milliseconds DEADLOCK_MAX_RETRY_TIME_MS = 1min;
int mysql_query(MYSQL* handle, char const* sql) {
    assert(handle); calls.emplace_back(sql);
    if (!handle->connected) { handle->error = CR_SERVER_GONE_ERROR; return 1; }
    if (!faults.empty() && faults.front().sql == sql) {
        auto fault = faults.front(); faults.erase(faults.begin());
        handle->error = fault.error;
        if (fault.committed) { durable += handle->pending; handle->pending = 0; }
        if (fault.error == CR_SERVER_LOST || fault.error == CR_SERVER_GONE_ERROR) {
            handle->connected = false; handle->transaction = false; handle->pending = 0;
        }
        if (fault.error == ER_LOCK_DEADLOCK) { handle->transaction = false; handle->pending = 0; }
        return 1;
    }
    handle->error = 0;
    if (std::string_view(sql) == "START TRANSACTION") {
        assert(!handle->transaction); handle->transaction = true;
    } else if (std::string_view(sql) == "COMMIT") {
        durable += handle->pending; handle->pending = 0; handle->transaction = false;
    } else if (std::string_view(sql) == "ROLLBACK") {
        handle->pending = 0; handle->transaction = false;
    } else if (std::string_view(sql) != "BIND") {
        if (handle->transaction) ++handle->pending; else ++durable;
    }
    return 0;
}
uint32 mysql_errno(MYSQL* handle) { assert(handle); return handle->error; }
char const* mysql_error(MYSQL*) { return "injected SQL failure"; }
void mysql_close(MYSQL* handle) { handle->pending = 0; handle->transaction = false; handle->connected = false; }
void mysql_ping(MYSQL* handle) { assert(handle); }
std::size_t mysql_real_escape_string(MYSQL* handle, char* to, char const* from, std::size_t length) {
    assert(handle && handle->connected); std::memcpy(to, from, length); to[length] = 0; return length;
}
int mysql_stmt_bind_param(MYSQL_STMT*, MYSQL_BIND*) { return mysql_query(&db, "BIND"); }
int mysql_stmt_execute(MYSQL_STMT*) { return mysql_query(&db, "PREPARED"); }
char const* mysql_stmt_error(MYSQL_STMT*) { return "injected prepared failure"; }
struct PreparedStatementBase { uint32 GetIndex() { return 0; } } prepared;
struct MySQLPreparedStatement {
    void BindParameters(PreparedStatementBase*) {}
    MYSQL_STMT* GetSTMT() { return &statement; }
    MYSQL_BIND* GetBind() { return &binding; }
    void ClearParameters() { ++clears; }
    char const* getQueryString() { return "PREPARED"; }
} mysqlPrepared;
struct SQLElementData { int type; std::variant<std::string, PreparedStatementBase*> element; };
struct TransactionBase {
    std::vector<SQLElementData> m_queries;
    bool cleaned = false;
    void Cleanup() { cleaned = true; }
};
template<class T> using SQLTransaction = std::shared_ptr<TransactionBase>;
class MySQLConnection {
    // transaction member
public:
    MYSQL* m_Mysql = &db;
    bool m_reconnecting = false;
    int m_connectionFlags = CONNECTION_ASYNC;
    struct { std::string database, host, port_or_socket; } m_connectionInfo;
    uint32 Open() { ++opens; db = MYSQL{}; m_Mysql = &db; return 0; }
    bool PrepareStatements() { return true; }
    MySQLPreparedStatement* GetPreparedStatement(uint32) { return &mysqlPrepared; }
    void Unlock() {}
    bool Execute(std::string_view);
    bool Execute(PreparedStatementBase*);
    void BeginTransaction(); void RollbackTransaction(); void CommitTransaction();
    int ExecuteTransaction(std::shared_ptr<TransactionBase>);
    uint32 GetLastError();
    void Ping();
    std::size_t EscapeString(char*, char const*, std::size_t);
    bool _HandleMySQLErrno(uint32, char const* = "", uint8 = 5);
};
struct TransactionTask {
    MySQLConnection* m_conn;
    std::shared_ptr<TransactionBase> m_trans;
    static inline std::mutex _deadlockLock;
    int TryExecute() { return m_conn->ExecuteTransaction(m_trans); }
    void CleanupOnFailure() { m_trans->Cleanup(); }
    bool Execute();
};
struct TransactionWithResultTask : TransactionTask {
    std::promise<bool> m_result;
    bool Execute();
};
template<class T> struct DatabaseWorkerPool {
    T* conn;
    T* GetFreeConnection() { return conn; }
    void DirectCommitTransaction(SQLTransaction<T>&);
};
'''

TRANSACTION_CHECKS = r'''
auto transaction(bool usePrepared = false) {
    auto trans = std::make_shared<TransactionBase>();
    trans->m_queries.push_back({SQL_ELEMENT_RAW, std::string("FIRST")});
    if (usePrepared) trans->m_queries.push_back({SQL_ELEMENT_PREPARED, &prepared});
    else trans->m_queries.push_back({SQL_ELEMENT_RAW, std::string("SECOND")});
    trans->m_queries.push_back({SQL_ELEMENT_RAW, std::string("TAIL")});
    return trans;
}
void reset() { db = MYSQL{}; faults.clear(); calls.clear(); durable = opens = clears = 0; }
void expect(std::initializer_list<std::string> expected) { assert(calls == std::vector<std::string>(expected)); }
void failedFuture(MySQLConnection& conn, std::shared_ptr<TransactionBase> trans) {
    TransactionWithResultTask task{{&conn, trans}, {}};
    auto future = task.m_result.get_future();
    assert(!task.Execute()); assert(!future.get()); assert(trans->cleaned);
}
int main() {
    reset(); { MySQLConnection conn; assert(conn.ExecuteTransaction(transaction()) == 0);
        assert(durable == 3 && opens == 0);
        expect({"START TRANSACTION", "FIRST", "SECOND", "TAIL", "COMMIT"}); }
    reset(); { MySQLConnection conn;
        faults = {{"START TRANSACTION", ER_DUP_ENTRY}};
        failedFuture(conn, transaction()); assert(durable == 0 && opens == 0);
        expect({"START TRANSACTION"}); }
    reset(); { MySQLConnection conn;
        faults = {{"SECOND", CR_SERVER_LOST}};
        failedFuture(conn, transaction()); assert(durable == 0 && opens == 0);
        expect({"START TRANSACTION", "FIRST", "SECOND", "ROLLBACK"});
        calls.clear(); assert(conn.ExecuteTransaction(transaction()) == 0);
        assert(opens == 1 && durable == 3);
        expect({"START TRANSACTION", "FIRST", "SECOND", "TAIL", "COMMIT"}); }
    for (auto phase : {"BIND", "PREPARED"}) {
        reset(); MySQLConnection conn; faults = {{phase, CR_SERVER_LOST}};
        failedFuture(conn, transaction(true)); assert(durable == 0 && opens == 0 && clears == 1);
        assert(calls.back() == "ROLLBACK");
        assert(calls.size() == (std::string_view(phase) == "BIND" ? 4 : 5));
    }
    for (bool committed : {false, true}) {
        reset(); MySQLConnection conn; faults = {{"COMMIT", CR_SERVER_LOST, committed}};
        failedFuture(conn, transaction()); assert(durable == (committed ? 3 : 0) && opens == 0);
        expect({"START TRANSACTION", "FIRST", "SECOND", "TAIL", "COMMIT", "ROLLBACK"});
    }
    reset(); { MySQLConnection conn;
        faults = {{"SECOND", ER_DUP_ENTRY}, {"ROLLBACK", ER_WRONG_VALUE_COUNT}};
        assert(conn.ExecuteTransaction(transaction()) == ER_DUP_ENTRY);
        assert(durable == 0 && opens == 0);
        assert(conn.ExecuteTransaction(transaction()) == 0); assert(durable == 3 && opens == 1); }
    reset(); { MySQLConnection conn;
        faults = {{"SECOND", ER_DUP_ENTRY}, {"ROLLBACK", ER_WRONG_VALUE_COUNT}};
        assert(conn.ExecuteTransaction(transaction()) == ER_DUP_ENTRY);
        conn.Ping(); assert(opens == 0);
        char escaped[8]{}; assert(conn.EscapeString(escaped, "safe", 4) == 4);
        assert(std::string_view(escaped) == "safe" && opens == 1 && durable == 0); }
    reset(); { MySQLConnection conn; faults = {{"FIRST", CR_SERVER_LOST}};
        assert(conn.Execute("FIRST")); assert(durable == 1 && opens == 1);
        expect({"FIRST", "FIRST"}); }
    for (auto phase : {"BIND", "PREPARED"}) {
        reset(); MySQLConnection conn; faults = {{phase, CR_SERVER_LOST}};
        assert(conn.Execute(&prepared)); assert(durable == 1 && opens == 1 && clears == 1);
    }
    reset(); { MySQLConnection conn; faults = {{"START TRANSACTION", CR_SERVER_LOST}};
        assert(conn.ExecuteTransaction(transaction()) == 0); assert(durable == 3 && opens == 1);
        expect({"START TRANSACTION", "START TRANSACTION", "FIRST", "SECOND", "TAIL", "COMMIT"}); }
    reset(); { MySQLConnection conn; conn.BeginTransaction();
        faults = {{"COMMIT", CR_SERVER_LOST, true}};
        assert(conn.Execute("FIRST")); conn.CommitTransaction();
        assert(durable == 1 && opens == 0); assert(calls.back() == "ROLLBACK"); }
    // Every production retry caller must stop if a deadlock retry loses the commit acknowledgement.
    for (int caller = 0; caller < 3; ++caller) {
        reset(); MySQLConnection conn; auto trans = transaction();
        faults = {{"SECOND", ER_LOCK_DEADLOCK}, {"COMMIT", CR_SERVER_LOST, true}};
        if (caller == 0) failedFuture(conn, trans);
        else if (caller == 1) { TransactionTask task{&conn, trans}; assert(!task.Execute()); }
        else { DatabaseWorkerPool<MySQLConnection> pool{&conn}; pool.DirectCommitTransaction(trans); }
        assert(opens == 0 && durable == 3 && trans->cleaned);
        expect({"START TRANSACTION", "FIRST", "SECOND", "ROLLBACK", "START TRANSACTION",
                "FIRST", "SECOND", "TAIL", "COMMIT", "ROLLBACK"});
    }
    for (int caller = 0; caller < 3; ++caller) {
        reset(); MySQLConnection conn; auto trans = transaction();
        faults = {{"SECOND", ER_LOCK_DEADLOCK}};
        if (caller == 0) {
            TransactionWithResultTask task{{&conn, trans}, {}}; auto future = task.m_result.get_future();
            assert(task.Execute() && future.get());
        } else if (caller == 1) { TransactionTask task{&conn, trans}; assert(task.Execute()); }
        else { DatabaseWorkerPool<MySQLConnection> pool{&conn}; pool.DirectCommitTransaction(trans); }
        assert(durable == 3 && opens == 0);
    }
    reset(); { MySQLConnection conn; auto empty = std::make_shared<TransactionBase>();
        assert(conn.ExecuteTransaction(empty) == -1 && calls.empty()); }
}
'''


if __name__ == "__main__":
    unittest.main()
