"""Standalone pinned-Detour checks; no server or client connection."""
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".local/v2-build/20261019T150600.624050Z/source"
BINARY = ROOT / ".local/navmesh/navmesh_path"
MMAPS = ROOT.parent / "wow-test/data/client-data/mmaps"
START = [-8911.4, -166.328, 82.2088]
END = [-8947.64, -132.319, 83.7199]


class NavmeshPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_dir() or not shutil.which("g++"):
            raise unittest.SkipTest("pinned source and host g++ required")
        detour = SOURCE / "deps/recastnavigation/Detour"
        BINARY.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            "g++", "-std=c++17", "-O2", "-I" + str(detour / "Include"),
            "-I" + str(SOURCE / "src/common"),
            "-I" + str(SOURCE / "src/common/Collision/Maps"),
            str(ROOT / "tools/navmesh_path.cpp"),
            *map(str, sorted((detour / "Source").glob("*.cpp"))),
            "-o", str(BINARY),
        ], check=True, timeout=60)

    def run_tool(self, *args):
        return subprocess.run([str(BINARY), *map(str, args)], capture_output=True,
                              text=True, timeout=15)

    def route(self, start=START, end=END, *extra):
        return self.run_tool(0, *start, *end, *(extra or ("--base", MMAPS)))

    def assert_error(self, result, message=None):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("navmesh_path:", result.stderr)
        if message:
            self.assertIn(message, result.stderr)

    def test_coordinate_roundtrip(self):
        result = self.run_tool("--self-check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["coordinate_roundtrip"])

    def test_bad_input(self):
        for args in [[], ["bad", *START, *END], [-1, *START, *END],
                     [0, "nan", *START[1:], *END],
                     [0, "inf", *START[1:], *END],
                     [0, "-8911x", *START[1:], *END],
                     [0, *START, *END, "--wrong", "/tmp"]]:
            with self.subTest(args=args):
                self.assert_error(self.run_tool(*args))
        self.assert_error(self.route(START, [0, 0, 0]), "2000-yard")

    def test_missing_and_corrupt_files(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assert_error(self.route(START, END, "--base", directory), "cannot read")
            params = Path(directory) / "000.mmap"
            params.write_bytes(b"bad")
            self.assert_error(self.route(START, END, "--base", directory), "cannot read")
            if not (MMAPS / "000.mmap").exists():
                return
            shutil.copyfile(MMAPS / "000.mmap", params)
            self.assert_error(self.route(START, END, "--base", directory), "no local navmesh")
            tile = Path(directory) / "0004832.mmtile"
            tile.write_bytes(bytes(56))
            self.assert_error(self.route(START, END, "--base", directory), "invalid tile header")
            if (MMAPS / tile.name).exists():
                tile.write_bytes((MMAPS / tile.name).read_bytes()[:56])
                self.assert_error(self.route(START, END, "--base", directory), "cannot read")

    @unittest.skipUnless((MMAPS / "0004832.mmtile").exists(), "actual map-0 tiles required")
    def test_actual_northshire_route(self):
        for start, end in [(START, END), (END, START)]:
            with self.subTest(start=start):
                result = self.route(start, end)
                self.assertEqual(result.returncode, 0, result.stderr)
                route = json.loads(result.stdout)
                points = route["waypoints"]
                self.assertTrue(route["ground_only"])
                self.assertFalse(route["client_walk_verified"])
                self.assertTrue(route["direct_segment_blocked"])
                self.assertIn("0004832.mmtile", route["tiles"])
                self.assertGreater(len(points), 3)
                self.assertLess(math.dist(points[0], start), 0.5)
                self.assertLess(math.dist(points[-1], end), 0.5)
                self.assertTrue(all(79 < p[2] < 85 for p in points))
                self.assertGreater(route["path_length"], route["direct_distance"] + 10)
                self.assertTrue(60 < route["path_length"] < 80)
                self.assertAlmostEqual(sum(math.dist(a, b) for a, b in zip(points, points[1:])),
                                       route["path_length"], places=2)
                # Exit corridor bends east before heading west to Willem, not through the wall.
                self.assertTrue(any(p[0] > -8907 and -161 < p[1] < -155 for p in points))
        self.assert_error(self.route([START[0], START[1], 200], END), "no ground polygon")


class NavmeshArgumentTests(unittest.TestCase):
    def test_route_passes_fixture_directory_or_explicit_override(self):
        tool = NavmeshPathTests()
        with patch.object(tool, "run_tool") as run:
            tool.route()
            run.assert_called_once_with(0, *START, *END, "--base", MMAPS)
            run.reset_mock()
            tool.route(START, END, "--base", "/custom/mmaps")
            run.assert_called_once_with(0, *START, *END, "--base", "/custom/mmaps")


if __name__ == "__main__":
    unittest.main()
