"""Personal stock is a pure function of seed, slot, profile, options and catalog.

Featured pieces roll independently *before* the inventory cap. If rolls overflow,
random.sample takes a uniform subset of those pieces; no set/order gets priority.
Coverage is best-effort after reservations, never a reason to erase a rolled piece.
"""
import hashlib
from random import Random

from .catalog import GEAR, GEAR_BY_ID, SETS, compatible, viable_roles

VOUCHER_ITEMS = 45 + 28 + 15
VOUCHER_SUPPLY = 45 + 28 * 3 + 15 * 5
assert (VOUCHER_ITEMS, VOUCHER_SUPPLY) == (88, 204)


def personal_rng(seed, slot, purpose):
    digest = hashlib.sha256(f"wowpilago-v2:{seed}:{slot}:{purpose}".encode()).digest()
    return Random(int.from_bytes(digest, "big"))


def select_legendaries(seed, slot, class_id, count=2):
    candidates = sorted((item for item in GEAR if item["quality"] == 5 and compatible(item, class_id)),
                        key=lambda item: item["wow_id"])
    if count > len(candidates):
        raise ValueError(f"Class {class_id} has only {len(candidates)} compatible named legendaries; requested {count}")
    return personal_rng(seed, slot, "legendaries").sample(candidates, count)


def facets(item, class_id=None):
    roles = item["roles"] if class_id is None else viable_roles(item, class_id)
    # Shared stamina/resistance utility is useful, but is not specialization coverage.
    if class_id is not None and len(item["roles"]) == 5:
        roles = ()
    return {("slot", item["inventory_type"]), ("expansion", item["expansion"]),
            ("quality", item["quality"])} | {
        ("role", role) for role in roles}


def generate_stock(seed, slot, class_id, size=60, featured_count=3, probability=80):
    if not 30 <= size <= 120 or not 1 <= featured_count <= 4 or not 0 <= probability <= 100:
        raise ValueError("Invalid merchant stock, featured set count, or piece probability")
    rng = personal_rng(seed, slot, "merchant")
    candidates = sorted((item for item in GEAR if item["quality"] != 5
                         and compatible(item, class_id) and viable_roles(item, class_id)),
                        key=lambda item: item["wow_id"])
    available = {item["wow_id"] for item in candidates}
    sets = sorted((entry for entry in SETS if class_id in entry["class_ids"]
                   and entry["pieces"] and set(entry["pieces"]) <= available), key=lambda entry: entry["wow_id"])
    if len(candidates) < size:
        raise ValueError(f"Class {class_id} has {len(candidates)} compatible vendor entries; requested {size}")
    if len(sets) < featured_count:
        raise ValueError(f"Class {class_id} has {len(sets)} compatible complete set catalogs; requested {featured_count}")
    featured = rng.sample(sets, featured_count)
    rolled = []
    included = set()
    for entry in featured:
        pieces = [piece for piece in sorted(entry["pieces"]) if rng.randrange(100) < probability]
        included.update(pieces)
        rolled.append({"set_id": entry["wow_id"], "pieces": sorted(entry["pieces"]), "rolled_pieces": pieces})
    reserved = sorted(included)
    overflow = max(0, len(reserved) - size)
    chosen = rng.sample(reserved, size) if overflow else reserved
    chosen_ids = set(chosen)
    covered = set().union(*(facets(GEAR_BY_ID[piece], class_id) for piece in chosen)) if chosen else set()
    featured_pieces = {piece for entry in featured for piece in entry["pieces"]}
    remaining = [item for item in candidates if item["wow_id"] not in chosen_ids | featured_pieces]
    if len(chosen) + len(remaining) < size:
        raise ValueError(f"Class {class_id} cannot fill stock {size} without undoing independent featured-piece rolls")
    # Random ties avoid catalog-order bias while covering viable roles, slots and eras.
    rng.shuffle(remaining)
    remaining_facets = {item["wow_id"]: facets(item, class_id) for item in remaining}
    all_facets = set().union(*remaining_facets.values())
    while len(chosen) < size and not all_facets <= covered:
        best = max(range(len(remaining)), key=lambda i: len(remaining_facets[remaining[i]["wow_id"]] - covered))
        item = remaining.pop(best)
        chosen.append(item["wow_id"])
        covered.update(remaining_facets[item["wow_id"]])
    # Keep affordable coverage, then favor upgrades so 204 vouchers is a real budget.
    remaining.sort(key=lambda item: item["quality"], reverse=True)
    chosen.extend(item["wow_id"] for item in remaining[:size - len(chosen)])
    rng.shuffle(chosen)
    stock = [{"wow_id": piece, "price": GEAR_BY_ID[piece]["price"], "max_purchases": 1} for piece in chosen]
    if any(not isinstance(entry["price"], int) or entry["price"] < 1 for entry in stock):
        raise ValueError("Catalog contains an invalid voucher price")
    return {"stock": stock, "featured_sets": rolled, "overflow": overflow,
            "overflow_policy": "uniform_sample_of_rolled_pieces",
            "total_cost": sum(entry["price"] for entry in stock), "voucher_supply": VOUCHER_SUPPLY}
