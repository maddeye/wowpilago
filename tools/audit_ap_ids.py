"""Compare active and reserved WoW IDs with the pinned installed AP registry."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def collisions(ours, registry):
    found = []
    for game, world in sorted(registry.items()):
        if game == "World of Warcraft":
            continue
        for kind, names in (("item", world.item_name_to_id), ("location", world.location_name_to_id)):
            for name, code in names.items():
                if code is not None and code in ours[kind]:
                    found.append(dict(kind=kind, ap_id=code, ours=ours[kind][code], other_game=game, other_name=name))
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    args = parser.parse_args()
    revision = subprocess.check_output(["git", "-C", str(args.upstream), "rev-parse", "HEAD"], text=True).strip()
    support = json.loads((ROOT / "support.json").read_text())
    if revision != support["archipelago_commit"]:
        raise SystemExit("Upstream revision differs from support.json")
    os.environ.pop("AP_TEST_WORLDS", None)
    os.environ["SKIP_REQUIREMENTS_UPDATE"] = "1"
    sys.path.insert(0, str(args.upstream.resolve()))
    import Utils
    with tempfile.TemporaryDirectory(prefix="wowpilago-id-audit-") as user:
        Utils.user_path.cached_path = user
        import worlds
        from worlds.AutoWorld import AutoWorldRegister
        data = ROOT / "apworld/wowpilago/data"
        load = lambda name: json.loads((data / (name + ".json")).read_text())
        items = {row["ap_id"]: row["name"] for row in load("rewards")["rewards"] + load("abilities")["abilities"]}
        items.update({919400000 + row["wow_id"]: row["name"] for row in load("gear")["items"] if row["quality"] == 5})
        locations = {row["ap_id"]: row["name"] for row in load("checks")["checks"]}
        active = dict(items=len(items), locations=len(locations))
        for code in support["legacy_item_ids"]:
            items[code] = "Retired potion prototype"
        locations.update({row["ap_id"]: row["name"] for row in load("retired-checks")["checks"]})
        found = collisions(dict(item=items, location=locations), AutoWorldRegister.world_types)
        failed = sorted(str(value) for value in worlds.failed_world_loads)
        report = dict(upstream_commit=revision, active=active, reserved=dict(items=len(items), locations=len(locations)),
                      registered_games=len(AutoWorldRegister.world_types), collisions=found, failed_imports=failed,
                      scope="Installed pinned upstream registry. Uninstalled third-party worlds are not covered.")
        (ROOT / "docs/ap-id-audit.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        if found or failed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
