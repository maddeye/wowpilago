"""Real AP construction/fill tests; no replacement catalogs or constant-only world tests."""
from collections import Counter
from itertools import product
import json
import unittest
from unittest.mock import patch

from BaseClasses import CollectionState, ItemClassification
from Fill import distribute_items_restrictive
from test.bases import WorldTestBase
from test.general import setup_solo_multiworld, setup_multiworld

from .. import CATEGORY_OPTIONS, WoWPilagoWorld
from ..catalog import CHECKS, CHECK_BY_KEY, GEAR, GEAR_BY_ID, ITEM_DEFINITIONS, PROFILES, REWARDS, filter_profile, in_starting_region, legendary_name
from ..progression import (Experience, TALENT_RESERVATION_LEVELS, ability_eligible, award_xp,
                           level_cap, raise_cap, riding_eligible, talent_points)
from ..shop import facets, generate_stock


def assert_filled_reachable(multiworld, visited=None):
    """Walk actual placements from an empty state, not an all-items approximation."""
    state = CollectionState(multiworld)
    remaining = list(multiworld.get_locations())
    while remaining:
        sphere = [location for location in remaining if location.can_reach(state)]
        if not sphere:
            raise AssertionError(f"Unreachable actual placements: {[loc.name for loc in remaining]}")
        if visited is not None:
            visited.extend(sphere)
        for location in sphere:
            remaining.remove(location)
            if location.item:
                state.collect(location.item, True, location)
    if not multiworld.has_beaten_game(state):
        raise AssertionError("Actual placements do not reach level-80 victory")
    for location in multiworld.get_locations():
        if location.address and any(c["ap_id"] == location.address and c["kind"] == "raid" for c in CHECKS):
            if location.item.classification != ItemClassification.filler:
                raise AssertionError(f"Non-filler at raid {location.name}")
    return state


