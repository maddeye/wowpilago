import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package", ROOT / "tools/package.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PackageTests(unittest.TestCase):
    def test_addon_archive_contains_every_toc_script(self):
        source = ROOT / "addon/WoWPilago"
        scripts = [line.strip() for line in (source / "WoWPilago.toc").read_text().splitlines()
                   if line.strip() and not line.startswith("##")]
        self.assertEqual(scripts, ["Catalog.lua", "WoWPilago.lua", "Shop.lua"])
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "WoWPilago.zip"
            package.write_archive(source, destination)
            with zipfile.ZipFile(destination) as archive:
                for name in ["WoWPilago.toc", *scripts]:
                    self.assertEqual(archive.read("WoWPilago/" + name), (source / name).read_bytes())

    def test_archive_has_installable_root_and_reproducible_source_and_licenses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "WoWPilago"
            source.mkdir()
            (source / "WoWPilago.toc").write_text("## Interface: 30300\nCatalog.lua\nWoWPilago.lua\n")
            (source / "Catalog.lua").write_text("WoWPilagoRewards = {}\n")
            (source / "WoWPilago.lua").write_text("-- test addon\n")
            (source / "secret.txt").write_text("not an addon asset")
            (source / "__pycache__").mkdir()
            (source / "__pycache__/excluded.py").write_text("not source")
            first, second = root / "one.zip", root / "two.zip"
            package.write_archive(source, first)
            package.write_archive(source, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist(), [
                    "WoWPilago/Catalog.lua", "WoWPilago/LICENSE",
                    "WoWPilago/LICENSES/AGPL-3.0.txt", "WoWPilago/LICENSES/GPL-2.0.txt",
                    "WoWPilago/THIRD_PARTY_NOTICES.md", "WoWPilago/WoWPilago.lua",
                    "WoWPilago/WoWPilago.toc",
                ])
                self.assertEqual(archive.read("WoWPilago/Catalog.lua"), b"WoWPilagoRewards = {}\n")
                for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "LICENSES/AGPL-3.0.txt", "LICENSES/GPL-2.0.txt"):
                    self.assertEqual(archive.read("WoWPilago/" + name), (ROOT / name).read_bytes())
                self.assertTrue(all(entry.date_time == (1980, 1, 1, 0, 0, 0) for entry in archive.infolist()))


if __name__ == "__main__":
    unittest.main()
