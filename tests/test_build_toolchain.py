"""Keep the dependency image independent of core and module sources."""
import importlib.util
from pathlib import Path
import shlex
import unittest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("builder", PROJECT / "tools/build_realm.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class BuildToolchainTest(unittest.TestCase):
    def test_dependency_only_image(self):
        dockerfile = (PROJECT / "tests/Dockerfile").read_text().replace("\\\n", " ")
        instructions = [line for line in dockerfile.splitlines()
                        if line.strip() and not line.startswith("#")]
        self.assertEqual(instructions[0], "FROM ubuntu:24.04")
        self.assertEqual([line.split()[0] for line in instructions], ["FROM", "ENV", "RUN"])
        install = shlex.split(instructions[2])
        required = {"build-essential", "ca-certificates", "git", "cmake", "curl", "python3",
                    "libtool", "libboost-all-dev", "default-libmysqlclient-dev", "libssl-dev",
                    "libreadline-dev", "zlib1g-dev", "libbz2-dev", "libncurses5-dev", "liblzma-dev"}
        self.assertTrue(required <= set(install), required - set(install))
        self.assertNotIn("/core", dockerfile)
        self.assertNotIn("/build", instructions[2])

    def test_fresh_build_command_matches_default_without_retagging_runtime(self):
        self.assertEqual(builder.IMAGE, "wowpilago-v2-toolchain-check:latest")
        docs = (PROJECT / "docs/BUILD.md").read_text()
        self.assertIn(f"docker build -f tests/Dockerfile -t {builder.IMAGE} .", docs)
        self.assertIn(builder.CORE_COMMIT, docs)
        self.assertIn(builder.BOTS_COMMIT, docs)


if __name__ == "__main__":
    unittest.main()
