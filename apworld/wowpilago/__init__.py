"""World of Warcraft 3.3.5a, protocol 2. Level 80 is the only victory goal."""
from collections import Counter

from BaseClasses import Item, ItemClassification, Location, LocationProgressType, Region
from worlds.AutoWorld import World

from .catalog import (ABILITIES, CATALOG_VERSION, CHECKS, CHECK_BY_KEY, ITEM_DEFINITIONS,
                      PROFILES, REWARDS, SCHEMA_VERSION, filter_profile, in_starting_region, legendary_name)
from .options import WoWOptions
from .shop import generate_stock, select_legendaries

CATEGORY_OPTIONS = dict(quest="quests", exploration="exploration", boss="dungeon_bosses",
                        dungeon="dungeon_completions", level="level_milestones", raid="raids")
RIDING_NAMES = dict(expert="Expert Riding", cold_weather="Cold Weather Flying")


class WoWItem(Item):
    game = "World of Warcraft"


class WoWLocation(Location):
    game = "World of Warcraft"


class WoWPilagoWorld(World):
    """One legal normal-class character per slot; no Death Knights in v1."""

    game = "World of Warcraft"
    options_dataclass = WoWOptions
    options: WoWOptions
    required_client_version = (0, 6, 8)
    item_name_to_id = {name: definition["ap_id"] for name, definition in ITEM_DEFINITIONS.items()}
    location_name_to_id = {check["name"]: check["ap_id"] for check in CHECKS}
    item_name_groups = {"Level caps": {"Progressive Level Cap"},
                        "Vouchers": {"Equipment Voucher +1", "Equipment Voucher +3", "Equipment Voucher +5"}}
    location_name_groups = {kind: {check["name"] for check in CHECKS if check["kind"] == kind}
                           for kind in CATEGORY_OPTIONS}

    def generate_early(self):
        race, class_id = self.options.character_race.value, self.options.character_class.value
        profiles = [profile for profile in PROFILES if (profile["race_id"], profile["class_id"]) == (race, class_id)]
        if len(profiles) != 1:
            raise ValueError(f"Illegal WotLK race/class profile: race {race}, class {class_id}. Death Knights are excluded in v1.")
        self.profile = dict(profiles[0])
        legal = {check["key"] for check in filter_profile(CHECKS, self.profile)}
        self.requirements = {}

        def requirements(key, trail=()):
            if key in trail:
                raise ValueError(f"Cyclic curated quest prerequisites: {' -> '.join((*trail, key))}")
            if key not in legal:
                raise ValueError(f"Curated prerequisite {key} is incompatible with profile {self.profile}")
            if key not in self.requirements:
                check = CHECK_BY_KEY[key]
                cap = max(10, check["min_cap"])
                expansions = {check["expansion"]} - {"azeroth"}
                riding = {check["riding"]} - {"none"}
                for prerequisite in check["prerequisites"]:
                    pcap, pexpansions, priding = requirements(prerequisite, (*trail, key))
                    cap = max(cap, pcap)
                    expansions.update(pexpansions)
                    riding.update(priding)
                # Flying retains normal eligibility and training prerequisites.
                if "expert" in riding:
                    cap = max(cap, 60)
                if "cold_weather" in riding:
                    cap = max(cap, 77)
                    riding.add("expert")
                self.requirements[key] = (cap, tuple(sorted(expansions)), tuple(sorted(riding)))
            return self.requirements[key]

        self.selected_checks = [check for check in CHECKS if check["key"] in legal
                                and getattr(self.options, CATEGORY_OPTIONS[check["kind"]]).value]
        for check in self.selected_checks:
            requirements(check["key"])
        self.progression_riding = {riding for check in self.selected_checks
                                   for riding in self.requirements[check["key"]][2]}
        self.abilities = [ability for ability in ABILITIES if ability["class_id"] == class_id]
        self.legendaries = select_legendaries(self.multiworld.seed, self.player, class_id,
                                             self.options.legendary_count.value)
        self.merchant = generate_stock(self.multiworld.seed, self.player, class_id,
            self.options.merchant_stock.value, self.options.featured_sets.value,
            self.options.set_piece_probability.value)

    def access_rule(self, requirements):
        cap, expansions, riding = requirements
        needed_caps = max(0, (cap - 10 + 9) // 10)
        player = self.player
        return lambda state: (state.has("Progressive Level Cap", player, needed_caps)
            and all(state.has(f"{expansion.title()} Access", player) for expansion in expansions)
            and all(state.has(RIDING_NAMES[tier], player) for tier in riding))

    def create_regions(self):
        menu = Region("Menu", self.player, self.multiworld)
        start = Region(f"Starting region {self.profile['starting_zone']}", self.player, self.multiworld)
        azeroth = Region("Azeroth", self.player, self.multiworld)
        outland = Region("Outland", self.player, self.multiworld)
        northrend = Region("Northrend", self.player, self.multiworld)
        self.multiworld.regions.extend((menu, start, azeroth, outland, northrend))
        menu.connect(start, f"Begin {self.profile['faction']} profile at {self.profile['starting_zone']}")
        # Ordinary walk/boat/zeppelin travel is abstract, including the map-530 Azeroth starts.
        start.connect(azeroth, "Leave starting region via ordinary Azeroth travel")
        azeroth.connect(start, "Return to starting region")
        azeroth.connect(outland, "Dark Portal: Azeroth to Outland",
                        self.access_rule((60, ("outland",), ())))
        northern_route = "Alliance boat" if self.profile["faction"] == "alliance" else "Horde zeppelin"
        azeroth.connect(northrend, f"{northern_route}: Azeroth to Northrend",
                        self.access_rule((70, ("northrend",), ())))
        outland.connect(azeroth, "Dark Portal return")
        northrend.connect(azeroth, "Return boat/zeppelin to Azeroth")
        owners = {"azeroth": azeroth, "outland": outland, "northrend": northrend}
        regions = {}
        for check in self.selected_checks:
            requirements = self.requirements[check["key"]]
            opening = in_starting_region(check, self.profile)
            # Curated territory owns the leaf, independently of inherited expansion gates.
            owner = check["expansion"]
            key = (owner, requirements, opening)
            if key not in regions:
                name = f"Cap {requirements[0]} / {','.join(requirements[1]) or 'azeroth'} / {','.join(requirements[2]) or 'ground'}"
                parent = start if opening else owners[owner]
                name = f"{parent.name} / {owner} / {name}"
                region = Region(name, self.player, self.multiworld)
                self.multiworld.regions.append(region)
                # Keep every inherited gate, even when redundant with the travel entrance.
                parent.connect(region, rule=self.access_rule(requirements))
                regions[key] = region
            region = regions[key]
            location = WoWLocation(self.player, check["name"], check["ap_id"], region)
            if check["kind"] == "raid":
                location.progress_type = LocationProgressType.EXCLUDED
                location.item_rule = lambda item: item.classification == ItemClassification.filler
            region.locations.append(location)
        victory = WoWLocation(self.player, "Reach Level 80", None, menu)
        victory.access_rule = self.access_rule((80, (), ()))
        victory.place_locked_item(WoWItem("Level 80 Victory", ItemClassification.progression, None, self.player))
        menu.locations.append(victory)

    def create_item(self, name):
        definition = ITEM_DEFINITIONS[name]
        classification = ItemClassification[definition["classification"]]
        if definition["kind"] == "riding" and definition["value"] in RIDING_NAMES:
            classification = (ItemClassification.progression if definition["value"] in self.progression_riding
                              else ItemClassification.useful)
        return WoWItem(name, classification, definition["ap_id"], self.player)

    def get_filler_item_name(self):
        return "Gold Cache" if self.random.randrange(172) < 100 else "Consumable Cache"

    def create_items(self):
        counts = Counter({reward["name"]: reward["base_count"] for reward in REWARDS
                          if reward["classification"] != "filler"})
        counts.update(ability["name"] for ability in self.abilities)
        counts.update(legendary_name(item) for item in self.legendaries)
        # Account for ordinary locked/prefilled items without counting the victory event.
        prefilled = [location for location in self.multiworld.get_locations(self.player)
                     if location.address is not None and location.item is not None]
        for location in prefilled:
            if location.item.player == self.player and counts[location.item.name]:
                counts[location.item.name] -= 1
        locations = self.multiworld.get_unfilled_locations(self.player)
        needed = sum(counts.values())
        nonraid = sum(check["kind"] != "raid" for check in self.selected_checks
                      if self.multiworld.get_location(check["name"], self.player).item is None)
        if needed > len(locations) or needed > nonraid:
            raise ValueError(f"Selected profile/categories leave {len(locations)} item locations ({nonraid} non-raid), "
                             f"but {needed} fixed progression/useful rewards are required. Enable more check categories "
                             "or reduce legendary_count; useful rewards are never silently dropped and raids are filler-only.")
        filler = len(locations) - needed
        gold = (filler * 100 + 86) // 172
        counts.update({"Gold Cache": gold, "Consumable Cache": filler - gold})
        self.pool_counts = dict(counts)
        self.multiworld.itempool.extend(self.create_item(name) for name, count in counts.items() for _ in range(count))

    def set_rules(self):
        self.multiworld.completion_condition[self.player] = lambda state: state.has("Level 80 Victory", self.player)

    def fill_slot_data(self):
        # This is a server-side allowlist, not permission for a client to invent rewards.
        reward_names = {reward["name"] for reward in REWARDS} | {ability["name"] for ability in self.abilities} | {
            legendary_name(item) for item in self.legendaries}
        rewards = {str(ITEM_DEFINITIONS[name]["ap_id"]): {
            "kind": ITEM_DEFINITIONS[name]["kind"], "value": ITEM_DEFINITIONS[name]["value"]}
            for name in sorted(reward_names)}
        return {"protocol_version": 2, "catalog_version": CATALOG_VERSION, "catalog_schema_version": SCHEMA_VERSION,
            "seed_name": self.multiworld.seed_name, "slot": self.player,
            "items_handling": 7, "profile": self.profile, "selected_checks": self.selected_checks,
            "rewards": rewards, "merchant": self.merchant,
            "legendary_ids": [item["wow_id"] for item in self.legendaries],
            "options": {name: getattr(self.options, name).value for name in (
                "character_race", "character_class", *CATEGORY_OPTIONS.values(), "merchant_stock", "featured_sets",
                "set_piece_probability", "legendary_count", "progression_balancing", "accessibility")},
            "rules": {"starting_level": 1, "starting_cap": 10, "maximum_level": 80,
                "victory": "server_confirmed_level_80", "victory_requires_expansions": False,
                "raid_items": "filler_only", "equipment_level_bypass": "authorized_item_guid_only",
                "talent_reservation_levels": list(range(15, 71, 5)), "xp_bank_next_level_percent": 50,
                "expert_includes_prerequisite_training": True,
                "check_requirements": {check["key"]: {"min_cap": self.requirements[check["key"]][0],
                    "expansions": list(self.requirements[check["key"]][1]),
                    "riding": list(self.requirements[check["key"]][2])} for check in self.selected_checks}}}

    def write_spoiler(self, spoiler_handle):
        spoiler_handle.write(f"\nPersonal merchant and legendaries ({self.multiworld.player_name[self.player]}):\n")
        for item in self.legendaries:
            spoiler_handle.write(f"  Legendary: {item['name']} ({item['wow_id']})\n")
        from .catalog import GEAR_BY_ID
        for entry in self.merchant["stock"]:
            spoiler_handle.write(f"  {GEAR_BY_ID[entry['wow_id']]['name']}: {entry['price']} vouchers\n")
        spoiler_handle.write(f"  Total shop cost: {self.merchant['total_cost']}; voucher supply: 204\n")
