"""Execute production cast/zone hooks with small core-boundary stubs, not a realm.

Effect fixtures use pinned Spell.dbc aura types and base points. Adaptive wrappers
carry a dummy aura and select a concrete child spell in core's spell_gen_mount.
"""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from test_native_progression import production_method

ROOT = pathlib.Path(__file__).resolve().parents[1]


class NativeMountCastTests(unittest.TestCase):
    def test_production_mount_cast_gates(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        self.assertIsNotNone(compiler, "a C++17 compiler is required")
        production = (ROOT / "src/APProgression.cpp").read_text()
        source = r'''
#include "APProgression.h"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <vector>
using uint32 = std::uint32_t;
using namespace WoWPilago;
enum AuraType
{
    SPELL_AURA_MOD_INCREASE_MOUNTED_SPEED = 32, SPELL_AURA_MOUNTED = 78,
    SPELL_AURA_FLY = 201, SPELL_AURA_MOD_INCREASE_FLIGHT_SPEED = 206,
    SPELL_AURA_MOD_INCREASE_MOUNTED_FLIGHT_SPEED = 207
};
enum { SPELL_EFFECT_SKILL = 118, SPELL_EFFECT_SKILL_STEP = 44, SKILL_RIDING = 762 };
enum SpellCastResult { SPELL_CAST_OK, SPELL_FAILED_SPELL_UNAVAILABLE, SPELL_FAILED_NOT_HERE };
struct Effect
{
    unsigned Effect = 6, ApplyAuraName = 0;
    int BasePoints = 0, MiscValue = 0;
    int CalcValue(Player const*) const { return BasePoints + 1; }
};
struct SpellInfo
{
    uint32 Id;
    std::vector<Effect> effects;
    auto const& GetEffects() const { return effects; }
    bool HasAura(unsigned aura) const
    {
        return std::any_of(effects.begin(), effects.end(), [=](auto const& effect)
            { return effect.ApplyAuraName == aura; });
    }
};
class Player
{
public:
    State state;
    bool bound = true, trainable = true;
    unsigned level = 77, map = 530, zone = 3483;
    Player* ToPlayer() { return this; }
    unsigned GetLevel() const { return level; }
    unsigned GetMapId() const { return map; }
    unsigned GetZoneId() const { return zone; }
    bool canFlyInZone(uint32 mapId, uint32 zoneId, SpellInfo const* info);
};
namespace WoWPilago
{
State* GetState(Player const* player)
{
    return player->bound ? &const_cast<Player*>(player)->state : nullptr;
}
}
bool CanTrain(Player const* player, uint32) { return player->trainable; }
constexpr std::array<uint32, 5> RidingSpells = {33388, 33391, 34090, 34091, 54197};
struct PlayerScript
{
    virtual ~PlayerScript() = default;
    virtual bool OnPlayerCanFlyInZone(Player*, uint32, uint32, SpellInfo const*) = 0;
};
struct ZoneHook : PlayerScript
{
''' + production_method(production, "bool OnPlayerCanFlyInZone(") + r'''
};
bool Player::canFlyInZone(uint32 mapId, uint32 zoneId, SpellInfo const* info)
{
    return ZoneHook().OnPlayerCanFlyInZone(this, mapId, zoneId, info);
}
struct Spell
{
    Player* caster;
    SpellInfo const* info;
    Player* GetCaster() const { return caster; }
    SpellInfo const* GetSpellInfo() const { return info; }
};
struct AllSpellScript
{
    virtual ~AllSpellScript() = default;
    virtual void OnSpellCheckCast(Spell*, bool, SpellCastResult&) = 0;
};
struct CastHook : AllSpellScript
{
''' + production_method(production, "void OnSpellCheckCast(") + r'''
};
void check(char const* label, Player& player, SpellInfo const& info, SpellCastResult expected,
    SpellCastResult initial = SPELL_CAST_OK)
{
    // Initial and completion checks both reach the same production hook.
    for (bool strict : {false, true})
    {
        Spell spell{&player, &info};
        auto result = initial;
        CastHook().OnSpellCheckCast(&spell, strict, result);
        if (result != expected)
        {
            std::fprintf(stderr, "%s: spell %u flags %u level %u map %u: expected %d, got %d\n",
                label, info.Id, player.state.ridingFlags, player.level, player.map, expected, result);
            std::abort();
        }
    }
}
int main()
{
    // Raw DBC base points, not final percentages. No skill/item boundary can
    // substitute for this check on an already learned ordinary mount.
    SpellInfo slow{32239, {{6, 78, 0}, {6, 207, 149}, {6, 32, 59}}};
    SpellInfo fast{32242, {{6, 78, 0}, {6, 207, 279}, {6, 32, 99}}};
    SpellInfo fastest{99999, {{6, 78, 0}, {6, 207, 309}, {6, 32, 99}}};
    Player player; player.state.accessFlags = 3; player.state.ridingFlags = 23;
    check("Expert 150 flight", player, slow, SPELL_CAST_OK);
    check("pre-Artisan live bypass", player, fast, SPELL_FAILED_SPELL_UNAVAILABLE);
    check("pre-Artisan 310 flight", player, fastest, SPELL_FAILED_SPELL_UNAVAILABLE);
    player.state.ridingFlags = 4; // Expert alone supplies the ground prerequisites.
    check("Expert-only 150 flight", player, slow, SPELL_CAST_OK);
    player.level = 59;
    check("Expert below 60", player, slow, SPELL_FAILED_NOT_HERE);
    player.level = 60;
    check("Expert at 60", player, slow, SPELL_CAST_OK);
    player.state.ridingFlags = 12;
    player.level = 69;
    check("Artisan below 70", player, fast, SPELL_FAILED_SPELL_UNAVAILABLE);
    player.level = 70;
    check("Artisan at 70", player, fast, SPELL_CAST_OK);
    check("Artisan 310 at 70", player, fastest, SPELL_CAST_OK);
    player.state.ridingFlags = 8;
    check("Artisan without Expert", player, fast, SPELL_FAILED_NOT_HERE);
    player.state.ridingFlags = 12;
    player.map = 571;
    check("Northrend missing Cold Weather", player, fast, SPELL_FAILED_NOT_HERE);
    player.state.ridingFlags = 28; player.level = 76;
    check("Cold Weather below 77", player, slow, SPELL_FAILED_NOT_HERE);
    player.level = 77;
    check("Cold Weather at 77", player, fast, SPELL_CAST_OK);
    player.state.ridingFlags = 20;
    check("Cold Weather without Artisan slow", player, slow, SPELL_CAST_OK);
    check("Cold Weather without Artisan fast", player, fast, SPELL_FAILED_SPELL_UNAVAILABLE);
    player.state.ridingFlags = 31;
    for (unsigned map : {0u, 1u, 530u, 571u})
    {
        player.map = map;
        check("flight map restriction", player, fast,
            map == 530 || map == 571 ? SPELL_CAST_OK : SPELL_FAILED_NOT_HERE);
    }
    player.map = 530; player.zone = 3430;
    check("Azeroth zone on map 530", player, fast, SPELL_FAILED_NOT_HERE);
    player.zone = 3483; player.state.accessFlags = 0;
    check("missing Outland access", player, fast, SPELL_FAILED_NOT_HERE);
    player.state.accessFlags = 3;
    // Druid passive 40121 uses aura 206, not mounted-flight aura 207.
    for (int base : {149, 279, 309})
    {
        SpellInfo druid{40121, {{6, 31, 99}, {6, 206, base}}};
        player.state.ridingFlags = 4;
        check("druid flight passive without Artisan", player, druid,
            base == 149 ? SPELL_CAST_OK : SPELL_FAILED_SPELL_UNAVAILABLE);
        player.state.ridingFlags = 12; player.level = 69;
        check("druid Artisan below 70", player, druid,
            base == 149 ? SPELL_CAST_OK : SPELL_FAILED_SPELL_UNAVAILABLE);
        player.level = 70;
        check("druid Artisan at 70", player, druid, SPELL_CAST_OK);
    }
    SpellInfo ground60{458, {{6, 78, 0}, {6, 32, 59}}};
    SpellInfo ground100{23227, {{6, 78, 0}, {6, 32, 99}}};
    player.map = 1; player.level = 20; player.state.ridingFlags = 1;
    check("Apprentice ground60", player, ground60, SPELL_CAST_OK);
    check("Apprentice ground100", player, ground100, SPELL_FAILED_SPELL_UNAVAILABLE);
    player.state.ridingFlags = 3; player.level = 39;
    check("Journeyman below 40", player, ground100, SPELL_FAILED_SPELL_UNAVAILABLE);
    player.level = 40;
    check("Journeyman at 40", player, ground100, SPELL_CAST_OK);
    player.level = 19;
    check("Apprentice below 20", player, ground60, SPELL_FAILED_SPELL_UNAVAILABLE);
    // Adaptive 47977 wrapper, then its 225-skill child 42667 and fast child 42668.
    SpellInfo wrapper{47977, {{6, 78, 0}, {6, 4, 0}, {77, 0, 0}}};
    player.map = 530; player.level = 77; player.state.ridingFlags = 4;
    check("adaptive wrapper", player, wrapper, SPELL_CAST_OK);
    slow.Id = 42667; fast.Id = 42668;
    check("adaptive Expert child", player, slow, SPELL_CAST_OK);
    check("adaptive fast child", player, fast, SPELL_FAILED_SPELL_UNAVAILABLE);
    player.trainable = false;
    check("existing CanTrain rejection", player, slow, SPELL_FAILED_SPELL_UNAVAILABLE);
    player.bound = false; player.level = 1; player.state.ridingFlags = 0; player.map = 1;
    for (auto const& info : {slow, fast, fastest, ground60, ground100, wrapper})
        check("unbound left to core", player, info, SPELL_CAST_OK);
    check("earlier hook rejection retained", player, fast, SPELL_FAILED_NOT_HERE, SPELL_FAILED_NOT_HERE);
}
'''
        with tempfile.TemporaryDirectory(prefix="wowpilago-mount-cast-") as directory:
            path = pathlib.Path(directory)
            (path / "check.cpp").write_text(source)
            subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=undefined", "-fno-sanitize-recover=all",
                            "-I", str(ROOT / "src"), str(path / "check.cpp"),
                            "-o", str(path / "check")], check=True)
            subprocess.run([str(path / "check")], check=True)


if __name__ == "__main__":
    unittest.main()
