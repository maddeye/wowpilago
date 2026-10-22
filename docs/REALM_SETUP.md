# Private protocol-2 realm preparation

This setup is test-only. It reuses the existing `wow-test` MySQL data and client data. It does not start servers, import core updates, reset accounts, create characters, or erase legacy Archipelago history. Warden is deliberately off. Do not expose this realm publicly.

## Preparation completed on 2026-10-19

Added 11 v2 character tables, 3 effect procedures, merchant template/model 900500 and all 10 reserved spawns. Created the separate `acore_playerbots_v2` with 29 base tables. Added accounts `APV2A` through `APV2F`, IDs 2 through 7, expansion 2, GM level 0, zero characters and zero-character realm counters. Existing account 1 and characters `Test`, `Apbags`, `Approbe` remain intact. No existing playerbots database was modified.

Nine self-checks pass, including three real-MySQL checks confined to a disposable PID schema. Read-only post-install preflight reports zero missing accounts, character objects or merchant rows. Compose rendering and build-image library checks pass. System Python still lacks PyMySQL; the existing venv works. No other missing runtime library or config file was found, but startup compatibility remains untested.

The first apply stopped at the first playerbots seed INSERT because the SQL helper passed an empty parameter tuple, making PyMySQL interpret literal `%` text as formatting. The helper now passes `None` for raw SQL, covered by a real-MySQL regression check. Before recovery, a PID schema independently verified every installed v2 table/procedure definition and the sole empty playerbots table. The checkpoint-specific `.local/v2-realm/recovery.py` then completed only missing additions after another backup. It refuses reruns once the receipt exists. Both attempts preserved all 133 pre-existing characters/auth tables. The before and after snapshot files in both backup directories have identical SHA-256:

```text
2c2babcc92c9290d84cc5b12cadee6b1295a8171f00456c2a6f2ae46ba4dab29
```

Evidence is in `.local/v2-realm/preparation.json`, `receipt.json`, `selftests.log`, `preflight.log`, `runtime-libraries.log` and the backup directories `20261019T160521.148254Z` and `20261019T160730.389998Z`. The initial failure and verified recovery logs are retained. No authserver/worldserver start, restart or deployment command was run.

## Files and prerequisites

| Path | Purpose |
| --- | --- |
| `tests/provision_realm.py` | Read-only preflight by default; `--apply` permits backups and ADD-only installation |
| `tests/test_provision_realm.py` | SRP6, account ownership, DB guard, SQL parsing, config and isolated MySQL checks |
| `.local/v2-realm/override.yaml` | Private override for `../wow-test/compose.yaml`; never combine with the legacy override |
| `.local/v2-realm/config/` | Private auth, world and module configs, separate from original runtime configs |
| `.local/v2-realm/backups/` | Full characters/auth dumps, targeted merchant dumps, SHA-256 manifests and before/after row hashes |

Run from the repository root. Use the existing `.venv/bin/python`, which has PyMySQL. System `python3` does not have it. Docker Compose must support `!override` and `!reset`; installed version 5.5.0 does. Private artifacts under `.local` are not committed.

The tool accepts no alternate host, port, user or live schema. It connects as root only to `127.0.0.1:13317`, checks the inspected MySQL server UUID, `wow-test` container labels, loopback port binding and original MySQL bind mount. It refuses while other `wow-test` services run. The existing realm must advertise loopback port 8085, Wrath build 12340 and player access. GUID/name pairs `1/Test`, `2/Apbags`, `3/Approbe` must still exist.

## Checks and application

1. Run offline self-checks:

   ```sh
   .venv/bin/python -m unittest discover -s tests -p test_provision_realm.py -v
   ```

2. Run actual MySQL self-checks. All test writes use a newly created PID-named schema and PID account name inside that schema. Cleanup drops only that disposable schema. The tests only read the real schemas.

   ```sh
   WOWPILAGO_PROVISION_MYSQL_TEST=1 WOWPILAGO_DB_PASSWORD=test-only \
     .venv/bin/python -m unittest discover -s tests -p test_provision_realm.py -v
   ```

3. Preflight without writes. Both passwords are required; the account password must be ASCII, 1 to 16 characters, matching the native account length limit.

   ```sh
   export WOWPILAGO_DB_PASSWORD=test-only
   export WOWPILAGO_TEST_ACCOUNT_PASSWORD=test-only
   .venv/bin/python tests/provision_realm.py
   ```

4. Explicit application, only while the realm is stopped:

   ```sh
   .venv/bin/python tests/provision_realm.py --apply
   ```

Each application first backs up the actual `acore_characters` and `acore_auth` databases, including routines/triggers, plus merchant template 900500, its models, and matching/reserved spawns 9005000 through 9005009. Dumps are private and contain credentials and player data. Their SHA-256 hashes are in `dump-sha256.json`. Dumps contain restore DDL; the provisioner never executes those dumps. Restoration requires separate review, never blind import into shared data.

