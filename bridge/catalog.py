"""Validate protocol-2 slot data against the installed, authoritative catalogs."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "apworld" / "wowpilago" / "data"
CATEGORIES = {"quest": "quests", "exploration": "exploration", "boss": "dungeon_bosses",
              "dungeon": "dungeon_completions", "level": "level_milestones", "raid": "raids"}
RIDING = {"apprentice": 0, "journeyman": 1, "expert": 2, "artisan": 3, "cold_weather": 4}


class ProtocolError(ValueError):
    pass


def integer(value, name, minimum=0, maximum=2**32 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ProtocolError(f"Invalid {name}")
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def matches(check, profile):
    return (check["faction"] in ("any", profile["faction"])
            and (not check["classes"] or profile["class_id"] in check["classes"])
            and (not check["races"] or profile["race_id"] in check["races"]))


def filter_profile(checks, profile):
    selected = {check["key"]: check for check in checks if matches(check, profile)}
    while True:
        removed = [key for key, check in selected.items()
                   if any(parent not in selected for parent in check["prerequisites"])]
        if not removed:
            return list(selected.values())
        for key in removed:
            del selected[key]


@dataclass(frozen=True)
class Manifest:
    raw: dict
    checksum: str
    profile: dict
    rewards: dict
    checks: frozenset
    stock: tuple


def normalize_reward(reward):
    kind, value = reward["kind"], reward["value"]
    if kind == "expansion":
        return value, 1 if value == "outland" else 2
    if kind == "riding":
        return kind, RIDING[value]
    if kind == "voucher":
        return "vouchers", value
    if kind == "consumables":
        return "consumable", value
    if kind == "bag":
        return kind, 21841
    return kind, integer(value, "reward value")


class Catalog:
    def __init__(self, directory=DATA):
        self.documents = {name: json.loads((directory / f"{name}.json").read_text())
                          for name in ("checks", "profiles", "gear", "abilities", "rewards")}
        if any(document.get("schema_version") != 2 for document in self.documents.values()):
            raise ProtocolError("Catalog schema must be version 2")
        semantic = {name: {key: value for key, value in document.items() if key != "provenance"}
                    for name, document in self.documents.items()}
        self.version = digest(semantic)
        self.profiles = self.documents["profiles"]["profiles"]
        self.checks = self.documents["checks"]["checks"]
        self.gear = {item["wow_id"]: item for item in self.documents["gear"]["items"]}
        self.class_roles = {int(key): set(value) for key, value in self.documents["gear"]["class_roles"].items()}
        self.abilities = self.documents["abilities"]["abilities"]
        self.generic = self.documents["rewards"]["rewards"]
        self.definitions = {reward["ap_id"]: reward for reward in self.generic}
        for ability in self.abilities:
            self.definitions[ability["ap_id"]] = {"kind": "ability", "value": ability["base_spell"]}
        for item in self.gear.values():
            if item["quality"] == 5:
                self.definitions[919400000 + item["wow_id"]] = {"kind": "legendary", "value": item["wow_id"]}

    def parse(self, raw, seed, slot):
        if not isinstance(raw, dict) or raw.get("protocol_version") != 2:
            raise ProtocolError("Slot requires the full protocol-2 WoW world, not the retired potion world")
        if raw.get("catalog_schema_version") != 2 or raw.get("catalog_version") != self.version:
            raise ProtocolError("Installed catalogs differ from the generated slot. Install matching catalogs")
        if raw.get("seed_name") != seed or raw.get("slot") != slot or raw.get("items_handling") != 7:
            raise ProtocolError("Slot identity or item handling does not match the room")
        raw_profile = raw.get("profile")
        profile = next((profile for profile in self.profiles if canonical(profile) == canonical(raw_profile)), None)
        if profile is None:
            raise ProtocolError("Unsupported race/class profile. Death Knights are excluded")
        options = raw.get("options")
        if not isinstance(options, dict):
            raise ProtocolError("Missing slot options")
        for option in CATEGORIES.values():
            integer(options.get(option), option, 0, 1)
        size = integer(options.get("merchant_stock"), "merchant stock", 30, 120)
        featured_count = integer(options.get("featured_sets"), "featured sets", 1, 4)
        integer(options.get("set_piece_probability"), "set-piece probability", 0, 100)
        legendary_count = integer(options.get("legendary_count"), "legendary count", 0, 10)
        if (options.get("character_race"), options.get("character_class")) != (profile["race_id"], profile["class_id"]):
            raise ProtocolError("Profile options disagree with the selected character")
        selected = [check for check in filter_profile(self.checks, profile) if options[CATEGORIES[check["kind"]]]]
        if canonical(raw.get("selected_checks")) != canonical(selected):
            raise ProtocolError("Selected checks do not match the curated profile and options")
        rules = raw.get("rules", {})
        expected_rules = {"starting_level": 1, "starting_cap": 10, "maximum_level": 80,
                          "victory": "server_confirmed_level_80", "victory_requires_expansions": False,
                          "raid_items": "filler_only", "equipment_level_bypass": "authorized_item_guid_only",
                          "talent_reservation_levels": list(range(15, 71, 5)), "xp_bank_next_level_percent": 50}
        if any(rules.get(key) != value for key, value in expected_rules.items()):
            raise ProtocolError("Slot changes a required progression or victory rule")
        legends = raw.get("legendary_ids")
        if not isinstance(legends, list):
            raise ProtocolError("Invalid selected legendary identities")
        for entry in legends:
            integer(entry, "legendary entry", 1)
        if len(legends) != legendary_count or len(set(legends)) != len(legends):
            raise ProtocolError("Invalid selected legendary identities")
        for entry in legends:
            item = self.gear.get(integer(entry, "legendary entry", 1))
            if item is None or item["quality"] != 5 or profile["class_id"] not in item["allowable_classes"]:
                raise ProtocolError("Legendary is not compatible with this class")
        allowed = {reward["ap_id"] for reward in self.generic}
        allowed.update(ability["ap_id"] for ability in self.abilities if ability["class_id"] == profile["class_id"])
        allowed.update(919400000 + entry for entry in legends)
        expected_rewards = {str(code): {"kind": self.definitions[code]["kind"], "value": self.definitions[code]["value"]}
                            for code in sorted(allowed)}
        if canonical(raw.get("rewards")) != canonical(expected_rewards):
            raise ProtocolError("Reward allowlist differs from the class and selected legendaries")
        merchant = raw.get("merchant")
        if not isinstance(merchant, dict) or not isinstance(merchant.get("stock"), list) or len(merchant["stock"]) != size:
            raise ProtocolError("Invalid personal merchant stock size")
        stock = []
        seen = set()
        for index, entry in enumerate(merchant["stock"]):
            if not isinstance(entry, dict) or set(entry) != {"wow_id", "price", "max_purchases"}:
                raise ProtocolError("Invalid merchant stock entry")
            item_id = integer(entry["wow_id"], "stock item", 1)
            item = self.gear.get(item_id)
            if (item is None or item["quality"] == 5 or profile["class_id"] not in item["allowable_classes"]
                    or not self.class_roles[profile["class_id"]].intersection(item["roles"])
                    or item_id in seen or entry["price"] != item["price"] or entry["max_purchases"] != 1):
                raise ProtocolError("Merchant item, price, class, or duplicate is invalid")
            integer(entry["price"], "voucher price", 1, 8)
            integer(entry["max_purchases"], "purchase limit", 1, 1)
            seen.add(item_id)
            stock.append((index, item_id, entry["price"]))
        if merchant.get("total_cost") != sum(row[2] for row in stock) or merchant.get("voucher_supply") != 204:
            raise ProtocolError("Merchant total or voucher supply is invalid")
        featured = merchant.get("featured_sets")
        sets = {entry["wow_id"]: entry for entry in self.documents["gear"]["sets"]}
        if not isinstance(featured, list) or len(featured) != featured_count:
            raise ProtocolError("Invalid featured set count")
        featured_ids = set()
        rolled = set()
        featured_pieces = set()
        for entry in featured:
            if not isinstance(entry, dict):
                raise ProtocolError("Invalid featured set")
            set_id = integer(entry.get("set_id"), "featured set", 1)
            original = sets.get(set_id)
            if (original is None or original["wow_id"] in featured_ids
                    or profile["class_id"] not in original["class_ids"]
                    or entry.get("pieces") != sorted(original["pieces"])
                    or not isinstance(entry.get("rolled_pieces"), list)
                    or not set(entry["rolled_pieces"]) <= set(original["pieces"])):
                raise ProtocolError("Featured set differs from the curated class set")
            if len(entry["rolled_pieces"]) != len(set(entry["rolled_pieces"])):
                raise ProtocolError("Duplicate featured piece roll")
            featured_ids.add(original["wow_id"])
            rolled.update(entry["rolled_pieces"])
            featured_pieces.update(original["pieces"])
        overflow = max(0, len(rolled) - size)
        if merchant.get("overflow") != overflow or merchant.get("overflow_policy") != "uniform_sample_of_rolled_pieces":
            raise ProtocolError("Featured-set overflow metadata is invalid")
        if (not overflow and seen & featured_pieces != rolled) or (overflow and not seen <= rolled):
            raise ProtocolError("Stock changes the independent featured-set rolls")
        return Manifest(raw, digest(raw), dict(profile),
                        {code: normalize_reward(self.definitions[code]) for code in allowed},
                        frozenset(check["ap_id"] for check in selected), tuple(stock))