class WoWPilagoTest(WorldTestBase):
    game = "World of Warcraft"

    def test_profile_locations_and_early_checks(self):
        checks = filter_profile(CHECKS, self.world.profile)
        self.assertEqual(len(self.multiworld.get_locations()), len(checks) + 1)
        state = CollectionState(self.multiworld)
        early = [loc for loc in self.multiworld.get_locations() if loc.address and loc.can_reach(state)]
        local = [check for check in checks if in_starting_region(check, self.world.profile)
                 and self.multiworld.get_location(check["name"], self.player).can_reach(state)]
        self.assertEqual(len(local), 20)
        self.assertGreaterEqual(len(early), len(local))
        self.assertTrue(all(self.multiworld.get_location(check["name"], self.player).parent_region.name.startswith("Starting region")
                            for check in local))

    def test_pool(self):
        counts = Counter(item.name for item in self.multiworld.itempool)
        self.assertEqual(sum(counts.values()), len(self.multiworld.get_unfilled_locations()))
        self.assertEqual(counts["Progressive Level Cap"], 7)
        self.assertEqual(sum(counts.values()), 213)
        self.assertEqual(counts["Gold Cache"], 49)
        self.assertEqual(counts["Consumable Cache"], 36)
        self.assertEqual(sum(counts[r["name"]] * r["value"] for r in REWARDS if r["kind"] == "voucher"), 204)
        self.assertEqual(sum(counts[r["name"]] for r in REWARDS if r["kind"] == "voucher"), 88)
        for reward in REWARDS:
            if reward["classification"] != "filler":
                self.assertEqual(counts[reward["name"]], reward["base_count"])
        reference = {r["name"]: r["base_count"] for r in REWARDS}
        self.assertEqual((reference["Gold Cache"], reference["Consumable Cache"]), (100, 72))
        categories = Counter()
        for reward in REWARDS:
            categories[reward["classification"]] += reward["base_count"]
        categories["useful"] += 8 + 2  # Class abilities and named legendaries.
        self.assertEqual(categories, {"progression": 11, "useful": 117, "filler": 172})
        self.assertEqual(sum(categories.values()), 300)
        for item in self.multiworld.itempool:
            if ITEM_DEFINITIONS[item.name]["kind"] in {"ability", "talent", "voucher", "legendary", "bag"}:
                self.assertEqual(item.classification, ItemClassification.useful)

    def test_caps_only_victory(self):
        state = CollectionState(self.multiworld)
        victory = self.multiworld.get_location("Reach Level 80", 1)
        for _ in range(6):
            state.collect(self.world.create_item("Progressive Level Cap"))
        self.assertFalse(victory.can_reach(state))
        state.collect(self.world.create_item("Progressive Level Cap"))
        self.assertTrue(victory.can_reach(state))
        state.sweep_for_advancements()
        self.assertTrue(self.multiworld.has_beaten_game(state))
        self.assertFalse(state.has("Northrend Access", 1))

    def test_no_useful_reward_gates_checks(self):
        state = CollectionState(self.multiworld)
        for item in self.multiworld.itempool:
            if item.advancement:
                state.collect(item)
        for location in self.multiworld.get_locations():
            self.assertTrue(location.can_reach(state), location.name)

    def test_actual_fill_and_cap_selflocks(self):
        distribute_items_restrictive(self.multiworld)
        assert_filled_reachable(self.multiworld)
        state = CollectionState(self.multiworld)
        remaining = list(self.multiworld.get_locations())
        cap_count = 0
        while remaining:
            sphere = [loc for loc in remaining if loc.can_reach(state)]
            self.assertTrue(sphere)
            before = state.count("Progressive Level Cap", 1)
            for loc in sphere:
                remaining.remove(loc)
                if loc.item and loc.item.name == "Progressive Level Cap":
                    check = next(c for c in CHECKS if c["ap_id"] == loc.address)
                    self.assertLessEqual(self.world.requirements[check["key"]][0], 10 + before * 10)
                    cap_count += 1
                if loc.item:
                    state.collect(loc.item, True, loc)
        self.assertEqual(cap_count, 7)

    def test_slot_data(self):
        data = json.loads(json.dumps(self.world.fill_slot_data()))
        self.assertEqual(data["protocol_version"], 2)
        self.assertEqual(len(data["selected_checks"]), len(self.multiworld.get_locations()) - 1)
        self.assertEqual(len(data["merchant"]["stock"]), 60)
        self.assertEqual(data["merchant"]["total_cost"], sum(entry["price"] for entry in data["merchant"]["stock"]))
        self.assertEqual(len(data["legendary_ids"]), 2)
        for wow_id in data["legendary_ids"]:
            self.assertEqual(data["rewards"][str(919400000 + wow_id)], {"kind": "legendary", "value": wow_id})
        self.assertNotIn("919000001", data["rewards"])

    def test_reproducible_and_personal(self):
        self.world_setup(seed=31337)
        first = self.world.fill_slot_data()
        self.world_setup(seed=31337)
        self.assertEqual(first, self.world.fill_slot_data())
        self.assertNotEqual(first["merchant"], generate_stock(31337, 2, 1))


