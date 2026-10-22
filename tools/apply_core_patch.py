#!/usr/bin/env python3
"""Apply the audited patch to the pinned core, including .git-free archives."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

PROJECT = Path(__file__).resolve().parents[1]
PATCH = PROJECT / "patches/azerothcore-v2.patch"
COMMIT = "9fb906bb7296212ff42fc95ff73a92aaf8554f0d"
# Generated from git archive of COMMIT and the resulting patched files.
FINGERPRINTS = {
    "src/server/scripts/World/server_mail.cpp": {
        "original": "6c1e4f4c3a31af713383124944d9a8259094cc9b65bf37152e08b7564fd02810",
        "patched": "508dbbdb9b6421805e6f34cda06e7981cfec8c7ab4bd8af9d0a3458e59d9952d",
    },
    "src/server/database/Database/MySQLConnection.cpp": {
        "original": "02f083daa76d1901030d775497981391e49af9d852333b67d50803d4422c0aa5",
        "patched": "19e8a51a84ebbf002f44a1a21759e81ad31ef0609b7548721b7f99cb7498b350",
    },
    "src/server/database/Database/MySQLConnection.h": {
        "original": "3c7de6ab1114301d63655212e84dc5b49d5302294a5617a59f990c8721e19870",
        "patched": "042982a79b57885727abe597f4d23dd750ba5a07a1da30550055baace4fe2300",
    },
    "src/server/database/Database/Transaction.cpp": {
        "original": "cbd8582eb53b230b54c8c8fc5f6dd7dd19124208f2de5e291874e8a81ec25896",
        "patched": "9045655d919e8792c0ddb66791d61b2dffad18c6dae9d1c6018d489f55f00c45",
    },
    "src/server/database/Database/DatabaseWorkerPool.cpp": {
        "original": "f31ac093e94ff8813689f79212a67f3d3a5570ec7c30833b8406690e54d5cdc1",
        "patched": "6f6edd055d0b0858f6606f1358d0d7f1b634ddd7588ca54af0513bd94fa8ca34",
    },
    "src/server/game/Entities/Creature/Trainer.cpp": {
        "original": "d4278f255b334f2298a33b2af93f60542f26b608afb968fd9d1638fa04123619",
        "patched": "accc4cb09adab83728c745558e6aa860a47ded8d0e8a994c39d39c4257b64076",
    },
    "src/server/game/Entities/Player/Player.cpp": {
        "original": "45cba4ed7c92debf42c974984fe727e35e21779a21b7bbfa7bb045ad8a1bf509",
        "patched": "22927f1cbf62fdbed6aa1441e84dbf01b173579f8c3dbc58a734dfb153726551",
    },
    "src/server/game/Entities/Player/Player.h": {
        "original": "74bbdb808f307ca346bde6933519364b6e198015e84e730ebc03db7e043266dd",
        "patched": "0b9bef59736c698dff76d52246bffb4e96f07627ce12d171c3fae1aae8dce1db",
    },
    "src/server/game/Entities/Player/PlayerStorage.cpp": {
        "original": "bcd368071217a82e7a6af8ac001337fac0092beff22f6e143d3ece40ad379606",
        "patched": "c7263b4ee679ca92c28478382a57c5c1428398c70e9f62cdf7efe29db5587a12",
    },
    "src/server/game/Maps/MapMgr.cpp": {
        "original": "2497304d1b5b1b28f2f96cf43f935e45a1aa5fc9fe1a46760a998044b99dbbdd",
        "patched": "91ff6d0d90b8f6168c8579084e1e2e512df0161696ea0d7721cb489abea18a2e",
    },
    "src/server/game/Scripting/ScriptDefines/PlayerScript.cpp": {
        "original": "a36602c5ff6bd69d6af194ec8a0b6710bfb8669318ef315502b930bb3d2592e6",
        "patched": "a82985163dedb1eb504f3a3d8fb90a26ef942dccc8e6f34f5a367b4d7e8a33a6",
    },
    "src/server/game/Scripting/ScriptDefines/PlayerScript.h": {
        "original": "026e272425ebc234fc74c9ecd4d1ca4982ddd8183f8e11c3ad9181225f5c88f5",
        "patched": "3ca326a7aa2fc5ec8c397adf3e36631602aa18b91bd869af561d64717b353d0c",
    },
    "src/server/game/Scripting/ScriptMgr.h": {
        "original": "da94439b0d98c6198dcab26f48680b67be5fbb7ddd02c51052c1e65c8d7a42cd",
        "patched": "cf5f2f52d4aca453f5c9674a4af0f43d21ce3ee8103267c74dbd0680cf6fac9e",
    },
}


def git(core, *args):
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(core.parent))
    return subprocess.run(
        ["git", "-C", str(core), *args], env=env,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def apply(core):
    core = Path(core).resolve(strict=True)
    support = json.loads((PROJECT / "support.json").read_text())
    if support["core_commit"] != COMMIT:
        raise ValueError("support.json core_commit does not match the audited patch")

    # Do not treat an archive inside an unrelated repository as that repository.
    repo = git(core, "rev-parse", "--show-toplevel")
    if repo.returncode == 0 and Path(repo.stdout.strip()).resolve() == core:
        head = git(core, "rev-parse", "HEAD")
        if head.returncode or head.stdout.strip() != COMMIT:
            raise ValueError(f"wrong core commit; expected {COMMIT}")

    actual = {}
    for name in FINGERPRINTS:
        path = core / name
        if not path.resolve().is_relative_to(core) or not path.is_file():
            raise ValueError(f"missing or unsafe core source: {name}")
        actual[name] = hashlib.sha256(path.read_bytes()).hexdigest()

    reverse = git(core, "apply", "--reverse", "--check", str(PATCH))
    if reverse.returncode == 0:
        state = "patched"
    else:
        state = "original"
    changed = [name for name, hashes in FINGERPRINTS.items() if actual[name] != hashes[state]]
    if changed:
        raise ValueError("wrong or modified core source: " + ", ".join(changed))
    if state == "patched":
        return "already applied"

    check = git(core, "apply", "--check", str(PATCH))
    if check.returncode:
        raise ValueError("patch preflight failed: " + check.stderr.strip())
    result = git(core, "apply", str(PATCH))
    if result.returncode:
        raise ValueError("patch application failed: " + result.stderr.strip())
    return "applied"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", required=True, type=Path, help="explicit core checkout or archive root")
    args = parser.parse_args()
    try:
        print(apply(args.core))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"core patch: {error}\n")


if __name__ == "__main__":
    main()
