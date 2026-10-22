"""Durable protocol-2 character binding, received rewards, and check outbox."""

import asyncio
import json
import logging
import os
import uuid

import pymysql
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from bridge.catalog import Catalog, ProtocolError, canonical, integer

LOG = logging.getLogger("wowpilago")
GAME = "World of Warcraft"


class Store:
    def __init__(self, database, guid, catalog=None):
        self.guid = integer(guid, "character GUID", 1)
        self.catalog = catalog if catalog is not None else Catalog()
        self.binding = None
        self.manifest = None
        self.db = pymysql.connect(**database, password=os.environ.get("WOWPILAGO_DB_PASSWORD", ""),
            charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, autocommit=True,
            connect_timeout=10, read_timeout=15, write_timeout=15)
        try:
            with self.db.cursor() as cursor:
                lock = uuid.uuid5(uuid.NAMESPACE_URL, f"{database['database']}:{guid}")
                cursor.execute("SELECT GET_LOCK(%s,0) AS owned", (f"wowpilago:{lock}",))
                if cursor.fetchone()["owned"] != 1:
                    raise ProtocolError("Another bridge owns this character")
                cursor.execute("SELECT guid FROM characters WHERE guid=%s AND account<>0", (guid,))
                if cursor.fetchone() is None:
                    raise ProtocolError("The character does not exist or was deleted")
        except Exception:
            self.db.close()
            raise

    def bind(self, seed, team, slot, raw):
        integer(team, "team")
        integer(slot, "slot", 1)
        if not isinstance(seed, str) or not 1 <= len(seed) <= 255:
            raise ProtocolError("Invalid seed name")
        manifest = self.catalog.parse(raw, seed, slot)
        profile = manifest.profile
        self.db.begin()
        try:
            with self.db.cursor() as cursor:
                cursor.execute("SELECT guid,name,account,level,`class`,race,online FROM characters WHERE guid=%s FOR SHARE", (self.guid,))
                character = cursor.fetchone()
                if character is None or not character["account"]:
                    raise ProtocolError("Character was deleted")
                if (character["class"], character["race"]) != (profile["class_id"], profile["race_id"]):
                    raise ProtocolError("Character race/class differs from the generated slot")
                cursor.execute("SELECT * FROM mod_archipelago_binding WHERE character_guid=%s FOR UPDATE", (self.guid,))
                existing = cursor.fetchone()
                if existing:
                    if (existing["seed_name"], existing["team"], existing["slot"], existing["protocol_version"],
                        existing["manifest_hash"], existing["character_account"]) != (
                        seed, team, slot, 2, manifest.checksum, character["account"]):
                        raise ProtocolError("Character is already bound to another seed, slot, account, or immutable manifest")
                    binding = existing["id"]
                    cursor.execute("SELECT binding_id FROM mod_archipelago_progress WHERE binding_id=%s", (binding,))
                    if cursor.fetchone() is None:
                        raise ProtocolError("Binding has no progression state. Restore its backup; do not reset receipts")
                else:
                    if character["level"] != 1 or character["online"]:
                        raise ProtocolError("A first binding requires an offline level-1 character")
                    cursor.execute("INSERT INTO mod_archipelago_binding "
                        "(character_guid,character_name,character_account,seed_name,team,slot,class_id,race_id,faction,manifest_hash,manifest) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (self.guid, character["name"], character["account"], seed, team, slot, profile["class_id"],
                         profile["race_id"], profile["faction"], manifest.checksum, canonical(raw)))
                    binding = cursor.lastrowid
                    cursor.execute("INSERT INTO mod_archipelago_progress (binding_id) VALUES (%s)", (binding,))
                    cursor.executemany("INSERT INTO mod_archipelago_enabled_check (binding_id,location_id) VALUES (%s,%s)",
                                       [(binding, location) for location in sorted(manifest.checks)])
                    cursor.executemany("INSERT INTO mod_archipelago_allowed_reward (binding_id,ap_item) VALUES (%s,%s)",
                                       [(binding, code) for code in sorted(manifest.rewards)])
                    cursor.executemany("INSERT INTO mod_archipelago_stock (binding_id,stock_index,item_entry,price) VALUES (%s,%s,%s,%s)",
                                       [(binding, *entry) for entry in manifest.stock])
                cursor.execute("UPDATE mod_archipelago_binding SET character_name=%s,status='connected',heartbeat=CURRENT_TIMESTAMP WHERE id=%s",
                               (character["name"], binding))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.binding, self.manifest = binding, manifest
        return binding

    def ensure_active(self):
        if self.binding is None:
            raise ProtocolError("Binding is not authenticated")
        with self.db.cursor() as cursor:
            cursor.execute("SELECT b.character_guid,c.account FROM mod_archipelago_binding b "
                           "JOIN characters c ON c.guid=b.character_guid WHERE b.id=%s AND b.status<>'archived'", (self.binding,))
            row = cursor.fetchone()
        if row is None or row["character_guid"] != self.guid or not row["account"]:
            raise ProtocolError("Character was deleted or its binding was archived")

    def status(self, value):
        if self.binding is None:
            return
        if value not in {"connected", "disconnected"}:
            raise ValueError("Invalid bridge connection status")
        with self.db.cursor() as cursor:
            cursor.execute("UPDATE mod_archipelago_binding SET status=IF(character_guid IS NULL,'archived',%s),"
                           "heartbeat=CURRENT_TIMESTAMP WHERE id=%s AND status<>'archived'", (value, self.binding))

    def receive(self, start, items):
        self.ensure_active()
        integer(start, "received item index")
        if not isinstance(items, list):
            raise ProtocolError("ReceivedItems must contain a list")
        parsed = []
        for offset, item in enumerate(items):
            if not isinstance(item, dict) or item.get("class") != "NetworkItem":
                raise ProtocolError("Invalid NetworkItem")
            code = integer(item.get("item"), "AP item", -(2**63), 2**63 - 1)
            effect = self.manifest.rewards.get(code)
            if effect is None:
                raise ProtocolError(f"Reward {code} is not in this slot's allowlist")
            location = integer(item.get("location"), "source location", -(2**63), 2**63 - 1)
            sender = integer(item.get("player"), "sender")
            flags = integer(item.get("flags"), "flags", 0, 7)
            parsed.append((integer(start + offset, "item index"), code, location, sender, flags, *effect))
        self.db.begin()
        try:
            with self.db.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS n,COALESCE(MAX(item_index)+1,0) AS next_index "
                               "FROM mod_archipelago_reward WHERE binding_id=%s", (self.binding,))
                row = cursor.fetchone()
                expected = row["next_index"]
                if row["n"] != expected:
                    raise ProtocolError("Stored reward history has a gap. Restore its backup")
                if start > expected:
                    self.db.rollback()
                    return False
                if start == 0 and len(parsed) < expected:
                    raise ProtocolError("Server reward history is shorter than the durable local history")
                for index, code, location, sender, flags, kind, value in parsed:
                    cursor.execute("SELECT ap_item,location_id,sender,flags,kind,value FROM mod_archipelago_reward "
                                   "WHERE binding_id=%s AND item_index=%s", (self.binding, index))
                    previous = cursor.fetchone()
                    values = (code, location, sender, flags, kind, value)
                    if previous is not None:
                        if tuple(previous[key] for key in ("ap_item", "location_id", "sender", "flags", "kind", "value")) != values:
                            raise ProtocolError("Replayed reward differs from the durable history")
                    else:
                        cursor.execute("INSERT INTO mod_archipelago_reward "
                            "(binding_id,item_index,ap_item,location_id,sender,flags,kind,value) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                            (self.binding, index, *values))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return True

    def checked(self, locations, *, reset=False):
        self.ensure_active()
        if not isinstance(locations, list):
            raise ProtocolError("Checked locations must be a list")
        values = {integer(location, "checked location", 1, 2**63 - 1) for location in locations}
        if not values <= self.manifest.checks:
            raise ProtocolError("AP server acknowledged locations outside the selected catalog")
        self.db.begin()
        try:
            with self.db.cursor() as cursor:
                if reset:
                    cursor.execute("UPDATE mod_archipelago_check SET acknowledged=0 WHERE binding_id=%s", (self.binding,))
                cursor.executemany("UPDATE mod_archipelago_check SET acknowledged=1 WHERE binding_id=%s AND location_id=%s",
                                   [(self.binding, location) for location in values])
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return values

    def pending_checks(self):
        self.ensure_active()
        with self.db.cursor() as cursor:
            cursor.execute("SELECT location_id FROM mod_archipelago_check WHERE binding_id=%s "
                           "AND acknowledged=0 ORDER BY location_id", (self.binding,))
            locations = [row["location_id"] for row in cursor.fetchall()]
        if not set(locations) <= self.manifest.checks:
            raise ProtocolError("Local outbox contains a location outside the seed")
        return locations

    def victory(self):
        self.ensure_active()
        with self.db.cursor() as cursor:
            cursor.execute("SELECT p.victory,p.last_level,c.level FROM mod_archipelago_progress p "
                           "JOIN mod_archipelago_binding b ON b.id=p.binding_id "
                           "JOIN characters c ON c.guid=b.character_guid WHERE p.binding_id=%s", (self.binding,))
            row = cursor.fetchone()
        return row is not None and row["victory"] == 1 and row["last_level"] == 80 and row["level"] == 80

    def close(self):
        if self.db.open:
            self.db.close()


async def send(socket, *commands):
    await socket.send(json.dumps(commands, allow_nan=False))


async def session(config, store):
    authenticated = False
    seed = None
    known_checks = set()
    goal_sent = False
    async with connect(config["server"], open_timeout=10, max_size=4 * 1024 * 1024) as socket:
        while True:
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=2)
            except TimeoutError:
                raw = "[]"
            packets = json.loads(raw)
            if not isinstance(packets, list):
                raise ProtocolError("Expected a packet list")
            for packet in packets:
                if not isinstance(packet, dict):
                    raise ProtocolError("Expected a packet object")
                command = packet.get("cmd")
                if command == "RoomInfo":
                    if seed is not None:
                        raise ProtocolError("Repeated room identity")
                    seed = packet.get("seed_name")
                    await send(socket, {"cmd": "Connect", "game": GAME, "name": config["slot"],
                        "password": os.environ.get("WOWPILAGO_AP_PASSWORD"),
                        "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"wowpilago-v2:{config['database']['database']}:{store.guid}")),
                        "version": {"major": 0, "minor": 6, "build": 8, "class": "Version"},
                        "items_handling": 7, "tags": [], "slot_data": True})
                elif command == "ConnectionRefused":
                    raise ProtocolError(f"Connection refused: {packet.get('errors', [])}")
                elif command == "Connected":
                    if authenticated or seed is None:
                        raise ProtocolError("Unexpected authentication result")
                    store.bind(seed, packet.get("team"), packet.get("slot"), packet.get("slot_data"))
                    known_checks = store.checked(packet.get("checked_locations"), reset=True)
                    missing = packet.get("missing_locations")
                    if not isinstance(missing, list):
                        raise ProtocolError("Missing location inventory")
                    missing = {integer(location, "missing location", 1, 2**63 - 1) for location in missing}
                    if missing & known_checks or missing | known_checks != store.manifest.checks:
                        raise ProtocolError("Server's location inventory differs from the generated slot")
                    authenticated = True
                    LOG.info("Character %s connected to seed %s slot %s", store.guid, seed, config["slot"])
                    await send(socket, {"cmd": "Sync"})
                elif command == "ReceivedItems":
                    if not authenticated:
                        raise ProtocolError("Rewards arrived before authentication")
                    if not store.receive(packet.get("index"), packet.get("items")):
                        await send(socket, {"cmd": "Sync"})
                elif command == "RoomUpdate" and "checked_locations" in packet:
                    if not authenticated:
                        raise ProtocolError("Location acknowledgement before authentication")
                    known_checks |= store.checked(packet["checked_locations"])
            if authenticated:
                store.status("connected")
                pending = store.pending_checks()
                already_known = known_checks & set(pending)
                if already_known:
                    store.checked(sorted(already_known))
                pending = [location for location in pending if location not in known_checks]
                if pending:
                    await send(socket, {"cmd": "LocationChecks", "locations": pending})
                if not goal_sent and store.victory():
                    await send(socket, {"cmd": "StatusUpdate", "status": 30})
                    goal_sent = True


async def run(config, store):
    while True:
        try:
            await session(config, store)
        except (OSError, ConnectionClosed, TimeoutError):
            LOG.warning("Archipelago disconnected. Retrying in 5 seconds")
        finally:
            store.status("disconnected")
        await asyncio.sleep(5)
