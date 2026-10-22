"""Run the client callbacks under an installed Lua 5.1-compatible interpreter."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AddonTests(unittest.TestCase):
    def run_lua(self, script, expected):
        interpreters = [path for name in ("lua5.1", "luajit") if (path := shutil.which(name))]
        self.assertTrue(interpreters, "Install Lua 5.1 or LuaJIT to test the 3.3.5a addon")
        for interpreter in interpreters:
            with self.subTest(interpreter=interpreter):
                result = subprocess.run([interpreter, script], cwd=ROOT, text=True,
                                        capture_output=True, check=True)
                self.assertIn(expected, result.stdout)

    def test_receipt_notifications(self):
        self.run_lua("tests/test_addon.lua", "addon tests passed")

    def test_graphical_shop(self):
        self.run_lua("tests/test_shop_addon.lua", "shop addon tests passed")


if __name__ == "__main__":
    unittest.main()
