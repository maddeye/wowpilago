"""Missing private inputs skip; existing broken inputs must fail validation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from integration_inputs import require_inputs


class IntegrationInputsTests(unittest.TestCase):
    def test_missing_input_names_the_prerequisite(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "private-archive.json"
            with self.assertRaises(unittest.SkipTest) as caught:
                require_inputs(missing)
            self.assertEqual(str(caught.exception), f"Integration prerequisite missing: {missing}")

    def test_present_corrupt_input_is_not_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "evidence.json"
            source.write_text("not JSON")
            require_inputs(source)
            with self.assertRaises(json.JSONDecodeError):
                json.loads(source.read_text())

    def test_dangling_input_fails_instead_of_skipping(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "evidence.json"
            source.symlink_to(source.with_name("missing.json"))
            with self.assertRaises(FileNotFoundError):
                require_inputs(source)

    def test_unreadable_input_fails_instead_of_skipping(self):
        with patch.object(Path, "lstat", side_effect=PermissionError("unreadable archive")):
            with self.assertRaises(PermissionError):
                require_inputs("private-archive.json")


if __name__ == "__main__":
    unittest.main()
