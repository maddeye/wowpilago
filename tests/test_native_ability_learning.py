"""Execute extracted progression bodies against the real catalog and bounded stubs.

No core spell loader, trainer purchase, receipt transaction, SQL, or realm runs here.
Native lifecycle proof still needs the patched core, saved spell chains, real trainer
wrappers, receipt publication, level changes, and logout/login persistence.
"""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from test_native_progression import production_method

ROOT = pathlib.Path(__file__).resolve().parents[1]


class NativeAbilityLearningTests(unittest.TestCase):
    def run_methods(self, assertions):
        compiler = shutil.which("g++") or shutil.which("clang++")
        self.assertIsNotNone(compiler, "a C++17 compiler is required")
        production = (ROOT / "src/APProgression.cpp").read_text()
        extract = lambda signature: production_method(production, signature)
        source = r'''
#include "APProgression.h"
#include "APCatalog.h"
#include <cassert>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using int64 = std::int64_t;
using namespace WoWPilago;
struct Session
{
    bool loading = false;
    bool PlayerLoading() const { return loading; }
};
struct Cache { bool savePending = false; State state; };
enum class HighGuid { Item };
struct ObjectGuid { ObjectGuid(HighGuid, uint32) {} };
constexpr unsigned PLAYER_FIELD_MAX_LEVEL = 1;
constexpr unsigned SPELL_EFFECT_LEARN_SPELL = 36;
struct Effect { unsigned Effect; uint32 TriggerSpell; };
struct SpellInfo
{
    std::vector<Effect> effects;
    auto const& GetEffects() const { return effects; }
};
struct SpellMgr
{
    // Core/DBC boundaries, deliberately not inferred from catalog order.
    std::map<uint32, uint32> previous;
    std::map<uint32, SpellInfo> infos;
    uint32 GetPrevSpellInChain(uint32 spell) const
    {
        auto it = previous.find(spell); return it == previous.end() ? 0 : it->second;
    }
    SpellInfo const* GetSpellInfo(uint32 spell) const
    {
        auto it = infos.find(spell); return it == infos.end() ? nullptr : &it->second;
    }
} spellMgr;
auto sSpellMgr = &spellMgr;
class Item
{
public:
    void SetBinding(bool) {} void ClearSoulboundTradeable(Player*) {}
    void SetNotRefundable(Player*) {}
};
class Player
{
public:
    Cache cache;
    State refreshedState;
    Session session;
    bool bound = true;
    uint8 classId = 1;
    unsigned level = 1, talentInits = 0, refreshes = 0, maxLevel = 0;
    std::set<uint32> spells;
    std::map<uint32, uint32> skills;
    std::vector<uint32> learned;
    Player() { cache.state.classId = classId; }
    uint32 GetLevel() const { return level; }
    uint32 getClassMask() const { return 1u << (classId - 1); }
    Session const* GetSession() const { return &session; }
    bool HasSpell(uint32 spell) const { return spells.count(spell); }
    uint32 GetBaseSkillValue(uint32 skill) const
    {
        auto it = skills.find(skill); return it == skills.end() ? 0 : it->second;
    }
    void SetUInt32Value(unsigned field, unsigned value)
    {
        assert(field == PLAYER_FIELD_MAX_LEVEL); maxLevel = value;
    }
    void InitTalentForLevel() { ++talentInits; }
    Item* GetItemByGuid(ObjectGuid) { return nullptr; }
    bool GetQuestRewardStatus(uint32) const { return false; }
    uint32 GetZoneId() const { return 0; }
    uint32 GetAreaId() const { return 0; }
    void learnSpell(uint32 spell);
};
Cache* PlayerCache(Player const* player) { return &const_cast<Player*>(player)->cache; }
namespace WoWPilago
{
State* GetState(Player const* player)
{
    return player && player->bound ? &PlayerCache(player)->state : nullptr;
}
bool IsBoundHuman(Player const* player) { return player && player->bound; }
// Persistence boundary only. The extracted login hook must refresh before reconcile.
void RefreshState(Player* player)
{
    ++player->refreshes; player->cache.state = player->refreshedState;
}
void RecordCheck(Player*, int64) {}
}
void ZoneChecks(Player*, uint32) {}
''' + extract("constexpr std::array<uint32, 5> RidingSpells =") + r''';
namespace Learning
{
// A copy permits explicit nonzero requirement fixtures; the shipped rows are zero.
auto Ranks = WoWPilago::Ranks;
''' + extract("bool CanLearn(") + "\n" + extract("bool CanTrain(") + r'''
}
using Learning::CanLearn;
using Learning::CanTrain;
struct PlayerScript
{
    virtual ~PlayerScript() = default;
    virtual bool OnPlayerCanAddSpell(Player*, uint32, uint8, bool, bool) = 0;
    virtual bool OnPlayerCanTrainSpell(Player const*, uint32) = 0;
    virtual void OnPlayerLearnSpell(Player*, uint32) = 0;
    virtual void OnPlayerLevelChanged(Player*, uint8) = 0;
    virtual void OnPlayerLogin(Player*) = 0;
};
struct Hooks : PlayerScript
{
''' + "\n".join(extract(signature) for signature in (
            "bool OnPlayerCanAddSpell(", "bool OnPlayerCanTrainSpell(",
            "void OnPlayerLearnSpell(", "void OnPlayerLevelChanged(",
            "void OnPlayerLogin(")) + r'''
};
// This models only successful insertion and notification, not core's spell engine.
void Player::learnSpell(uint32 spell)
{
    assert(Hooks().OnPlayerCanAddSpell(this, spell, 0, false, false));
    if (spells.insert(spell).second)
    {
        learned.push_back(spell);
        Hooks().OnPlayerLearnSpell(this, spell);
    }
}
namespace WoWPilago
{
''' + extract("void Reconcile(") + r'''
}
void expect(Player& player, uint32 spell, bool allowed)
{
    assert(CanLearn(&player, spell) == allowed);
    // None of spec mask, temporary, or learn-from-skill may evade the gate.
    for (uint8 mask : {0, 1, 3})
        for (bool temporary : {false, true})
            for (bool fromSkill : {false, true})
                assert(Hooks().OnPlayerCanAddSpell(&player, spell, mask, temporary, fromSkill) == allowed);
    assert(CanTrain(&player, spell) == allowed);
    assert(Hooks().OnPlayerCanTrainSpell(&player, spell) == allowed);
    // Synthetic SpellInfo wrapper proves each target gate also survives training indirection.
    constexpr uint32 wrapper = 900002;
    spellMgr.infos[wrapper].effects = {{SPELL_EFFECT_LEARN_SPELL, spell}};
    assert(CanTrain(&player, wrapper) == allowed);
    assert(Hooks().OnPlayerCanTrainSpell(&player, wrapper) == allowed);
}
RankDef& rank(uint32 spell)
{
    auto it = std::find_if(Learning::Ranks.begin(), Learning::Ranks.end(), [=](auto const& row)
        { return row.spell == spell; });
    assert(it != Learning::Ranks.end()); return *it;
}
int main()
{
''' + assertions + "\n}\n"
        with tempfile.TemporaryDirectory(prefix="wowpilago-ability-learning-") as directory:
            path = pathlib.Path(directory)
            (path / "check.cpp").write_text(source)
            subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=undefined", "-fno-sanitize-recover=all",
                            "-I", str(ROOT / "src"), str(path / "check.cpp"),
                            "-o", str(path / "check")], check=True)
            subprocess.run([str(path / "check")], check=True)

    def test_every_catalog_rank_class_unlock_level_and_baseline_prerequisites(self):
        self.run_methods(r'''
    unsigned prerequisites = 0;
    for (auto const& row : WoWPilago::Ranks)
    {
        auto ability = std::find_if(Abilities.begin(), Abilities.end(), [&](auto const& a)
            { return a.baseSpell == row.baseSpell; });
        assert(ability != Abilities.end());
        for (bool loading : {false, true})
        {
            Player p; p.classId = ability->classId; p.level = row.level;
            p.cache.state.classId = p.classId; p.session.loading = loading;
            for (uint8 i = 0; i < ability->prerequisiteCount; ++i)
                p.spells.insert(ability->prerequisites[i]);
            expect(p, row.spell, false);
            p.cache.state.abilityUnlocks.insert(row.baseSpell);
            expect(p, row.spell, true);
            --p.level; expect(p, row.spell, false); ++p.level;
            p.classId = ability->classId == 1 ? 2 : 1;
            expect(p, row.spell, false); p.classId = ability->classId;
            for (uint8 i = 0; i < ability->prerequisiteCount; ++i)
            {
                ++prerequisites;
                p.spells.erase(ability->prerequisites[i]);
                expect(p, row.spell, loading);
                p.spells.insert(ability->prerequisites[i]);
            }
        }
    }
    assert(prerequisites > 0);
''')

    def test_previous_rank_and_unordered_saved_chain(self):
        self.run_methods(r'''
    // Pinned Charge chain. The catalog itself does not carry previous-rank IDs.
    spellMgr.previous = {{6178, 100}, {11578, 6178}};
    Player p; p.level = 46; p.cache.state.abilityUnlocks.insert(100);
    p.spells.insert(2457);
    expect(p, 11578, false);
    p.spells.insert(100); expect(p, 11578, false);
    p.spells.insert(6178); expect(p, 11578, true);
    p.spells.clear(); p.session.loading = true;
    for (uint32 spell : {11578u, 6178u, 100u})
    {
        expect(p, spell, true); p.learnSpell(spell);
    }
    assert(p.talentInits == 0); // Loading must not trigger prerequisite reconciliation.
    p.session.loading = false;
    expect(p, 11578, false); // Baseline stance was not saved yet.
    p.spells.insert(2457); expect(p, 11578, true);
    for (bool loading : {false, true})
    {
        p.session.loading = loading;
        p.cache.state.abilityUnlocks.clear(); expect(p, 11578, false);
        p.cache.state.abilityUnlocks.insert(100);
        p.classId = 2; expect(p, 11578, false); p.classId = 1;
        p.level = 45; expect(p, 11578, false); p.level = 46;
    }
''')

    def test_required_spell_and_skill_use_real_rank_shape(self):
        self.run_methods(r'''
    // All shipped requirement fields are zero. Set one existing row, not a fake catalog.
    auto& row = rank(6178);
    assert(row.requiredSpell == 0 && row.requiredSkill == 0 && row.requiredSkillRank == 0);
    row.requiredSpell = 71; row.requiredSkill = 26; row.requiredSkillRank = 50;
    spellMgr.previous[6178] = 100;
    Player p; p.level = row.level; p.cache.state.abilityUnlocks.insert(100);
    p.spells = {100, 2457, 71}; p.skills[26] = 50;
    expect(p, 6178, true);
    p.spells.erase(71); expect(p, 6178, false);
    p.session.loading = true; expect(p, 6178, true);
    p.spells.clear(); expect(p, 6178, true); // All spell-order dependencies relaxed.
    p.skills[26] = 49; expect(p, 6178, false);
    p.skills.clear(); expect(p, 6178, false);
    p.skills[26] = 50; expect(p, 6178, true);
    p.cache.state.abilityUnlocks.clear(); expect(p, 6178, false);
    p.cache.state.abilityUnlocks.insert(100);
    p.classId = 2; expect(p, 6178, false); p.classId = 1;
    --p.level; expect(p, 6178, false); ++p.level;
    p.session.loading = false; p.spells = {100, 2457, 71};
    p.skills[26] = 49; expect(p, 6178, false);
    p.skills[26] = 50; expect(p, 6178, true);
''')

    def test_baseline_unbound_and_trainer_learn_spell_wrapper(self):
        self.run_methods(r'''
    Player p;
    for (bool loading : {false, true})
    {
        p.session.loading = loading;
        for (uint32 spell : {2457u, 2458u, 71u, 768u, 5487u, 133u})
            expect(p, spell, true); // Left to core, not granted by this policy.
        p.bound = false;
        for (auto const& row : WoWPilago::Ranks) expect(p, row.spell, true);
        p.bound = true;
    }
    p.session.loading = false;
    constexpr uint32 wrapper = 900001;
    // Synthetic trainer wrapper at the SpellInfo boundary, not a claim about DBC IDs.
    spellMgr.infos[wrapper].effects = {{SPELL_EFFECT_LEARN_SPELL, 100}};
    assert(CanLearn(&p, wrapper));
    auto train = [&](bool allowed)
    {
        assert(CanTrain(&p, wrapper) == allowed);
        assert(Hooks().OnPlayerCanTrainSpell(&p, wrapper) == allowed);
    };
    train(false);
    p.cache.state.abilityUnlocks.insert(100); train(false);
    p.level = 4; train(false);
    p.spells.insert(2457); train(true);
    p.classId = 2; train(false); p.classId = 1;
    p.cache.state.abilityUnlocks.clear(); train(false);
    p.session.loading = true; train(false); // Loading is not permission.
    p.bound = false; train(true); p.bound = true;
    p.session.loading = false; p.cache.state.abilityUnlocks.insert(100);
    // Check every effect, not just the first permitted target.
    spellMgr.infos[wrapper].effects = {{36, 2457}, {36, 100}, {36, 20230}};
    train(false);
    p.level = 20; p.cache.state.abilityUnlocks.insert(20230); train(true);
    spellMgr.infos[wrapper].effects = {{36, 0}, {6, 11578}};
    train(true); // Zero trigger and non-LEARN_SPELL effects do not gate training.
    spellMgr.infos.erase(wrapper); train(true);
    // A gated wrapper must also pass its own permission before its effects matter.
    spellMgr.infos[20252].effects = {{36, 2457}};
    expect(p, 20252, false);
''')

    def test_prerequisite_wrapper_releases_pummel_but_not_its_intercept_child(self):
        self.run_methods(r'''
    Player p; Hooks hooks; p.level = 80;
    p.cache.state.capItems = 7; p.cache.state.victory = true;
    p.spells.insert(2457);
    p.cache.state.abilityUnlocks.insert(6552);
    Reconcile(&p);
    assert(!p.HasSpell(2458) && !p.HasSpell(6552) && !p.HasSpell(20252));
    // Model only effect36's target insertion boundary, not the actual spell engine.
    // Native wrapper8616's first child is the stance, its second is Intercept.
    assert(hooks.OnPlayerCanAddSpell(&p, 2458, 255, false, false));
    p.learnSpell(2458);
    assert((p.learned == std::vector<uint32>{2458, 6552}));
    assert(!hooks.OnPlayerCanAddSpell(&p, 20252, 255, false, false));
    assert(!p.HasSpell(20252));
    Reconcile(&p);
    assert((p.learned == std::vector<uint32>{2458, 6552}));
    assert(p.cache.state.victory && p.maxLevel == 80);
''')

    def test_pending_base_receipt_level_login_and_prerequisite_learning(self):
        self.run_methods(r'''
    Player p; Hooks hooks; p.level = 3;
    Reconcile(&p); assert(p.learned.empty());
    // Receipt publication is a boundary here: expose committed permission then run
    // actual Reconcile, as APDelivery::Publish does. No receipt/SQL proof is claimed.
    p.cache.state.abilityUnlocks.insert(100);
    Reconcile(&p); assert(!p.HasSpell(100));
    p.level = 4; hooks.OnPlayerLevelChanged(&p, 3);
    assert(p.cache.savePending && !p.HasSpell(100));
    unsigned calls = p.talentInits;
    p.learnSpell(133); assert(p.talentInits == calls);
    p.learnSpell(2457);
    assert(p.HasSpell(100) && p.talentInits == calls + 1);
    assert((p.learned == std::vector<uint32>{133, 2457, 100}));
    Reconcile(&p); assert(p.learned.size() == 3); // No duplicate base grant.
    p.level = 46; hooks.OnPlayerLevelChanged(&p, 4);
    assert(!p.HasSpell(6178) && !p.HasSpell(11578)); // Receipt grants base only.

    Player level; level.cache.state.abilityUnlocks.insert(5246); level.level = 21;
    Reconcile(&level); assert(level.learned.empty());
    level.level = 22; hooks.OnPlayerLevelChanged(&level, 21);
    assert(level.HasSpell(5246) && level.cache.savePending);

    Player receipt; receipt.level = 22;
    Reconcile(&receipt); assert(receipt.learned.empty());
    receipt.cache.state.abilityUnlocks.insert(5246); Reconcile(&receipt);
    assert((receipt.learned == std::vector<uint32>{5246}));

    Player login; login.level = 4;
    login.refreshedState.classId = 1; login.refreshedState.abilityUnlocks.insert(100);
    login.session.loading = true; login.learnSpell(2457);
    assert(login.talentInits == 0 && !login.HasSpell(100));
    login.session.loading = false; hooks.OnPlayerLogin(&login);
    assert(login.refreshes == 1 && login.HasSpell(100));
    hooks.OnPlayerLogin(&login);
    assert((login.learned == std::vector<uint32>{2457, 100}));

    // Every real baseline prerequisite can release its pending base, without
    // granting another class's permission or an unreceived sibling ability.
    for (auto const& ability : Abilities)
    {
        if (!ability.prerequisiteCount) continue;
        Player pending; pending.classId = ability.classId; pending.level = ability.level;
        pending.cache.state.classId = ability.classId;
        pending.cache.state.abilityUnlocks.insert(ability.baseSpell);
        Reconcile(&pending); assert(!pending.HasSpell(ability.baseSpell));
        for (uint8 i = 0; i < ability.prerequisiteCount; ++i)
            pending.learnSpell(ability.prerequisites[i]);
        assert(pending.HasSpell(ability.baseSpell));
        for (auto const& other : Abilities)
            if (other.baseSpell != ability.baseSpell) assert(!pending.HasSpell(other.baseSpell));
    }
    Player unbound; unbound.bound = false; unbound.level = 22;
    unbound.cache.state.abilityUnlocks.insert(5246); Reconcile(&unbound);
    assert(unbound.learned.empty() && unbound.talentInits == 0);
''')


if __name__ == "__main__":
    unittest.main()
