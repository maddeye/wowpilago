"""Verify the pinned AzerothCore source, world DB revision, and client build."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pymysql

ROOT = Path(__file__).resolve().parents[1]


def verify_database(connection, expected):
    with connection.cursor() as cursor:
        cursor.execute("SELECT db_version,cache_id FROM version")
        revision, cache = cursor.fetchone()
        if (revision, cache) != (expected["database_revision"], expected["database_cache_id"]):
            raise ValueError(f"Database revision mismatch: {(revision, cache)}")
        cursor.execute("SELECT name,hash FROM updates ORDER BY name")
        updates = cursor.fetchall()
    digest = hashlib.sha256(json.dumps(updates, separators=(",", ":")).encode()).hexdigest()
    if digest != expected["database_updates_sha256"]:
        raise ValueError(f"Applied world updates differ from support.json: {digest}")
    return {"revision": revision, "cache_id": cache, "updates_sha256": digest, "applied_updates": len(updates)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--port", type=int, default=13317)
    parser.add_argument("--user", default="root")
    parser.add_argument("--client-build", type=int, default=12340)
    args = parser.parse_args()
    expected = json.loads((ROOT / "support.json").read_text())
    commit = subprocess.check_output(["git", "-C", str(args.core), "rev-parse", "HEAD"], text=True).strip()
    if commit != expected["core_commit"]:
        raise SystemExit(f"Unsupported core commit {commit}")
    if args.client_build != expected["client_build"]:
        raise SystemExit(f"Unsupported client build {args.client_build}")
    with pymysql.connect(host="127.0.0.1", port=args.port, user=args.user,
                         password=os.environ["WOWPILAGO_DB_PASSWORD"], database="acore_world") as connection:
        result = verify_database(connection, expected)
    changes = subprocess.check_output(["git", "-C", str(args.core), "diff", "--binary", "HEAD"], text=True)
    result.update({"core_commit": commit, "client_build": args.client_build,
                   "working_tree_diff_sha256": hashlib.sha256(changes.encode()).hexdigest(),
                   "working_tree_is_clean": not bool(changes)})
    (ROOT / "docs" / "support-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
