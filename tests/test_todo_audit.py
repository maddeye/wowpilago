import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.audit_todo import audit, requirements
from integration_inputs import require_inputs


class TodoAuditTests(unittest.TestCase):
    def test_repository_checkmarks_have_evidence(self):
        root = Path(__file__).resolve().parents[1]
        todo = (root / "TODO.md").read_text()
        evidence = json.loads((root / "docs/requirements-evidence.json").read_text())
        private_archives = {root.joinpath(*Path(artifact).parts[:2])
                            for record in evidence.values()
                            for artifact in record.get("artifacts", [])
                            if artifact.startswith(".local/")}
        require_inputs(*sorted(private_archives))
        self.assertEqual(audit(todo, evidence, root)[1], [])

    def test_repository_audit_does_not_skip_incomplete_private_archives(self):
        todo = "- [x] Ship.\n"
        identity = requirements(todo)[0]["id"]
        evidence = {identity: {"status": "verified", "artifacts": [".local/native-case/run.txt"],
                               "verification": "python test.py"}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "TODO.md").write_text(todo)
            (root / "docs").mkdir()
            (root / "docs/requirements-evidence.json").write_text(json.dumps(evidence))
            with patch(__name__ + ".__file__", str(root / "tests/test_todo_audit.py")):
                with self.assertRaisesRegex(unittest.SkipTest, "Integration prerequisite missing:"):
                    self.test_repository_checkmarks_have_evidence()
                (root / ".local").mkdir()
                with self.assertRaisesRegex(unittest.SkipTest, "Integration prerequisite missing:"):
                    self.test_repository_checkmarks_have_evidence()
                (root / ".local/native-case").mkdir()
                with self.assertRaisesRegex(AssertionError, "missing artifact .local/native-case/run.txt"):
                    self.test_repository_checkmarks_have_evidence()
                (root / ".local/native-case/run.txt").write_text("Archived test result.\n")
                self.test_repository_checkmarks_have_evidence()
                evidence[identity]["artifacts"] = ["public-result.txt"]
                (root / "docs/requirements-evidence.json").write_text(json.dumps(evidence))
                with self.assertRaisesRegex(AssertionError, "missing artifact public-result.txt"):
                    self.test_repository_checkmarks_have_evidence()

    def test_extracts_sections_and_stable_requirement_identity(self):
        first = requirements("## Runtime\n- [ ] Deliver exactly once.\n")
        checked = requirements("## Runtime\n- [x] Deliver exactly once.\n")
        self.assertEqual(first[0]["section"], "Runtime")
        self.assertEqual(first[0]["id"], checked[0]["id"])
        self.assertFalse(first[0]["checked"])
        self.assertTrue(checked[0]["checked"])

    def test_checked_tasks_require_real_evidence_artifacts(self):
        todo = "## Runtime\n- [x] Deliver exactly once.\n"
        identity = requirements(todo)[0]["id"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(audit(todo, {}, root)[1], [
                f"Checked without verified evidence: {identity} Deliver exactly once.",
            ])
            evidence = {identity: {"status": "verified", "artifacts": ["run.txt"], "verification": "python test.py"}}
            self.assertEqual(audit(todo, evidence, root)[1], [f"{identity} missing artifact run.txt"])
            (root / "run.txt").write_text("Verified actual delivery once.\n")
            self.assertEqual(audit(todo, evidence, root)[1], [])

    def test_unknown_tasks_and_empty_verification_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            _, errors = audit("- [ ] Ship.\n", {"unknown": {"status": "verified"}}, Path(directory))
        self.assertEqual(errors, ["Unknown requirement unknown", "unknown has no verification command or artifact"])


if __name__ == "__main__":
    unittest.main()
