"""Execute the pinned Factory's patched loop without starting a realm."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from integration_inputs import require_inputs

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("builder", PROJECT / "tools/build_realm.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
CORE = Path(os.environ.get("CORE_PATCH_SOURCE", str(PROJECT.parent / "wow-test/azerothcore")))
PATCH = PROJECT / "patches/playerbots-safety.patch"


def block(text, signature):
    start = text.index(signature)
    brace = text.index("{", start)
    end, depth = brace + 1, 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def pinned(repo, commit, name):
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{commit}:{name}"], text=True)


class PlayerbotsPatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_inputs(CORE, CORE / 'modules/mod-playerbots')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wowpilago-bots-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.factory = self.root / builder.BOTS_FACTORY
        self.factory.parent.mkdir(parents=True)
        self.factory.write_text(pinned(CORE / "modules/mod-playerbots", builder.BOTS_COMMIT,
                                       builder.BOTS_FACTORY))

    def test_apply_reapply_and_reject_modified_archive(self):
        self.assertEqual(builder.apply_playerbots_patch(self.root, PATCH)["state"], "applied")
        self.assertEqual(builder.apply_playerbots_patch(self.root, PATCH)["state"], "already applied")
        self.factory.write_text(self.factory.read_text() + "\n// modified\n")
        before = self.factory.read_bytes()
        with self.assertRaisesRegex(ValueError, "modified pinned"):
            builder.apply_playerbots_patch(self.root, PATCH)
        self.assertEqual(self.factory.read_bytes(), before)

    def test_checkout_and_modified_patch_rejected_without_writes(self):
        before = self.factory.read_bytes()
        (self.root / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "Git-free"):
            builder.apply_playerbots_patch(self.root, PATCH)
        (self.root / ".git").rmdir()
        bad = self.root / "bad.patch"
        bad.write_bytes(PATCH.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "patch digest"):
            builder.apply_playerbots_patch(self.root, bad)
        self.assertEqual(self.factory.read_bytes(), before)

    def test_actual_three_effect_loop_selection_with_sanitizers(self):
        builder.apply_playerbots_patch(self.root, PATCH)
        factory = self.factory.read_text()
        enchant = block(factory, "void PlayerbotFactory::EnchantItem(")
        loop_start = enchant.index("            for (uint8 i =")
        loop = block(enchant[loop_start:], "for (uint8 i =")
        stats = block(factory, "void PlayerbotFactory::AddItemStats(").replace("PlayerbotFactory::", "")
        item = pinned(CORE, builder.CORE_COMMIT, "src/server/game/Entities/Item/ItemTemplate.h")
        enums = pinned(CORE, builder.CORE_COMMIT, "src/server/shared/DataStores/DBCEnums.h")
        dbc = pinned(CORE, builder.CORE_COMMIT, "src/server/shared/DataStores/DBCStructure.h")
        define = next(line for line in dbc.splitlines()
                      if line.startswith("#define MAX_SPELL_ITEM_ENCHANTMENT_EFFECTS "))
        entry = block(dbc, "struct SpellItemEnchantmentEntry")
        program = "#include <cstdint>\n#include <cassert>\nusing uint8 = uint8_t; using uint32 = uint32_t;\n"
        program += block(item, "enum ItemModType") + ";\n"
        program += next(line for line in item.splitlines() if line.startswith("#define MAX_ITEM_MOD ")) + "\n"
        program += block(enums, "enum ItemEnchantmentType") + ";\n"
        program += define + "\n" + entry + ";\n" + stats + "\n"
        program += """
int main() {
    static_assert(MAX_SPELL_ITEM_ENCHANTMENT_EFFECTS == 3);
    static_assert(MAX_ITEM_MOD == 49);
    for (unsigned mask = 0; mask < 8; ++mask) {
        SpellItemEnchantmentEntry record{};
        auto* enchant = &record;
        uint32 mods[] = {ITEM_MOD_INTELLECT, ITEM_MOD_AGILITY, ITEM_MOD_STAMINA};
        for (unsigned slot = 0; slot < 3; ++slot) {
            record.type[slot] = (mask & (1u << slot)) ? ITEM_ENCHANTMENT_TYPE_STAT : ITEM_ENCHANTMENT_TYPE_NONE;
            record.spellid[slot] = mods[slot];
        }
        uint8 sp = 0, ap = 0, tank = 0;
""" + loop + """
        assert(sp == bool(mask & 1) + bool(mask & 4));
        assert(ap == bool(mask & 2) + bool(mask & 4));
        assert(tank == bool(mask & 2) + bool(mask & 4));
    }
}
"""
        source = self.root / "loop.cpp"
        source.write_text(program)
        binary = self.root / "loop"
        compiler = os.environ.get("CXX", "c++")
        subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-g", "-O1",
                        "-fsanitize=address,undefined,bounds", "-fno-sanitize-recover=all",
                        "-fno-omit-frame-pointer", "-no-pie", str(source), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
        # The same executed check must reject the original 49-entry loop.
        source.write_text(program.replace("for (uint8 i = 0; i < MAX_SPELL_ITEM_ENCHANTMENT_EFFECTS; ++i)",
                                          "for (uint8 i = ITEM_MOD_MANA; i < MAX_ITEM_MOD; ++i)"))
        subprocess.run([compiler, "-std=c++17", "-O1", "-fsanitize=undefined,bounds",
                        "-fno-sanitize-recover=all", str(source), "-o", str(binary)], check=True)
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("index 3 out of bounds", result.stderr)


if __name__ == "__main__":
    unittest.main()