class ProfileAndOptionsTest(unittest.TestCase):
    def test_all_legal_profiles(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                mw = setup_multiworld(WoWPilagoWorld, seed=52, options={"character_race": profile["race_id"],
                    "character_class": profile["class_id"]})
                state = CollectionState(mw)
                early = [loc for loc in mw.get_locations() if loc.address and loc.can_reach(state)]
                local_ids = {check["ap_id"] for check in mw.worlds[1].selected_checks if in_starting_region(check, profile)}
                local = [location for location in early if location.address in local_ids]
                self.assertEqual(len(local), 20, profile)
                distribute_items_restrictive(mw)
                assert_filled_reachable(mw)

    def test_illegal_profile(self):
        with self.assertRaisesRegex(ValueError, "Illegal WotLK"):
            setup_multiworld(WoWPilagoWorld, options={"character_race": "human", "character_class": "druid"})
        with self.assertRaises(Exception):
            WoWPilagoWorld.options_dataclass.type_hints["character_class"].from_any(6)

    def test_every_category_combination(self):
        for profile in PROFILES:
            for mask in range(64):
                options = {name: bool(mask & (1 << bit)) for bit, name in enumerate(CATEGORY_OPTIONS.values())}
                options.update(character_race=profile["race_id"], character_class=profile["class_id"])
                with self.subTest(options=options):
                    mw = setup_multiworld(WoWPilagoWorld, seed=mask, options=options,
                                          steps=("generate_early", "create_regions"))
                    # Category capacity errors must not hide a missing/incorrect starting region.
                    start = mw.get_region(f"Starting region {profile['starting_zone']}", 1)
                    self.assertTrue(start.can_reach(CollectionState(mw)))
                    self.assertEqual(len(mw.get_region("Menu", 1).exits), 1)
                    self.assertIs(mw.get_region("Menu", 1).exits[0].connected_region, start)
                    try:
                        mw.worlds[1].create_items()
                    except ValueError as error:
                        self.assertIn("fixed progression/useful rewards", str(error))
                        continue
                    mw.worlds[1].set_rules()
                    self.assertEqual(len(mw.itempool), len(mw.get_unfilled_locations()))
                    distribute_items_restrictive(mw)
                    assert_filled_reachable(mw)
                    for item in mw.itempool:
                        definition = ITEM_DEFINITIONS[item.name]
                        if definition["kind"] == "riding":
                            expected = ItemClassification.progression if definition["value"] in mw.worlds[1].progression_riding else ItemClassification.useful
                            self.assertEqual(item.classification, expected)

    def test_prefilled_location_accounting(self):
        mw = setup_multiworld(WoWPilagoWorld, steps=("generate_early", "create_regions"), seed=91)
        world = mw.worlds[1]
        location = next(loc for loc in mw.get_unfilled_locations() if loc.can_reach(mw.state))
        location.place_locked_item(world.create_item("Equipment Voucher +1"))
        world.create_items()
        world.set_rules()
        self.assertEqual(len(mw.itempool), len(mw.get_unfilled_locations()))
        self.assertEqual(sum(item.name == "Equipment Voucher +1" for item in mw.itempool), 44)
        distribute_items_restrictive(mw)
        assert_filled_reachable(mw)

    def test_multiplayer_fill(self):
        mw = setup_multiworld([WoWPilagoWorld, WoWPilagoWorld], seed=107,
            options=[{}, {"character_race": "tauren", "character_class": "druid"}])
        distribute_items_restrictive(mw)
        assert_filled_reachable(mw)

    def test_exclusions_and_balancing(self):
        from worlds.generic.Rules import exclusion_rules
        for accessibility in ("full", "minimal"):
            mw = setup_multiworld(WoWPilagoWorld, seed=987, options={
                "accessibility": accessibility, "progression_balancing": 99})
            excluded = {loc.name for loc in mw.get_locations() if loc.address and loc.can_reach(mw.state)}
            excluded = set(sorted(excluded)[:5])
            exclusion_rules(mw, 1, excluded)
            distribute_items_restrictive(mw)
            assert_filled_reachable(mw)
            for name in excluded:
                self.assertFalse(mw.get_location(name, 1).item.advancement)

    def test_named_legendary_ids_never_alias(self):
        legendary_items = [item for item in GEAR if item["quality"] == 5]
        for item in legendary_items:
            definition = ITEM_DEFINITIONS[legendary_name(item)]
            self.assertEqual(definition["ap_id"], 919400000 + item["wow_id"])
            self.assertEqual(definition["value"], item["wow_id"])
        self.assertEqual(len({legendary_name(item) for item in legendary_items}), len(legendary_items))

    def test_configurable_legendary_count(self):
        for count in (0, 1, 2, 5, 10):
            mw = setup_multiworld(WoWPilagoWorld, seed=371, options={"legendary_count": count})
            self.assertEqual(sum(ITEM_DEFINITIONS[item.name]["kind"] == "legendary" for item in mw.itempool), count)
            self.assertEqual(len(mw.itempool), len(mw.get_unfilled_locations()))
            distribute_items_restrictive(mw)
            assert_filled_reachable(mw)
        with self.assertRaisesRegex(ValueError, "compatible named legendaries"):
            setup_multiworld(WoWPilagoWorld, options={"character_class": "paladin", "legendary_count": 10})

    def test_stock_compatibility_and_cap(self):
        for class_id in sorted({profile["class_id"] for profile in PROFILES}):
            default = generate_stock(31415, 1, class_id)
            self.assertGreater(default["total_cost"], 204)
            self.assertLessEqual(sum(sorted(entry["price"] for entry in default["stock"])[:45]), 204)
            from ..catalog import CLASS_ROLES, viable_roles
            viable_facets = set().union(*(facets(item, class_id) for item in GEAR
                if class_id in item["allowable_classes"] and item["quality"] != 5 and viable_roles(item, class_id)))
            stocked_facets = set().union(*(facets(GEAR_BY_ID[entry["wow_id"]], class_id) for entry in default["stock"]))
            self.assertEqual({value for kind, value in stocked_facets if kind == "role"}, CLASS_ROLES[class_id])
            # Legal proficiency alone must not admit caster cloth for Warriors or caster sets for Hunters.
            for entry in default["stock"]:
                item = GEAR_BY_ID[entry["wow_id"]]
                self.assertTrue(viable_roles(item, class_id), item)
            for item in GEAR:
                if class_id in item["allowable_classes"] and not viable_roles(item, class_id):
                    self.assertNotIn(item["wow_id"], {entry["wow_id"] for entry in default["stock"]})
            self.assertTrue(viable_facets <= stocked_facets, viable_facets - stocked_facets)
            no_sets = generate_stock(31415, 1, class_id, 120, 4, 0)
            no_set_ids = {entry["wow_id"] for entry in no_sets["stock"]}
            self.assertEqual(len(no_set_ids), 120)
            self.assertTrue(all(not no_set_ids.intersection(featured["pieces"])
                                for featured in no_sets["featured_sets"]))
            for size in (30, 60, 120):
                merchant = generate_stock(31415, 1, class_id, size, 4, 100)
                stock = merchant["stock"]
                ids = {entry["wow_id"] for entry in stock}
                self.assertEqual(len(ids), size)
                for wow_id in ids:
                    self.assertIn(class_id, GEAR_BY_ID[wow_id]["allowable_classes"])
                    self.assertNotEqual(GEAR_BY_ID[wow_id]["quality"], 5)
                    self.assertTrue(viable_roles(GEAR_BY_ID[wow_id], class_id))
                rolled = {piece for featured in merchant["featured_sets"] for piece in featured["rolled_pieces"]}
                if len(rolled) <= size:
                    self.assertTrue(rolled <= ids)
                else:
                    self.assertTrue(ids <= rolled)
                self.assertEqual(merchant, generate_stock(31415, 1, class_id, size, 4, 100))


def old_inherited_requirements(check):
    """Independent pre-travel feasibility oracle over the real curated parent chain."""
    ancestors = [check]
    seen = set()
    cap, expansions, riding = 10, set(), set()
    while ancestors:
        current = ancestors.pop()
        if current["key"] in seen:
            continue
        seen.add(current["key"])
        cap = max(cap, current["min_cap"])
        expansions.update({current["expansion"]} - {"azeroth"})
        riding.update({current["riding"]} - {"none"})
        ancestors.extend(CHECK_BY_KEY[key] for key in current["prerequisites"])
    if "cold_weather" in riding:
        riding.add("expert")
        cap = max(cap, 77)
    if "expert" in riding:
        cap = max(cap, 60)
    return cap, tuple(sorted(expansions)), tuple(sorted(riding))


def travel_state(mw, caps=0, outland=False, northrend=False, expert=False, cold_weather=False):
    state = CollectionState(mw)
    # Explicit inventories also cover Cold Weather, currently classified useful and not collected by AP.
    for name, count in (("Progressive Level Cap", caps), ("Outland Access", outland),
                        ("Northrend Access", northrend), ("Expert Riding", expert),
                        ("Cold Weather Flying", cold_weather)):
        if count:
            state.add_item(name, 1, int(count))
    return state


class CriticalTravelTest(unittest.TestCase):
    def make_world(self, profile=None, **options):
        if profile:
            options.update(character_race=profile["race_id"], character_class=profile["class_id"])
        return setup_multiworld(WoWPilagoWorld, seed=39, options=options,
                                steps=("generate_early", "create_regions", "set_rules"))

    def test_every_profile_inventory_matches_old_inherited_rule(self):
        """52 * 8 caps * 4 expansion flags * 4 riding flags; every numbered location."""
        comparisons = 0
        for profile in PROFILES:
            mw = self.make_world(profile)
            world = mw.worlds[1]
            rows = [(check, mw.get_location(check["name"], 1), old_inherited_requirements(check))
                    for check in world.selected_checks]
            for check, _, requirement in rows:
                self.assertEqual(world.requirements[check["key"]], requirement)
            for caps, outland, north, expert, cold in product(range(8), (False, True),
                                                             (False, True), (False, True), (False, True)):
                state = travel_state(mw, caps, outland, north, expert, cold)
                expansions = {name for name, have in (("outland", outland), ("northrend", north)) if have}
                riding = {name for name, have in (("expert", expert), ("cold_weather", cold)) if have}
                for check, location, (cap, required_expansions, required_riding) in rows:
                    old_rule = (caps >= max(0, (cap - 1) // 10)
                                and set(required_expansions) <= expansions and set(required_riding) <= riding)
                    self.assertEqual(location.can_reach(state), old_rule,
                                     (profile, check["key"], caps, outland, north, expert, cold))
                    self.assertEqual(location.parent_region.entrances[0].access_rule(state), old_rule,
                                     ("full leaf rule", check["key"], caps, outland, north, expert, cold))
                    comparisons += 1
                self.assertEqual(mw.get_location("Reach Level 80", 1).can_reach(state), caps == 7)
                self.assertEqual(mw.get_region("Outland", 1).can_reach(state), caps >= 5 and outland)
                self.assertEqual(mw.get_region("Northrend", 1).can_reach(state), caps >= 6 and north)
        self.assertEqual(comparisons, sum(len(filter_profile(CHECKS, p)) for p in PROFILES) * 128)

    def test_core_structure_owners_counts_and_faction_routes(self):
        expected_counts = {1: 213, 2: 205, 3: 213, 4: 213, 5: 206, 6: 206,
                           7: 213, 8: 205, 10: 215, 11: 218}
        for profile in PROFILES:
            with self.subTest(profile=profile):
                mw = self.make_world(profile)
                world = mw.worlds[1]
                empty = CollectionState(mw)
                menu = mw.get_region("Menu", 1)
                start = mw.get_region(f"Starting region {profile['starting_zone']}", 1)
                azeroth = mw.get_region("Azeroth", 1)
                outland = mw.get_region("Outland", 1)
                north = mw.get_region("Northrend", 1)
                core = {menu, start, azeroth, outland, north}
                self.assertEqual(len(menu.exits), 1)
                self.assertIs(menu.exits[0].connected_region, start)
                self.assertEqual(menu.exits[0].name,
                                 f"Begin {profile['faction']} profile at {profile['starting_zone']}")
                self.assertEqual([loc.name for loc in menu.locations], ["Reach Level 80"])
                victory = menu.locations[0]
                self.assertIsNone(victory.address)
                self.assertTrue(victory.locked)
                self.assertEqual(victory.item.name, "Level 80 Victory")
                self.assertTrue(start.can_reach(empty))
                self.assertTrue(azeroth.can_reach(empty))
                self.assertFalse(outland.can_reach(empty))
                self.assertFalse(north.can_reach(empty))
                self.assertEqual(len(outland.entrances), 1)
                self.assertEqual(len(north.entrances), 1)
                self.assertIs(outland.entrances[0].parent_region, azeroth)
                self.assertIs(north.entrances[0].parent_region, azeroth)
                self.assertEqual(outland.entrances[0].name, "Dark Portal: Azeroth to Outland")
                route = "Alliance boat" if profile["faction"] == "alliance" else "Horde zeppelin"
                self.assertEqual(north.entrances[0].name, f"{route}: Azeroth to Northrend")
                for source, destination, name in (
                    (start, azeroth, "Leave starting region via ordinary Azeroth travel"),
                    (azeroth, start, "Return to starting region"),
                    (outland, azeroth, "Dark Portal return"),
                    (north, azeroth, "Return boat/zeppelin to Azeroth"),
                ):
                    edge = next(edge for edge in source.exits if edge.connected_region is destination)
                    self.assertEqual(edge.name, name)
                    self.assertTrue(edge.access_rule(empty))  # Returns do not introduce another gate.
                self.assertFalse(mw.get_entrance("Dark Portal return", 1).can_reach(empty))
                self.assertFalse(mw.get_entrance("Return boat/zeppelin to Azeroth", 1).can_reach(empty))
                self.assertTrue(mw.get_entrance("Dark Portal return", 1).can_reach(travel_state(mw, 5, True)))
                self.assertTrue(mw.get_entrance("Return boat/zeppelin to Azeroth", 1).can_reach(
                    travel_state(mw, 6, northrend=True)))
                groups = {}
                local = []
                for check in world.selected_checks:
                    location = mw.get_location(check["name"], 1)
                    opening = in_starting_region(check, profile)
                    leaf = location.parent_region
                    owner = start if opening else mw.get_region(check["expansion"].title(), 1)
                    self.assertNotIn(leaf, core)
                    self.assertEqual(len(leaf.entrances), 1)
                    self.assertIs(leaf.entrances[0].parent_region, owner)
                    self.assertFalse(leaf.exits)
                    key = (check["expansion"], world.requirements[check["key"]], opening)
                    self.assertIs(groups.setdefault(key, leaf), leaf)
                    if opening:
                        local.append(check)
                        self.assertTrue(location.can_reach(empty))
                self.assertEqual(len(set(groups.values())), len(groups))
                self.assertEqual(len(mw.regions), 5 + len(groups))
                self.assertEqual(len({region.name for region in mw.regions}), len(mw.regions))
                self.assertEqual(len(mw.get_locations()), expected_counts[profile["race_id"]] + 1)
                self.assertEqual(Counter(c["kind"] for c in local), {"quest": 17, "exploration": 1, "level": 2})
                self.assertEqual(sum(loc.address is None for loc in mw.get_locations()), 1)

    def test_start_exists_with_all_categories_disabled(self):
        for profile in PROFILES:
            mw = self.make_world(profile, **{name: False for name in CATEGORY_OPTIONS.values()})
            self.assertEqual(len(mw.regions), 5)
            self.assertEqual(len(mw.get_locations()), 1)
            self.assertFalse(mw.worlds[1].selected_checks)
            self.assertTrue(mw.get_region(f"Starting region {profile['starting_zone']}", 1).can_reach(mw.state))
            self.assertTrue(mw.get_region("Azeroth", 1).can_reach(mw.state))
            self.assertFalse(mw.get_region("Outland", 1).can_reach(mw.state))
            with self.assertRaisesRegex(ValueError, "fixed progression/useful rewards"):
                mw.worlds[1].create_items()

    def test_conservative_thresholds_independent_expansions_and_flight(self):
        mw = self.make_world()
        world = mw.worlds[1]
        self.assertEqual(min(c["min_cap"] for c in CHECKS if c["expansion"] == "outland"), 60)
        self.assertEqual(min(c["min_cap"] for c in CHECKS if c["expansion"] == "northrend"), 70)
        flight = {c["key"] for c in CHECKS if c["riding"] == "expert"}
        self.assertEqual(flight, {"boss_19219", "boss_19221", "boss_19220", "dungeon_554"})
        self.assertFalse(any(c["riding"] == "cold_weather" for c in CHECKS))
        cases = {"exploration_3483": (5, True, False, False),
                 "exploration_3537": (6, False, True, False),
                 "exploration_495": (6, False, True, False)}
        cases.update({key: (6, True, False, True) for key in flight})
        cases.update({c["key"]: (7, False, True, False) for c in world.selected_checks
                      if c["kind"] == "exploration" and c["expansion"] == "northrend" and c["min_cap"] == 80})
        for key, inventory in cases.items():
            location = mw.get_location(CHECK_BY_KEY[key]["name"], 1)
            self.assertTrue(location.can_reach(travel_state(mw, *inventory)), key)
            below = (inventory[0] - 1, *inventory[1:])
            self.assertFalse(location.can_reach(travel_state(mw, *below)), key)
            for index, needed in enumerate(inventory[1:], 1):
                if needed:
                    missing = list(inventory)
                    missing[index] = False
                    self.assertFalse(location.can_reach(travel_state(mw, *missing)), (key, index))
        for key in flight:
            self.assertFalse(mw.get_location(CHECK_BY_KEY[key]["name"], 1).can_reach(
                travel_state(mw, 7, True, True, cold_weather=True)), key)

    def test_map530_azeroth_starts_and_six_curated_zones(self):
        zones_seen = set()
        zones = {3430, 3433, 3487, 3524, 3525, 3557}
        for profile in PROFILES:
            if profile["race_id"] not in (10, 11):
                continue
            mw = self.make_world(profile)
            self.assertEqual(profile["map_id"], 530)
            self.assertTrue(mw.get_region(f"Starting region {profile['starting_zone']}", 1).can_reach(mw.state))
            for check in mw.worlds[1].selected_checks:
                if check["kind"] != "exploration" or check["wow_id"] not in zones:
                    continue
                zones_seen.add(check["wow_id"])
                self.assertEqual(check["expansion"], "azeroth")
                self.assertIn(check["faction"], ("any", profile["faction"]))
                self.assertEqual(mw.worlds[1].requirements[check["key"]][1], ())
                state = travel_state(mw, (check["min_cap"] - 1) // 10)
                self.assertTrue(mw.get_location(check["name"], 1).can_reach(state))
            selected = {c["key"] for c in mw.worlds[1].selected_checks}
            for zone in zones:
                check = CHECK_BY_KEY[f"exploration_{zone}"]
                if check["faction"] not in ("any", profile["faction"]):
                    self.assertNotIn(check["key"], selected)
        self.assertEqual(zones_seen, zones)

    def test_quest_closure_is_feasibility_without_completion_events(self):
        self.assertEqual(sum(c["kind"] == "quest" and bool(c["prerequisites"]) for c in CHECKS), 56)
        for profile in PROFILES:
            mw = self.make_world(profile)
            selected = {c["key"] for c in mw.worlds[1].selected_checks}
            for check in mw.worlds[1].selected_checks:
                self.assertLessEqual(set(check["prerequisites"]), selected)
                self.assertEqual(mw.worlds[1].requirements[check["key"]], old_inherited_requirements(check))
                if check["kind"] == "quest" and check["prerequisites"]:
                    self.assertEqual(old_inherited_requirements(check), (10, (), ()))
                    self.assertTrue(mw.get_location(check["name"], 1).can_reach(mw.state))
            self.assertFalse(mw.state.locations_checked)
            self.assertEqual([loc.item.name for loc in mw.get_locations() if loc.locked], ["Level 80 Victory"])
            # Disabled boss rewards still require the ability to do their ordinary gameplay.
            disabled = self.make_world(profile, dungeon_bosses=False)
            selected = {c["key"] for c in disabled.worlds[1].selected_checks}
            for check in disabled.worlds[1].selected_checks:
                self.assertEqual(disabled.worlds[1].requirements[check["key"]], old_inherited_requirements(check))
                for parent in check["prerequisites"]:
                    if CHECK_BY_KEY[parent]["kind"] == "boss":
                        self.assertNotIn(parent, selected)
                        self.assertIn(parent, disabled.worlds[1].requirements)
            location = disabled.get_location(CHECK_BY_KEY["dungeon_554"]["name"], 1)
            self.assertTrue(location.can_reach(travel_state(disabled, 6, True, expert=True)))
            self.assertFalse(location.can_reach(travel_state(disabled, 6, True)))

    def test_invalid_quest_parent_closure_and_cycle(self):
        # Mutate one real row temporarily; no replacement world, IDs, or serialized catalog.
        with patch.dict(CHECK_BY_KEY["quest_7"], prerequisites=["quest_missing"]):
            mw = self.make_world()
            selected = {c["key"] for c in mw.worlds[1].selected_checks}
            self.assertTrue({"quest_7", "quest_15", "quest_21"}.isdisjoint(selected))
            self.assertIn("quest_783", selected)
        with patch.dict(CHECK_BY_KEY["quest_783"], prerequisites=["quest_21"]):
            with self.assertRaisesRegex(ValueError, "Cyclic curated quest prerequisites"):
                self.make_world()

    def test_future_inherited_owner_split_and_cold_weather(self):
        # Exercise existing future-facing logic with real rows, restored before the test exits.
        # Azeroth and northern leaves can share requirements but must never share ownership.
        with patch.dict(CHECK_BY_KEY["exploration_12"], prerequisites=["exploration_3537"]), \
             patch.dict(CHECK_BY_KEY["exploration_3483"], prerequisites=["exploration_3537"]):
            profile = next(p for p in PROFILES if p["race_id"] == 3)
            mw = self.make_world(profile)
            azeroth = mw.get_location(CHECK_BY_KEY["exploration_12"]["name"], 1).parent_region
            north = mw.get_location(CHECK_BY_KEY["exploration_3537"]["name"], 1).parent_region
            self.assertIsNot(azeroth, north)
            self.assertIs(azeroth.entrances[0].parent_region, mw.get_region("Azeroth", 1))
            outland = mw.get_location(CHECK_BY_KEY["exploration_3483"]["name"], 1)
            self.assertIs(outland.parent_region.entrances[0].parent_region, mw.get_region("Outland", 1))
            self.assertFalse(outland.can_reach(travel_state(mw, 7, True)))
            self.assertTrue(outland.can_reach(travel_state(mw, 7, True, True)))
            # Full leaf gate must still reject missing inherited Northrend after reaching Outland.
            self.assertFalse(outland.parent_region.entrances[0].access_rule(travel_state(mw, 7, True)))
        with patch.dict(CHECK_BY_KEY["exploration_3537"], riding="cold_weather"), \
             patch.dict(CHECK_BY_KEY["boss_19219"], riding="cold_weather"):
            mw = self.make_world()
            world = mw.worlds[1]
            self.assertEqual(world.requirements["exploration_3537"], (77, ("northrend",), ("cold_weather", "expert")))
            self.assertTrue(world.create_item("Cold Weather Flying").advancement)
            self.assertTrue(world.create_item("Expert Riding").advancement)
            for key in ("exploration_3537", "boss_19219", "boss_19220", "dungeon_554"):
                self.assertEqual(world.requirements[key], old_inherited_requirements(CHECK_BY_KEY[key]))
                location = mw.get_location(CHECK_BY_KEY[key]["name"], 1)
                for caps, expert, cold in product(range(8), (False, True), (False, True)):
                    self.assertEqual(location.can_reach(travel_state(mw, caps, True, True, expert, cold)),
                                     caps == 7 and expert and cold, key)


class ProgressionTest(unittest.TestCase):
    def test_caps(self):
        self.assertEqual([level_cap(n) for n in range(9)], [10, 20, 30, 40, 50, 60, 70, 80, 80])

    def test_talents_every_level_and_arrival(self):
        self.assertEqual(len(TALENT_RESERVATION_LEVELS), 12)
        for level in range(1, 81):
            normal = max(0, level - 9)
            eligible = sum(level >= threshold for threshold in TALENT_RESERVATION_LEVELS)
            self.assertEqual(talent_points(level, 0), normal - eligible)
            self.assertEqual(talent_points(level, 12), normal)
            for unlocks in range(13):
                self.assertEqual(talent_points(level, unlocks), normal - eligible + min(unlocks, eligible))
        self.assertEqual(talent_points(80, 12), 71)
        self.assertEqual(talent_points(80, 0), 59)
        self.assertEqual(talent_points(14, 12), 5)
        self.assertEqual(talent_points(15, 1), 6)

    def test_exact_xp_bank_and_release(self):
        xp = {level: 101 for level in range(1, 80)}
        self.assertEqual(award_xp(Experience(9, 90), 1000, 10, xp), Experience(10, 0, 50))
        banked = award_xp(Experience(10), 37, 10, xp)
        self.assertEqual(banked, Experience(10, 0, 37))
        self.assertEqual(award_xp(banked, 100, 10, xp), Experience(10, 0, 50))
        self.assertEqual(raise_cap(banked, 10, 10, xp), banked)
        released = raise_cap(banked, 10, 20, xp)
        self.assertEqual(released, Experience(10, 37, 0))
        self.assertEqual(raise_cap(released, 20, 30, xp), released)
        self.assertEqual(award_xp(Experience(79, 100), 500, 80, xp), Experience(80))
        self.assertEqual(raise_cap(Experience(79, 100, 50), 79, 80, xp), Experience(80))

    def test_eligibility(self):
        self.assertFalse(riding_eligible("expert", 59, {"apprentice", "journeyman", "expert"}))
        self.assertTrue(riding_eligible("expert", 60, {"expert"}))
        self.assertFalse(riding_eligible("cold_weather", 77, {"cold_weather"}))
        self.assertTrue(riding_eligible("cold_weather", 77, {"expert", "cold_weather"}))
        self.assertFalse(riding_eligible("cold_weather", 76, set()))
        ability = {"min_level": 20, "prerequisites": [123]}
        self.assertFalse(ability_eligible(ability, 19, {123}))
        self.assertFalse(ability_eligible(ability, 20, set()))
        self.assertTrue(ability_eligible(ability, 20, {123}))
