"""Load the same audited catalogs in source and zipped APWorld installations."""
from collections import Counter
import hashlib
import json
import pkgutil

SCHEMA_VERSION = 2
CHECK_BASES = dict(quest=919500000, level=919600000, exploration=919700000,
                   boss=919800000, dungeon=919900000, raid=920000000)
CHECK_COUNTS = dict(quest=150, exploration=60, boss=48, dungeon=14, level=16, raid=12)
SUPPORTED_CLASSES = frozenset({1, 2, 3, 4, 5, 7, 8, 9, 11})


def load_catalog(name):
    raw = pkgutil.get_data(__package__, f"data/{name}.json")
    if raw is None:
        raise ValueError(f"Missing authoritative catalog: {name}.json")
    data = json.loads(raw)
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{name}.json must use schema_version {SCHEMA_VERSION}")
    return data


DOCUMENTS = {name: load_catalog(name) for name in ("checks", "profiles", "gear", "abilities", "rewards")}
CHECKS = DOCUMENTS["checks"]["checks"]
PROFILES = DOCUMENTS["profiles"]["profiles"]
GEAR = DOCUMENTS["gear"]["items"]
CLASS_ROLES = {int(cls): frozenset(roles) for cls, roles in DOCUMENTS["gear"]["class_roles"].items()}
SETS = DOCUMENTS["gear"]["sets"]
ABILITIES = DOCUMENTS["abilities"]["abilities"]
REWARDS = DOCUMENTS["rewards"]["rewards"]
SEMANTIC_DOCUMENTS = {name: {key: value for key, value in document.items() if key != "provenance"}
                      for name, document in DOCUMENTS.items()}
CATALOG_VERSION = hashlib.sha256(json.dumps(SEMANTIC_DOCUMENTS, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def matches_profile(check, profile):
    return (check["faction"] in ("any", profile["faction"])
            and (not check["classes"] or profile["class_id"] in check["classes"])
            and (not check["races"] or profile["race_id"] in check["races"]))


def filter_profile(checks, profile):
    selected = {check["key"]: check for check in checks if matches_profile(check, profile)}
    while True:
        removed = [key for key, check in selected.items()
                   if any(parent not in selected for parent in check["prerequisites"])]
        if not removed:
            return list(selected.values())
        for key in removed:
            del selected[key]


def in_starting_region(check, profile):
    if check["kind"] == "level":
        return check["wow_id"] <= 10
    if check["kind"] == "exploration":
        return check["wow_id"] == profile["starting_zone"]
    return check["kind"] == "quest" and check.get("starting_zone") == profile["starting_zone"]


def compatible(item, class_id):
    # The catalog already intersects allowable_classes with armor/weapon proficiencies.
    return class_id in item["allowable_classes"]


def viable_roles(item, class_id):
    return CLASS_ROLES[class_id].intersection(item["roles"])


def validate_catalogs():
    from collections import Counter

    def unique(rows, field, label):
        values = [row[field] for row in rows]
        if len(values) != len(set(values)):
            raise ValueError(f"Duplicate {field} in {label}")

    if Counter(check["kind"] for check in CHECKS) != CHECK_COUNTS:
        raise ValueError("checks.json does not contain the required 300 curated definitions")
    for rows, field, label in ((CHECKS, "key", "checks"), (CHECKS, "ap_id", "checks"),
                                (CHECKS, "name", "checks"), (GEAR, "wow_id", "gear"),
                                (SETS, "wow_id", "sets")):
        unique(rows, field, label)
    keys = {check["key"] for check in CHECKS}
    for check in CHECKS:
        if check["ap_id"] != CHECK_BASES[check["kind"]] + check["wow_id"]:
            raise ValueError(f"Invalid check ID: {check['key']}")
        if not set(check["prerequisites"]) <= keys:
            raise ValueError(f"Unknown prerequisite: {check['key']}")
        if check["expansion"] not in {"azeroth", "outland", "northrend"} or check["riding"] not in {"none", "expert", "cold_weather"}:
            raise ValueError(f"Unknown access requirement: {check['key']}")
        if not 1 <= check["min_cap"] <= 80:
            raise ValueError(f"Invalid logical cap: {check['key']}")
    if set(CLASS_ROLES) != SUPPORTED_CLASSES or any(not roles or not roles <= {
            "caster", "healer", "melee", "tank", "ranged"} for roles in CLASS_ROLES.values()):
        raise ValueError("Invalid class role policy")
    gear_ids = {item["wow_id"] for item in GEAR}
    for featured in SETS:
        if not set(featured["pieces"]) <= gear_ids:
            raise ValueError(f"Missing set pieces: {featured['name']}")
    for ability in ABILITIES:
        if ability["class_id"] not in SUPPORTED_CLASSES or ability["ap_id"] != 919101000 + ability["base_spell"]:
            raise ValueError(f"Invalid shuffled ability: {ability['name']}")
    if any(count > 8 for count in Counter(a["class_id"] for a in ABILITIES).values()):
        raise ValueError("A class has more than eight shuffled major abilities")
    if any(profile["class_id"] not in SUPPORTED_CLASSES for profile in PROFILES):
        raise ValueError("profiles.json contains an unsupported class; DK is excluded in v1")


validate_catalogs()
CHECK_BY_KEY = {check["key"]: check for check in CHECKS}
GEAR_BY_ID = {item["wow_id"]: item for item in GEAR}
LEGENDARY_NAME_COUNTS = Counter(item["name"] for item in GEAR if item["quality"] == 5)


def legendary_name(item):
    # Atiesh variants and main/off-hand Warglaives share names but not identities.
    return f"{item['name']} [{item['wow_id']}]" if LEGENDARY_NAME_COUNTS[item["name"]] > 1 else item["name"]


ITEM_DEFINITIONS = {reward["name"]: dict(reward) for reward in REWARDS}
for ability in ABILITIES:
    ITEM_DEFINITIONS[ability["name"]] = dict(ap_id=ability["ap_id"], name=ability["name"],
        kind="ability", value=ability["base_spell"], classification="useful", base_count=1)
for item in GEAR:
    if item["quality"] == 5:
        ITEM_DEFINITIONS[legendary_name(item)] = dict(ap_id=919400000 + item["wow_id"], name=legendary_name(item),
            kind="legendary", value=item["wow_id"], classification="useful", base_count=1)
if len({item["ap_id"] for item in ITEM_DEFINITIONS.values()}) != len(ITEM_DEFINITIONS):
    raise ValueError("Reward AP IDs collide")
