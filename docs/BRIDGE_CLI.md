# Protocol-2 bridge CLI

Run from the repository with the existing dependencies in `bridge/requirements.txt`:

```sh
WOWPILAGO_DB_PASSWORD='your-password' .venv/bin/python bridge/client.py bridge.local.toml
# Or:
WOWPILAGO_DB_PASSWORD='your-password' .venv/bin/python -m bridge.client bridge.local.toml
```

`bridge.client.load_config(path)` remains the config API. Protocol handling lives only in
`bridge.v2`; the old `bridge.client.Store`, `session`, `run`, and potion constants are removed.
Old callers must migrate to v2 and supply its full generated manifest, not a protocol-1 seed.

## Configuration

```toml
protocol_version = 2
character_guid = 23
server = "wss://ap.example.org:38281"
slot = "Azeroth"

[database]
host = "127.0.0.1"
port = 3306
user = "wowpilago"
database = "acore_characters"
```

`protocol_version` defaults to integer 2. No other protocol is accepted, including strings,
booleans or floats. GUID must be a nonboolean integer from 1 through 4294967295.
Slot must be a nonblank string. Server must use `ws` or `wss` with a host and an optional
port from 1 through 65535. Credentials, whitespace and URL fragments are rejected.

`database` must be a table with nonblank string `host`, `user` and `database` settings.
Its optional integer `port` defaults to PyMySQL's 3306. Unknown settings in either table
are errors, not ignored options. Passwords belong in `WOWPILAGO_DB_PASSWORD`, not TOML.
The AP room password, when needed, comes from `WOWPILAGO_AP_PASSWORD`.

Config/file errors, rejected manifests and MySQL errors stop with a logged error and
exit code 1. Ctrl-C closes the database connection. Network disconnects use v2's reconnect
loop. First binding requires an offline level-1 character matching the generated profile.
Existing bindings and immutable manifests cannot be repurposed for a different slot.

## Data safety

This convergence does not migrate, delete or reset legacy SQL tables or receipt history.
Do not clear those tables to make an old character fit a new seed. Back them up and retain
them. Use a fresh offline level-1 character for a new protocol-2 binding.

## Isolated verification

The old `verify_delivery.py ws://...` and `verify_inventory_edges.py` realm invocations now
refuse before opening any connection. They cannot verify a protocol-2 world and must not
reuse the old potion fixtures. The realm command encoder remains for its wire-format test.

Use the replacement runner only against disposable local MySQL:

```sh
WOWPILAGO_DB_PASSWORD=test-only WOWPILAGO_TEST_DB_PORT=13317 \
  .venv/bin/python tests/verify_delivery.py --v2-isolated
```

The runner executes real tests, not mock inventory operations. It writes only the isolated
`wowpilago_bridge_v2_test` and `wowpilago_v2_test` databases. Fixtures reset their own test
tables, so do not store anything valuable there or run tests sharing these schemas concurrently.
It never logs into a realm or writes `acore_characters`. It covers durable offline reward queuing, reopening/replaying a binding,
WebSocket authentication/reconnect/replay and native check acknowledgement, full-slot SQL failure/retry,
transaction rollback and duplicate suppression. CLI boundary tests mock only v2 startup
and async execution. Historical inventory SQL tests remain independent of the CLI:

```sh
WOWPILAGO_DB_PASSWORD=test-only WOWPILAGO_TEST_DB_PORT=13317 \
  .venv/bin/python -m unittest discover -s tests -p 'test_inventory_sql.py' -v
```

## Manual checks still required

No runtime deployment or live realm verification is part of this change. Isolated SQL
checks do not establish any of the following:

1. Native online/offline reward processing across logout and realm restart.
2. A physically full backpack delaying delivery, then exactly one item after freeing space.
3. Exactly one ITEM_PUSH and addon notification, with no premature success on SQL failure.
4. A real generated AP room reconnect preserving rewards, merchant stock and acknowledged checks.
5. Unchanged achievements and no unintended mail or inventory changes on the live realm.
