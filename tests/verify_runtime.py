"""Fabricated AP ingress for native smoke checks, never a real AP/release gate.

No arguments prints the plan without SQL, authentication, or socket access.
See docs/RUNTIME_SMOKE.md. This file deliberately does not import bridge.v2.session.
"""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.catalog import Catalog, filter_profile
from realm_client import RealmClient, Reader, ProtocolError, authenticate, create_character

MARKER = "wowpilago-fixture@invalid"
ACCOUNTS = tuple("APV2" + letter for letter in "ABCDEF")
PROTECTED = frozenset({1, 2, 3})
LABEL = "fabricated AP ingress; NOT real AP client, gameplay, or release-gate evidence"
PLAN = {
    "label": LABEL,
    "network_without_run": False,
    "endpoints": ["127.0.0.1:3724", "127.0.0.1:8085", "127.0.0.1:13317"],
    "targets": "APV2A..F, exact auth email marker, SEC_PLAYER, fresh human warrior only",
    "writes": "native character creation; Store.bind/receive on a fresh offline level-1 GUID only",
    "checks": ["cap/talent/ability/riding/vouchers/bag/legend receipts and authorization",
               "SEC_PLAYER status, denied remote purchase, authorized sword equip",
               "full logout save and relogin: progress, inventory, spells, talents, receipts",
               "--setup: fresh TEST GM character, native level/quest XP bank and cap release"],
    "remaining_live_gates": ["nearby merchant positive purchase and replay/debit/equip",
                             "talent spending and eligible riding learning",
                             "real AP room ingress and normal gameplay/playthrough"],
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def guard_account(row, account, *, setup=False):
    require(row is not None and row["username"] == account, "Account missing or mismatched")
    if setup:
        require(account == "TEST" and row["security"] == 3, "Setup requires existing TEST GM3")
    else:
        require(account in ACCOUNTS and row["email"] == MARKER and row["security"] == 0,
                "Refusing unmarked or privileged fixture account")
    require(row["online"] == 0, "Account already online")


def guard_character(row, account_id, name, known, *, expected_profile=None):
    profile = expected_profile or {"race_id": 1, "class_id": 1}
    require(type(profile["race_id"]) is int and type(profile["class_id"]) is int,
            "Invalid expected profile")
    require(row is not None and row["guid"] not in PROTECTED and row["guid"] in known,
            "Refusing protected or not-known-created GUID")
    require(row["account"] == account_id and row["name"] == name
            and row["race"] == profile["race_id"] and row["class"] == profile["class_id"],
            "Character ownership/profile mismatch")


def say_packet(text):
    require(isinstance(text, str) and text.startswith(".") and "\0" not in text
            and "\n" not in text and len(text) < 255, "Invalid command")
    return struct.pack("<II", 1, 7) + text.encode("ascii") + b"\0"  # CHAT_MSG_SAY, Common


def selection_packet(guid):
    require(type(guid) is int and guid > 3 and guid < 2**32, "Unsafe player selection")
    return struct.pack("<Q", guid)


def system_chat(data):
    r = Reader(data)
    kind, language = r.unpack("BI")
    if kind != 0:  # CHAT_MSG_SYSTEM only, no monster/channel variable layouts
        return None
    _, _, _, size = r.unpack("QIQI")
    message = r.take(size)
    r.take(1)
    r.finish()
    require(language == 0 and message.endswith(b"\0"), "Invalid system chat")
    return message[:-1].decode("utf-8", "strict")


def initial_spells(data):
    r = Reader(data)
    r.take(1)
    count, = r.unpack("H")
    spells = {r.unpack("IH")[0] for _ in range(count)}
    cooldowns, = r.unpack("H")
    r.take(cooldowns * 16)  # uint32 spell, uint16 item/category, uint32 x2 time
    r.finish()
    return spells


class SmokeClient(RealmClient):
    """Keep the parent's protocol implementation; capture only smoke evidence."""

    def __init__(self, sock, authorize_login):
        self.messages = []
        self.events = []
        self.spells = None
        self.talent_points = None
        self.authorize_login = authorize_login
        super().__init__(sock, emit=self.events.append)

    def send(self, opcode, payload=b""):
        if opcode == 0x3D:
            guid, = struct.unpack("<Q", payload)
            self.authorize_login(guid, self.events)
        super().send(opcode, payload)

    def process(self, opcode, payload):
        if opcode == 0x96:
            message = system_chat(payload)
            if message is not None:
                self.messages.append(message)
                return
        elif opcode == 0x12A:
            self.spells = initial_spells(payload)
        elif opcode == 0x4C0 and payload and payload[0] == 0:
            # Player::BuildPlayerTalentsInfoData starts with uint32 free points.
            require(len(payload) >= 7, "Truncated player talent packet")
            self.talent_points, = struct.unpack_from("<I", payload, 1)
        super().process(opcode, payload)

    def command(self, text):
        start = len(self.messages)
        self.send(0x95, say_packet(text))
        self.stay(0.5)
        return self.messages[start:]


def manifest_fixture(catalog, seed):
    profile = next(p for p in catalog.profiles if p["race_id"] == p["class_id"] == 1)
    featured = next(s for s in catalog.documents["gear"]["sets"] if 1 in s["class_ids"])
    stock = [{"wow_id": g["wow_id"], "price": g["price"], "max_purchases": 1}
             for g in sorted(catalog.gear.values(), key=lambda g: g["wow_id"])
             if g["quality"] != 5 and 1 in g["allowable_classes"]
             and catalog.class_roles[1].intersection(g["roles"])
             and g["wow_id"] not in featured["pieces"]][:30]
    codes = {r["ap_id"] for r in catalog.generic}
    codes.update(a["ap_id"] for a in catalog.abilities if a["class_id"] == 1)
    codes.add(919419019)  # Thunderfury, human warrior one-handed sword proficiency
    raw = {
        "protocol_version": 2, "catalog_schema_version": 2, "catalog_version": catalog.version,
        "seed_name": seed, "slot": 1, "items_handling": 7, "profile": profile,
        "options": {"character_race": 1, "character_class": 1, "quests": 1, "exploration": 1,
                    "dungeon_bosses": 1, "dungeon_completions": 1, "level_milestones": 1, "raids": 1,
                    "merchant_stock": 30, "featured_sets": 1, "set_piece_probability": 0, "legendary_count": 1},
        "selected_checks": filter_profile(catalog.checks, profile),
        "rewards": {str(code): catalog.definitions[code] for code in sorted(codes)},
        "legendary_ids": [19019],
        "merchant": {"stock": stock, "total_cost": sum(g["price"] for g in stock), "voucher_supply": 204,
                     "featured_sets": [{"set_id": featured["wow_id"], "pieces": sorted(featured["pieces"]),
                                        "rolled_pieces": []}],
                     "overflow": 0, "overflow_policy": "uniform_sample_of_rolled_pieces"},
        "rules": {"starting_level": 1, "starting_cap": 10, "maximum_level": 80,
                  "victory": "server_confirmed_level_80", "victory_requires_expansions": False,
                  "raid_items": "filler_only", "equipment_level_bypass": "authorized_item_guid_only",
                  "talent_reservation_levels": list(range(15, 71, 5)), "xp_bank_next_level_percent": 50},
    }
    # Generic definitions have extra catalog keys. Only kind/value belong on the wire.
    raw["rewards"] = {code: {"kind": r["kind"], "value": r["value"]} for code, r in raw["rewards"].items()}
    catalog.parse(raw, seed, 1)
    return raw


REWARDS = (919100001, 919100020, 919101100, 919100010, 919100033, 919100040, 919419019)


def bank_setup_commands(name):
    create_character(name, race=1, class_id=1)
    return (".learn 100", ".levelup " + name + " 9",
            ".quest add 783 " + name, ".quest complete 783 " + name, ".quest reward 783 " + name)


def network_items():
    return [{"class": "NetworkItem", "item": code, "location": -1, "player": 0, "flags": 0}
            for code in REWARDS]


class Runner:
    def __init__(self, db, account):
        self.db, self.account = db, account
        self.known = set()
        self.before = {r["guid"] for r in self.query("SELECT guid FROM acore_characters.characters")}
        self.names = {}

    def query(self, sql, args=()):
        # This connection is observation-only. Store owns the only SQL writes.
        require(sql.startswith("SELECT ") and ";" not in sql, "Only SELECT permitted")
        with self.db.cursor() as cursor:
            cursor.execute(sql, args)
            return list(cursor.fetchall())

    def account_row(self, account):
        rows = self.query("SELECT a.id,a.username,a.email,a.online,COALESCE(MAX(x.gmlevel),0) AS security "
                          "FROM acore_auth.account a LEFT JOIN acore_auth.account_access x ON x.id=a.id "
                          "WHERE a.username=%s GROUP BY a.id", (account,))
        return rows[0] if rows else None

    def character(self, guid):
        rows = self.query("SELECT * FROM acore_characters.characters WHERE guid=%s", (guid,))
        return rows[0] if rows else None

    def offline(self, guid):
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            row = self.character(guid)
            if row is not None and row["online"] == 0:
                accounts = self.query("SELECT online FROM acore_auth.account WHERE id=%s", (row["account"],))
                if len(accounts) == 1 and accounts[0]["online"] == 0:
                    return row
            time.sleep(0.2)
        raise RuntimeError("Character did not become offline; no SQL fallback")

    @contextmanager
    def login(self, account, *, guid=None, expected_profile=None):
        profile = expected_profile or {"race_id": 1, "class_id": 1}
        setup = account == "TEST"
        require(not setup or profile["race_id"] == profile["class_id"] == 1,
                "TEST control must remain Human Warrior")
        row = self.account_row(account)
        guard_account(row, account, setup=setup)
        if guid is None:
            name = "Aps" + "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(9))
            require(not self.query("SELECT guid FROM acore_characters.characters WHERE name=%s", (name,)),
                    "Generated name already exists")
        else:
            name = self.names[guid]
            guard_character(self.character(guid), row["id"], name, self.known, expected_profile=profile)

        cleanup_guid = guid

        def authorize(candidate, events):
            nonlocal cleanup_guid
            if guid is None:
                require(candidate not in self.before and "CREATED " + name in events,
                        "Refusing preexisting character login")
                self.known.add(candidate)
                self.names[candidate] = name
            else:
                require(candidate == guid, "Relogin GUID changed")
            guard_character(self.character(candidate), row["id"], name, self.known, expected_profile=profile)
            cleanup_guid = candidate

        auth = authenticate(account, os.environ["WOWPILAGO_TEST_ACCOUNT_PASSWORD"] if not setup else "TEST",
                            ready_timeout=45)
        realm = next((r for r in auth.realms if not r.locked and not r.flags & 3), None)
        require(realm is not None, "No ready unlocked realm")
        try:
            with socket.create_connection(("127.0.0.1", 8085), timeout=10) as sock:
                client = getattr(self, 'client_type', SmokeClient)(sock, authorize)
                try:
                    chosen = client.connect(account, auth, realm, name,
                                            race=profile['race_id'], class_id=profile['class_id'])
                    client.stay(2)
                    yield client, chosen.guid
                finally:
                    if client.login:
                        client.logout()
        finally:
            if cleanup_guid is not None:
                self.offline(cleanup_guid)

    def snapshot(self, guid, binding):
        guard_character(self.character(guid), self.account_row(self.account)["id"], self.names[guid], self.known)
        return {
            "character": self.query("SELECT level,xp,money FROM acore_characters.characters WHERE guid=%s", (guid,)),
            "progress": self.query("SELECT * FROM acore_characters.mod_archipelago_progress WHERE binding_id=%s", (binding,)),
            "rewards": self.query("SELECT * FROM acore_characters.mod_archipelago_reward WHERE binding_id=%s ORDER BY item_index", (binding,)),
            "inventory": self.query("SELECT bag,slot,item FROM acore_characters.character_inventory WHERE guid=%s ORDER BY bag,slot", (guid,)),
            "items": self.query("SELECT i.* FROM acore_characters.item_instance i JOIN acore_characters.character_inventory v ON v.item=i.guid WHERE v.guid=%s ORDER BY i.guid", (guid,)),
            "abilities": self.query("SELECT base_spell FROM acore_characters.mod_archipelago_ability WHERE binding_id=%s ORDER BY base_spell", (binding,)),
            "purchases": self.query("SELECT * FROM acore_characters.mod_archipelago_purchase WHERE binding_id=%s ORDER BY stock_index", (binding,)),
            "stock": self.query("SELECT * FROM acore_characters.mod_archipelago_stock WHERE binding_id=%s ORDER BY stock_index", (binding,)),
            "authorized": self.query("SELECT * FROM acore_characters.mod_archipelago_authorized_item WHERE binding_id=%s ORDER BY item_guid", (binding,)),
            "spells": self.query("SELECT spell,specMask FROM acore_characters.character_spell WHERE guid=%s ORDER BY spell", (guid,)),
        }

    def execute(self, setup):
        from bridge.v2 import Store  # No websocket client is called.
        catalog = Catalog()
        seed = "fabricated-native-smoke-" + secrets.token_hex(12)
        raw = manifest_fixture(catalog, seed)
        with self.login(self.account) as (_, guid):
            print(json.dumps({"created_guid": guid, "name": self.names[guid], "seed": seed, "label": LABEL}), flush=True)
        row = self.offline(guid)
        account = self.account_row(self.account)
        guard_account(account, self.account)
        guard_character(row, account["id"], self.names[guid], self.known)
        require(row["level"] == 1, "Fresh character is not level 1")
        require(not self.query("SELECT id FROM acore_characters.mod_archipelago_binding WHERE character_guid=%s", (guid,)),
                "Fresh character unexpectedly has binding; do not clear indexes")
        store = Store(dict(host="127.0.0.1", port=13317, user="root", database="acore_characters"), guid, catalog)
        try:
            binding = store.bind(seed, 0, 1, raw)
            store.status("disconnected")  # Fabricated ingress has no live AP bridge session.
            bank = 0
            if setup:
                with self.login(self.account, guid=guid) as (player, _), self.login("TEST") as (gm, _):
                    gm.send(0x13D, selection_packet(guid))
                    for command in bank_setup_commands(self.names[guid]):
                        gm.command(command)
                    player.stay(2)
                before = self.snapshot(guid, binding)
                require(before["character"][0]["level"] == 10, "Native setup did not reach cap 10")
                require(100 not in {r["spell"] for r in before["spells"]}, "Locked ability learned without permission")
                bank = before["progress"][0]["banked_xp"]
                require(bank > 0, "Quest setup did not bank XP; native bank gate failed")
            guard_character(self.offline(guid), account["id"], self.names[guid], self.known)
            guard_account(self.account_row(self.account), self.account)
            require(store.receive(0, network_items()), "Fixture queue rejected")
            with self.login(self.account, guid=guid) as (player, _):
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    pending = self.query("SELECT COUNT(*) AS n FROM acore_characters.mod_archipelago_reward WHERE binding_id=%s AND applied=0", (binding,))[0]["n"]
                    if not pending:
                        break
                    player.stay(0.5)
                require(pending == 0, "Native callback delivery timeout, pending receipts remain")
                messages = player.command(".archipelago status")
                require(any("cap 20" in m for m in messages), "Live status did not publish cap 20")
                player.send(0x13D, struct.pack("<Q", 0))
                messages = player.command(".archipelago buy 0")
                require(any("Select a nearby Archipelago merchant" in m for m in messages), "Remote purchase was not denied")
                legend = self.query("SELECT item_guid FROM acore_characters.mod_archipelago_authorized_item WHERE binding_id=%s AND item_entry=19019", (binding,))
                require(len(legend) == 1, "Legend authorization missing")
                player.command(".archipelago equip " + str(legend[0]["item_guid"]) + " 15")
                if setup:
                    with self.login("TEST") as (gm, _):
                        gm.send(0x13D, selection_packet(guid))
                        gm.command(".learn 100")
                        gm.command(".learn 33388")  # Received but below level 20.
                    player.stay(1)
            saved = self.snapshot(guid, binding)
            progress = saved["progress"][0]
            require((progress["cap_items"], progress["talent_unlocks"], progress["riding_flags"], progress["vouchers"]) == (1, 1, 1, 5), "Progress effects differ")
            require(progress["banked_xp"] == 0 and len(saved["rewards"]) == len(REWARDS), "Bank/receipt count differs")
            require([r["ap_item"] for r in saved["rewards"]] == list(REWARDS)
                    and all(r["applied"] == 1 for r in saved["rewards"]), "Receipt identity/application differs")
            require(saved["abilities"] == [{"base_spell": 100}], "Ability permission missing")
            require(not saved["purchases"] and not any(r["sold"] for r in saved["stock"]), "Denied purchase changed stock")
            bag_receipt = saved["rewards"][5]
            require(any(i["guid"] == bag_receipt["item_guid"] and i["itemEntry"] == 21841
                        and i["owner_guid"] == guid and i["count"] == 1 for i in saved["items"]), "Bag receipt has no owned physical item")
            require(any(i["guid"] == legend[0]["item_guid"] and i["itemEntry"] == 19019
                        and i["owner_guid"] == guid and i["count"] == 1
                        and i["flags"] & 1 and not i["flags"] & (256 | 4096) for i in saved["items"]), "Legend instance or binding flags differ")
            if setup:
                xp_rows = self.query("SELECT Experience FROM acore_world.player_xp_for_level WHERE Level=10")
                require(len(xp_rows) == 1 and xp_rows[0]["Experience"] > 0, "Missing pinned level-10 XP row")
                character = saved["character"][0]
                require((character["level"], character["xp"]) == (10, min(bank, xp_rows[0]["Experience"] // 2)),
                        "Cap receipt failed exact bank release without level gain")
                require(100 in {r["spell"] for r in saved["spells"]} and 33388 not in {r["spell"] for r in saved["spells"]}, "Ability/riding level gates differ")
            require(any(r["slot"] == 15 and r["bag"] == 0 and r["item"] == legend[0]["item_guid"] for r in saved["inventory"]), "Native equip did not save to main hand")
            require(store.receive(0, network_items()), "Identical queue replay rejected")
            with self.login(self.account, guid=guid) as (player, _):
                player.stay(2)
                require(player.spells is not None and player.talent_points == (1 if setup else 0), "Relogin spell/talent packets absent or wrong")
                require((100 in player.spells) == setup and 33388 not in player.spells, "Relogin spell state differs")
            require(saved == self.snapshot(guid, binding), "Full save/relogin/replay changed durable effects")
            print(json.dumps({"result": "PASS bounded native smoke", "label": LABEL, "guid": guid,
                              "binding": binding, "bank_setup": setup,
                              "remaining_live_gates": PLAN["remaining_live_gates"] +
                              ([] if setup else ["XP bank release and ability learning require --setup"])}), flush=True)
        finally:
            store.close()  # Preserve bindings, receipts, queues and all created characters.


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--account", choices=ACCOUNTS, default="APV2A")
    parser.add_argument("--setup", action="store_true", help="fresh TEST GM setup character for native bank/learn checks")
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(PLAN, indent=2))
        return 0
    require(os.environ.get("WOWPILAGO_TEST_ACCOUNT_PASSWORD") == "test-only", "Set WOWPILAGO_TEST_ACCOUNT_PASSWORD=test-only")
    require(bool(os.environ.get("WOWPILAGO_DB_PASSWORD")), "Set WOWPILAGO_DB_PASSWORD")
    # Fail before any SQL writes or character creation if either server is not listening.
    for port in (3724, 8085):
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            pass
    import pymysql
    with pymysql.connect(host="127.0.0.1", port=13317, user="root", password=os.environ["WOWPILAGO_DB_PASSWORD"],
                         autocommit=True, cursorclass=pymysql.cursors.DictCursor,
                         connect_timeout=5, read_timeout=15, write_timeout=15) as db:
        Runner(db, args.account).execute(args.setup)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ProtocolError, OSError, ValueError, struct.error) as exc:
        print("FAIL: " + str(exc) + "; fixtures/history preserved, no SQL repair attempted", file=sys.stderr)
        sys.exit(1)
