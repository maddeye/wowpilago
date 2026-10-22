"""Package into an isolated AP user path; never modify the upstream checkout."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
import zlib


def bootstrap(upstream):
    project = Path(__file__).resolve().parents[1]
    root = Path(tempfile.mkdtemp(prefix="wowpilago-world-test-"))
    os.environ["AP_TEST_WORLDS"] = "wowpilago"
    os.environ["SKIP_REQUIREMENTS_UPDATE"] = "1"
    sys.path.insert(0, str(Path(upstream).resolve()))
    os.chdir(root)
    import Utils
    Utils.user_path.cached_path = str(root)
    worlds = root / "worlds"
    worlds.mkdir()
    source = project / "apworld" / "wowpilago"
    with zipfile.ZipFile(worlds / "wowpilago.apworld", "w") as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix in {".py", ".json"}:
                archive.write(path, str(path.relative_to(source.parent)))
    return project, root


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tests/verify_world.py /path/to/Archipelago")
    project, root = bootstrap(sys.argv[1])
    suite = unittest.defaultTestLoader.loadTestsFromName("worlds.wowpilago.test")
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit(1)
    import Generate
    import Main
    import Utils
    players = root / "players"
    players.mkdir()
    (players / "player.yaml").write_bytes((project / "examples" / "player.yaml").read_bytes())
    args = Generate.mystery_argparse([
        "--player_files_path", str(players), "--outputpath", str(root / "output"),
        "--seed", "919000001", "--spoiler", "1",
    ])
    Main.main(*Generate.main(args))
    generated, = (root / "output").glob("AP_*.zip")
    with zipfile.ZipFile(generated) as archive:
        name, = [name for name in archive.namelist() if name.endswith(".archipelago")]
        data = archive.read(name)
        multidata = Utils.restricted_loads(zlib.decompress(data[1:]))
        spoiler = "\n".join(archive.read(name).decode() for name in archive.namelist() if name.endswith("_Spoiler.txt"))
    slot = multidata["slot_data"][1]
    package = multidata["datapackage"]["World of Warcraft"]
    for label, ap_id in {"Progressive Level Cap": 919100001,
                         "Equipment Voucher +1": 919100031, "Gold Cache": 919100050}.items():
        assert package["item_name_to_id"][label] == ap_id and label in spoiler
    assert package["location_name_to_id"]["Quest: Kobold Camp Cleanup [7]"] == 919500007
    assert "Charge" in package["item_name_to_id"] and "Charge" in spoiler
    assert "Raid: Ragnaros" in package["location_name_to_id"] and "Raid: Ragnaros" in spoiler
    for check in slot["selected_checks"]:
        assert package["location_name_to_id"][check["name"]] == check["ap_id"]
        assert check["name"] in spoiler
    assert slot["protocol_version"] == 2
    assert set(multidata["locations"][1]) == {check["ap_id"] for check in slot["selected_checks"]}
    assert len(slot["merchant"]["stock"]) == 60
    assert len(slot["legendary_ids"]) == 2
    for wow_id in slot["legendary_ids"]:
        assert f"({wow_id})" in spoiler, "Legendary identity missing from actual AP spoiler"
        assert any(item[0] == 919400000 + wow_id for item in multidata["locations"][1].values())
    assert json.loads((project / "apworld/wowpilago/archipelago.json").read_text())["game"] == "World of Warcraft"
    print(f"PASS packaged world, real AP fill, generation, spoiler and protocol-2 multidata. Artifacts: {root}")


if __name__ == "__main__":
    main()