The provisioner hashes every row of every pre-existing characters/auth table before and after application. Only newly inserted account IDs and their new realm counters are excluded from the after comparison. Existing accounts, characters, inventory and legacy history must match. A mismatch stops with an error and retains the evidence, without attempting a destructive rollback.

`sql/v2.sql` adds only absent tables. `sql/v2_effects.sql` adds only absent procedures, skipping its DROP directives. Existing protocol-2 objects need a matching private receipt and schema definition; unverified objects or changed source SQL require manual review. The world installer checks every NPC collision predicate from `sql/world.sql`, then inserts only absent merchant rows. Matching rows are skipped; differing rows are refused, never updated. No world installer routine is created or replaced.

Playerbots base SQL is imported only into a newly created `acore_playerbots_v2`. The tool strips its DROP/DELETE statements and accepts only CREATE/INSERT statements. It never imports into an older playerbots database. An already existing v2 playerbots database needs the matching receipt/schema; interrupted installation requires review rather than overwrite. Base seed/cache data is not an account or character population.

Accounts `APV2A` through `APV2F` use random 32-byte salts and the pinned core's Wrath SRP6 verifier, with uppercased ASCII username/password and little-endian integers. Both mail fields carry `wowpilago-fixture@invalid`. Existing names require both markers and a matching verifier. They must already have expansion 2, no nonzero GM access and a realm counter. The tool never resets their passwords or updates any existing row. New accounts get expansion 2, no `account_access` grant, and zero-character counters for each existing realm. This follows `AccountMgr::CreateAccount` initialization but scopes inserts to the new account IDs, avoiding its broad missing-counter repair query. Characters must be created later through a real client.

## Private runtime configuration

The override mounts the current install directory from `.local/v2-build/20261019T150600.624050Z/install`, not a copied or final-hash-pinned binary. Another agent is refreshing that build's header and playerbots safety patch. The parent must approve its completed build evidence before starting anything.

The runtime image is the exact build image, `sha256:d29bbb51fbad4cff828b9ede4333d5ef31b2573d5d3e5c3457897ad7dd34ab48`. Generated core/module libraries are statically linked; this image supplies MySQL, Boost, OpenSSL and other dynamic libraries. Offline `ldd` checks against the image are recorded in `.local/v2-realm/runtime-libraries.log`. No server was invoked for those checks.

Both commands use explicit `-c /work/install/etc/<server>.conf` paths. The private config mount also sits at the compiled module configuration directory `/work/install/etc/modules`, so `playerbots.conf` is not accidentally loaded from the old runtime. Database connections use the existing compose service `database:3306` inside the network, not container loopback. Only host publications use 127.0.0.1.

The world config preserves default XP rates of 1, level maximum 80 and `Rate.Talent = 1`. This core calls its world-worker setting `MapUpdate.Threads`, set to 1, not `WorldWorkerThreads`. Database and network worker defaults are also 1. Core updates and automatic DB setup are disabled in both server configs. SOAP and remote administration are disabled, with no SOAP publication.

The linked native playerbots module is disabled through `AiPlayerbot.Enabled = 0`. Random/alt login, bot/addclass account pools, level automation, talent/spell/equipment automation and random activity are also disabled explicitly. Its DB connection points only at `acore_playerbots_v2`, and module updates are off. Do not enable the module or summon bots until the parent reviews the refreshed safety patch and progression behavior. Zero account counts alone are not a sufficient safety switch because upstream can calculate them automatically.

## Parent review, not an instruction to deploy

Inspect the merged configuration first. This command does not start services:

```sh
docker compose -f ../wow-test/compose.yaml \
  -f "$PWD/.local/v2-realm/override.yaml" config
```

Only after parent approval of the refreshed build, backups, receipt and runtime prerequisites, the proposed start command is:

```sh
docker compose -f ../wow-test/compose.yaml \
  -f "$PWD/.local/v2-realm/override.yaml" \
  up -d --no-deps --no-build --pull never authserver worldserver
```

This command has **not** been run. It deliberately excludes `database`, `db-import` and `client-data`, so it must not recreate or restart the running DB or run core imports. Do not use a bare `compose up` or add the legacy `.local/test-realm.override.yaml`. Existing DB volumes and `/data/client-data` remain unchanged. The configs bind to all container interfaces so Docker port forwarding works; host publications remain loopback-only. Other containers on the same Docker network can still reach container ports, so this is host-private, not isolation from trusted Docker peers.

Remaining runtime gates are the parent build refresh, actual server/schema compatibility, client-data compatibility, real-client login/character creation, and native gameplay/playerbots checks. No startup, client login, gameplay or release readiness is claimed.
