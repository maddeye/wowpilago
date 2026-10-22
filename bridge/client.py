"""One operator-configured protocol-2 character connection to an Archipelago slot."""

import argparse
import asyncio
import logging
from pathlib import Path
import sys
import tomllib
from urllib.parse import urlsplit

import pymysql

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bridge import v2
from bridge.catalog import integer

LOG = logging.getLogger("wowpilago")


def load_config(path):
    with open(path, "rb") as stream:
        config = tomllib.load(stream)
    required = {"character_guid", "server", "slot", "database"}
    missing = required - config.keys()
    if missing:
        raise ValueError(f"Missing config settings: {', '.join(sorted(missing))}")
    unknown = config.keys() - required - {"protocol_version"}
    if unknown:
        raise ValueError(f"Unknown config settings: {', '.join(sorted(unknown))}")
    if type(config.get("protocol_version", 2)) is not int or config.get("protocol_version", 2) != 2:
        raise ValueError("protocol_version must be integer 2. Protocol 1 is retired; preserve legacy receipt history")
    integer(config["character_guid"], "character_guid", 1)
    server = config["server"]
    try:
        address = urlsplit(server) if isinstance(server, str) else None
        valid = (address is not None and address.scheme in ("ws", "wss") and address.hostname
                 and address.username is None and address.password is None and not address.fragment
                 and not any(char.isspace() for char in server)
                 and (address.port is None or 1 <= address.port <= 65535)
                 and not address.netloc.endswith(":"))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("server must be a ws:// or wss:// URL with a valid host/port, without credentials, whitespace or fragment")
    if not isinstance(config["slot"], str) or not config["slot"].strip():
        raise ValueError("slot must be a nonblank string")
    database = config["database"]
    if not isinstance(database, dict):
        raise ValueError("database must be a TOML table")
    missing = {"host", "user", "database"} - database.keys()
    if missing:
        raise ValueError(f"Missing database settings: {', '.join(sorted(missing))}")
    unknown = database.keys() - {"host", "user", "database", "port"}
    if unknown:
        raise ValueError(f"Unknown database settings: {', '.join(sorted(unknown))}. Use WOWPILAGO_DB_PASSWORD for the password")
    for key in ("host", "user", "database"):
        if not isinstance(database[key], str) or not database[key].strip():
            raise ValueError(f"database.{key} must be a nonblank string")
    if "port" in database:
        integer(database["port"], "database.port", 1, 65535)
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="Path to the operator's TOML config")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    store = None
    try:
        config = load_config(args.config)
        store = v2.Store(config["database"], config["character_guid"])
        asyncio.run(v2.run(config, store))
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, pymysql.MySQLError) as error:
        LOG.error("Bridge stopped: %s", error)
        raise SystemExit(1) from None
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    main()
