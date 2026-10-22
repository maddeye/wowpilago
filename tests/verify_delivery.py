"""Run the real protocol-2 isolated MySQL/WebSocket checks, never the realm.

WOWPILAGO_DB_PASSWORD=test-only WOWPILAGO_TEST_DB_PORT=13317 \
    .venv/bin/python tests/verify_delivery.py --v2-isolated

Requires a disposable local MySQL instance. Writes only wowpilago_bridge_v2_test
and wowpilago_v2_test. The effects SQL suite requires port 13317.
This is not an in-game inventory or notification verification.
"""

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REFUSAL = (
    "Protocol 1 realm verification is retired. No realm connection or SQL was attempted. "
    "Preserve old characters, tables and receipt history. "
    "Use tests/verify_delivery.py --v2-isolated with a disposable local MySQL instance. "
    "See docs/BRIDGE_CLI.md for coverage and remaining manual checks."
)


def main():
    if sys.argv[1:] != ["--v2-isolated"]:
        raise SystemExit(REFUSAL)
    if os.environ.get("WOWPILAGO_TEST_DB_PORT") != "13317" or not os.environ.get("WOWPILAGO_DB_PASSWORD"):
        raise SystemExit("Set WOWPILAGO_TEST_DB_PORT=13317 and WOWPILAGO_DB_PASSWORD for disposable local MySQL")
    print("Running v2 offline queue/reconnect, WebSocket and full-slot SQL checks. No realm login.", flush=True)
    result = subprocess.run([
        sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_bridge*.py", "-v",
    ], cwd=ROOT)
    if result.returncode:
        raise SystemExit(result.returncode)
    raise SystemExit(subprocess.run([
        sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_v2_effects_sql.py", "-v",
    ], cwd=ROOT).returncode)


if __name__ == "__main__":
    main()
