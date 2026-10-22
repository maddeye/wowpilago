import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("audit_ap_ids", ROOT / "tools/audit_ap_ids.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class APIDTests(unittest.TestCase):
    def test_collisions_respect_item_and_location_namespaces(self):
        ours = {"item": {919000001: "Reserved potion"}, "location": {919500022: "Retired quest"}}
        registry = {
            "Other game": SimpleNamespace(item_name_to_id={"Conflict": 919000001, "Event": None},
                                          location_name_to_id={"Separate namespace": 919000001, "Conflict": 919500022}),
            "World of Warcraft": SimpleNamespace(item_name_to_id={"Self": 919000001}, location_name_to_id={}),
        }
        self.assertEqual(audit.collisions(ours, registry), [
            {"kind": "item", "ap_id": 919000001, "ours": "Reserved potion", "other_game": "Other game", "other_name": "Conflict"},
            {"kind": "location", "ap_id": 919500022, "ours": "Retired quest", "other_game": "Other game", "other_name": "Conflict"},
        ])
        self.assertEqual(audit.collisions(ours, {"Safe game": SimpleNamespace(item_name_to_id={}, location_name_to_id={})}), [])


if __name__ == "__main__":
    unittest.main()
