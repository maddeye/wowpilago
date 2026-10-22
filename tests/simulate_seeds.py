"""Thousands of real AP restrictive fills plus independent featured-piece statistics.

Usage: <AP python> tests/simulate_seeds.py /path/to/Archipelago [--seeds 2000]
Results are written to the isolated user's directory, not to the upstream tree.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import time

from verify_world import bootstrap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("--seeds", type=int, default=2000)
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("--seeds must be positive")
    _, root = bootstrap(args.upstream)
    from BaseClasses import CollectionState
    from Fill import distribute_items_restrictive
    from test.general import setup_multiworld
    from worlds.wowpilago import WoWPilagoWorld
    from worlds.wowpilago.catalog import CLASS_ROLES, GEAR_BY_ID, ITEM_DEFINITIONS, PROFILES, in_starting_region, viable_roles
    from worlds.wowpilago.shop import facets, generate_stock
    from worlds.wowpilago.test import assert_filled_reachable

    started = time.monotonic()
    costs, affordable_fractions = [], []
    pieces = included = eight_sets = eight_complete = overflow = 0
    early_counts, local_counts = [], []
    economy_quarters = [[], [], [], []]
    profiles_seen = set()
    role_coverage = Counter()
    for seed in range(args.seeds):
        profile = PROFILES[seed % len(PROFILES)]
        profiles_seen.add((profile["race_id"], profile["class_id"]))
        options = {"character_race": profile["race_id"], "character_class": profile["class_id"]}
        mw = setup_multiworld(WoWPilagoWorld, seed=seed, options=options)
        world = mw.worlds[1]
        empty = CollectionState(mw)
        early = sum(bool(loc.address) and loc.can_reach(empty) for loc in mw.get_locations())
        local = sum(mw.get_location(check["name"], 1).can_reach(empty) for check in world.selected_checks
                    if in_starting_region(check, profile))
        assert 20 <= local <= 35, (seed, profile, local)
        early_counts.append(early)
        local_counts.append(local)
        distribute_items_restrictive(mw)
        visited = []
        assert_filled_reachable(mw, visited)
        merchant = world.merchant
        ids = {entry["wow_id"] for entry in merchant["stock"]}
        assert len(ids) == 60
        assert all(profile["class_id"] in GEAR_BY_ID[piece]["allowable_classes"]
                   and GEAR_BY_ID[piece]["quality"] != 5
                   and viable_roles(GEAR_BY_ID[piece], profile["class_id"]) for piece in ids)
        coverage = set().union(*(facets(GEAR_BY_ID[piece], profile["class_id"]) for piece in ids))
        assert all(("role", role) in coverage for role in CLASS_ROLES[profile["class_id"]]), (seed, profile)
        assert merchant["total_cost"] > 204, (seed, merchant["total_cost"])
        for category, value in coverage:
            if category == "role":
                role_coverage[value] += 1
        for featured in merchant["featured_sets"]:
            total, rolled = len(featured["pieces"]), len(featured["rolled_pieces"])
            pieces += total
            included += rolled
            if total == 8:
                eight_sets += 1
                eight_complete += rolled == 8
            if not merchant["overflow"]:
                assert set(featured["rolled_pieces"]) <= ids
                assert ids.intersection(featured["pieces"]) == set(featured["rolled_pieces"])
        overflow += merchant["overflow"] > 0
        costs.append(merchant["total_cost"])
        balance, purchased = 204, 0
        for price in sorted(entry["price"] for entry in merchant["stock"]):
            if balance < price:
                break
            balance -= price
            purchased += 1
        affordable_fractions.append(purchased / 60)
        ordinary = [location for location in visited if location.address]
        for quarter in range(1, 5):
            income = sum(ITEM_DEFINITIONS[location.item.name]["value"]
                for location in ordinary[:len(ordinary) * quarter // 4]
                if ITEM_DEFINITIONS[location.item.name]["kind"] == "voucher")
            spent = affordable = 0
            for price in sorted(entry["price"] for entry in merchant["stock"]):
                if spent + price > income:
                    break
                spent += price
                affordable += 1
            economy_quarters[quarter - 1].append(affordable)
        if seed % 50 == 0:
            assert merchant == generate_stock(seed, 1, profile["class_id"])
            # Small-stock overflow and zero-probability rolls use real equipment too.
            for probability in (0, 100):
                small = generate_stock(seed, 1, profile["class_id"], 30, 4, probability)
                assert len({entry["wow_id"] for entry in small["stock"]}) == 30
        if (seed + 1) % 250 == 0:
            print(f"{seed + 1}/{args.seeds} actual AP fills passed", flush=True)
    report = {"seed_count": args.seeds, "reachable_real_ap_fills": args.seeds,
        "profiles_tested": len(profiles_seen), "legal_profiles": len(PROFILES),
        "early_checks_min": min(early_counts), "early_checks_max": max(early_counts),
        "local_early_checks_min": min(local_counts), "local_early_checks_max": max(local_counts),
        "piece_rolls": pieces, "included_pieces": included, "piece_rate": included / pieces,
        "eight_piece_sets": eight_sets, "complete_eight_piece_rolls": eight_complete,
        "eight_piece_complete_rate": eight_complete / eight_sets if eight_sets else None,
        "expected_eight_piece_complete_rate": 0.8 ** 8, "default_stock_overflow_seeds": overflow,
        "shop_cost_min": min(costs), "shop_cost_mean": statistics.mean(costs), "shop_cost_max": max(costs),
        "affordable_fraction_mean_cheapest_first": statistics.mean(affordable_fractions),
        "role_coverage_seed_counts": dict(role_coverage),
        "affordable_entries_at_check_quarters_mean": [statistics.mean(quarter) for quarter in economy_quarters],
        "elapsed_seconds": round(time.monotonic() - started, 2)}
    if args.seeds >= 1000:
        assert len(profiles_seen) == len(PROFILES)
        assert abs(report["piece_rate"] - 0.8) < 0.015, report
        assert eight_sets >= 1000, "Insufficient actual eight-piece sets for a distribution test"
        assert abs(report["eight_piece_complete_rate"] - 0.8 ** 8) < 0.025, report
        assert report["affordable_fraction_mean_cheapest_first"] >= 0.7, report
    output = root / "seed-simulation.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print(f"PASS real AP fills and deterministic stock simulation. Report: {output}")


if __name__ == "__main__":
    main()
