"""Execute the production exploration producer and callbacks with core-boundary stubs.

These tests do not establish physical reachability or live-client credit.
"""
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

from test_native_progression import production_method

ROOT = pathlib.Path(__file__).resolve().parents[1]


class NativeExplorationTests(unittest.TestCase):
    def test_zone_and_same_zone_area_transitions(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        self.assertIsNotNone(compiler, "a C++17 compiler is required")
        production = (ROOT / "src/APProgression.cpp").read_text()
        extract = lambda signature: production_method(production, signature)
        start = production.index("    ProgressionPlayer() :")
        end = production.index("\n\n    void OnPlayerLoadFromDB", start)
        constructor = production[start:end].replace("ProgressionPlayer()", "Hooks()", 1)
        hook_names = sorted(set(re.findall(r"\bPLAYERHOOK_[A-Z_]+\b", constructor))
                            | {"PLAYERHOOK_ON_UPDATE_AREA"})
        source = r'''
#include <cassert>
#include <cstdint>
#include <initializer_list>
#include <set>
#include <vector>
using uint32 = std::uint32_t;
using int64 = std::int64_t;
enum class CheckKind { Exploration, Quest };
struct Check { CheckKind kind; uint32 wowId, mapId; int64 id; };
// The area9 fixture shares zone12; no zone transition occurs when entering it.
std::vector<Check> Checks = {
    {CheckKind::Exploration, 12, 0, 919700012},
    {CheckKind::Exploration, 9, 0, 919700009},
    {CheckKind::Exploration, 9, 1, 919700099},
    {CheckKind::Quest, 9, 0, 919500009},
};
struct WorldLocation {
    uint32 map;
    WorldLocation(uint32 m, float, float, float, float) : map(m) {}
};
struct Player {
    bool bound = true, alive = true, flight = false, access = true;
    uint32 map = 0, zone = 12, area = 87;
    bool IsAlive() const { return alive; }
    bool IsInFlight() const { return flight; }
    uint32 GetMapId() const { return map; }
    uint32 GetZoneId() const { return zone; }
    uint32 GetAreaId() const { return area; }
    float GetPositionX() const { return 0; }
    float GetPositionY() const { return 0; }
    float GetPositionZ() const { return 0; }
    float GetOrientation() const { return 0; }
};
bool IsBoundHuman(Player const* p) { return p && p->bound; }
bool CanAccess(Player const* p, uint32 map, WorldLocation const* destination) {
    assert(destination && destination->map == map);
    return p->access;
}
std::vector<int64> candidates;
void RecordCheck(Player*, int64 id) { candidates.push_back(id); }
''' + extract("void ZoneChecks(") + "\nenum { " + ", ".join(hook_names) + r''' };
struct PlayerScript {
    std::set<unsigned> enabled;
    PlayerScript(char const*, std::initializer_list<unsigned> hooks) : enabled(hooks) {}
    virtual ~PlayerScript() = default;
    virtual void OnPlayerUpdateZone(Player*, uint32, uint32) = 0;
    virtual void OnPlayerUpdateArea(Player*, uint32, uint32) = 0;
};
struct Hooks : PlayerScript {
''' + constructor + "\n" + extract("void OnPlayerUpdateZone(") + "\n" + extract("void OnPlayerUpdateArea(") + r'''
};
int main() {
    Player p;
    Hooks hooks;
    assert(hooks.enabled.count(PLAYERHOOK_ON_UPDATE_ZONE) == 1);
    assert(hooks.enabled.count(PLAYERHOOK_ON_UPDATE_AREA) == 1);
    hooks.OnPlayerUpdateZone(&p, 12, 87);
    assert((candidates == std::vector<int64>{919700012}));
    candidates.clear();
    // Core calls the hook BEFORE m_areaUpdateId = newArea. Reading GetAreaId
    // here would credit the old87, not the entered9.
    hooks.OnPlayerUpdateArea(&p, 87, 9);
    assert(p.GetAreaId() == 87);
    assert((candidates == std::vector<int64>{919700009}));
    candidates.clear();
    hooks.OnPlayerUpdateArea(&p, 9, 87);
    assert(candidates.empty());
    hooks.OnPlayerUpdateArea(&p, 87, 999999);
    assert(candidates.empty());
    p.map = 1;
    hooks.OnPlayerUpdateArea(&p, 87, 9);
    assert((candidates == std::vector<int64>{919700099}));
    candidates.clear(); p.map = 0;
    for (unsigned guard = 0; guard < 4; ++guard) {
        p.bound = guard != 0; p.alive = guard != 1;
        p.flight = guard == 2; p.access = guard != 3;
        hooks.OnPlayerUpdateArea(&p, 87, 9);
        hooks.OnPlayerUpdateZone(&p, 12, 9);
        assert(candidates.empty());
    }
    p.bound = true; p.alive = true; p.flight = false; p.access = true;
    hooks.OnPlayerUpdateArea(&p, 87, 9);
    assert((candidates == std::vector<int64>{919700009}));
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "exploration.cpp"
            binary = pathlib.Path(directory) / "exploration"
            path.write_text(source)
            subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            str(path), "-o", str(binary)], check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
