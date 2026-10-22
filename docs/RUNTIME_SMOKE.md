# Native v2 runtime smoke

`tests/verify_runtime.py` uses fabricated AP ingress. It is not a real AP client, gameplay test, playthrough, or release gate. No live execution has been performed for this implementation. The server was not started, restarted, or deployed.

## Safe first commands

1. Print the plan. This does not open sockets, query SQL, or authenticate.

   ```sh
   .venv/bin/python tests/verify_runtime.py
   ```

2. Run the offline tests.

   ```sh
   .venv/bin/python -m unittest discover -s tests -p test_runtime_runner.py -v
   ```

3. After the operator has independently made the intended native v2 server ready, run the bounded level-1 smoke.

   ```sh
   export WOWPILAGO_TEST_ACCOUNT_PASSWORD=test-only
   # Supply WOWPILAGO_DB_PASSWORD privately in the environment.
   .venv/bin/python tests/verify_runtime.py --run --account APV2A
   ```

4. To also attempt native XP-bank/release and selected-player learn checks, use a new run with setup enabled.

   ```sh
   .venv/bin/python tests/verify_runtime.py --run --account APV2B --setup
   ```

Every run creates new characters. There is no resume, reset, delete, account provisioning, SQL repair, or cleanup mode. Keep the printed seed, character name, GUID and binding ID as evidence. A failed run leaves its fixtures and history intact. Do not connect its seed/character to an actual AP room, clear its indexes, or reuse its binding for another test.

## Guards and prerequisites

Only explicit `--run` enables runtime work. `--setup` alone still prints the plan. Connections are fixed to loopback auth 3724, world 8085 and MySQL 13317. The runner does not follow the realm list's host address. Both server listeners must accept a connection, then normal SRP6 authentication must return an unlocked online realm. A listening socket alone does not count as a successful smoke.

The provisioned APV2A through APV2F accounts must have the exact email `wowpilago-fixture@invalid`, no account-access row above security 0, and no current online session. The runner checks the chosen account, not all six. Passwords come from `WOWPILAGO_TEST_ACCOUNT_PASSWORD`, which must equal `test-only`. It does not provision or elevate accounts.

The optional, narrow exception is the existing TEST/TEST GM3 account for setup. It must be offline before each setup login. The runner creates fresh, randomly named human warriors on TEST. It never logs an existing TEST character. The player under test remains on its marked SEC_PLAYER account for delivery, status, purchase rejection and equip.

Before creation, the runner records all existing character GUIDs and checks that its random name is absent. Before sending `CMSG_PLAYER_LOGIN`, it requires an observed successful creation event and a new GUID, or a GUID created earlier by this same invocation for relogin. Ownership, exact name and human-warrior profile must match. GUIDs 1, 2 and 3 are always rejected, even if supplied in the known-created set. This protects the original Test, Apbags and Approbe characters regardless of name spelling. No other preexisting character is an eligible target.

The database must already have the current v2 tables/routines, catalogs and matching native module. The operator must confirm the intended compiled core and `CharacterDatabase.WorkerThreads=1`, as required by `docs/V2_EFFECTS.md`. The runner does not deploy SQL or verify the running binary's provenance. A native callback/configuration mismatch should fail the checks, not trigger an automatic fix.

## What runs

The first login creates a fresh human warrior through the authenticated client and logs it out fully. Only then does `bridge.v2.Store` bind its offline level-1 GUID to a random `fabricated-native-smoke-*` seed. `Catalog` validates the complete current manifest, including checks, class reward allowlist, one selected legendary, 30 personal stock entries and progression rules. There is no WebSocket session and no AP-room connection. Immediately after binding, Store status is set to disconnected so the fixture does not advertise a live AP bridge.

`Store.receive(0, ...)` queues these exact rewards in order:

| Index | AP ID | Effect |
| --- | --- | --- |
| 0 | 919100001 | Cap +10 |
| 1 | 919100020 | One talent permission |
| 2 | 919101100 | Charge permission, spell 100 |
| 3 | 919100010 | Apprentice riding permission |
| 4 | 919100033 | Five vouchers |
| 5 | 919100040 | Netherweave Bag, 21841 |
| 6 | 919419019 | Thunderfury, 19019 |

These are fabricated `NetworkItem` records with source location -1, sender 0 and flags 0. They are controlled fixture ingress, not proof that AP generated or delivered anything. Store writes only binding/manifest/queue state and its associated check/reward/stock allowlists. The runner's observation connection accepts only SELECT statements. No runner SQL changes character level, XP, money, inventory, spells, or progression effects. Native callbacks must apply the queued effects.

On player login, the runner waits up to 45 seconds for all seven durable applied receipts. It checks live status for cap 20, clears selection and verifies that `.archipelago buy 0` refuses a purchase without a nearby selected merchant. It then sends `.archipelago equip <authorized Thunderfury GUID> 15` as SEC_PLAYER. The saved main-hand placement, not merely a command response, proves equip succeeded.

After full logout it checks receipt identities, cap/talent/riding/voucher totals, Charge permission, the physical owned bag, the legendary's authorization and instance flags, and unchanged unsold stock with no purchase receipts. It replays the identical ingress without changing any index, relogs the same known-created GUID, captures initial spells and free talent points, logs out again, and compares durable progress, receipts, inventory placements, serialized item rows, permissions, spell rows, authorization and stock. Differences fail the smoke.

This is full logout-save/relogin persistence, not crash recovery. No native effect procedure is called by the runner directly.

## Optional native setup and pinned commands

Command signatures were inspected read-only under `.local/v2-build/20261019T150600.624050Z/source/src/server/scripts/Commands`. The runner does not patch that tree or the dirty source checkout.

| Source | Supported command and use |
| --- | --- |
| `cs_character.cpp`, `HandleLevelUpCommand` | `.levelup <fresh player name> 9`, from level 1 to cap 10 |
| `cs_quest.cpp`, add/complete/reward handlers | `.quest add 783 <name>`, `.quest complete 783 <name>`, `.quest reward 783 <name>` |
| `cs_learn.cpp`, `HandleLearnCommand` | `.learn 100` or `.learn 33388`, acts on selected player, not a trailing name argument |
| `cs_misc.cpp`, `HandleSaveAllCommand` | `.saveall` exists but saves every online player, deliberately not sent |

With `--setup`, a newly created TEST GM selects the known-created bound player GUID, attempts locked Charge learning, raises that player to level 10, and adds/completes/rewards quest 783. This is fabricated GM quest setup, not quest gameplay. After both clients log out, level must be 10, Charge must remain absent and the saved bank must be positive. If the quest or core configuration does not produce banked XP, the run fails. It does not insert bank/XP through SQL or silently skip the assertion.

The queued cap receipt must then release exactly `min(saved bank, floor(level-10 next-level XP / 2))` into ordinary XP, clear the bank and leave level 10 unchanged. The XP-table value is read from the existing world database. A second fresh TEST GM selects the fixture player and attempts Charge and Apprentice Riding learning after permission delivery. Charge must persist, while riding must remain absent below level 20. Relogin must report one free talent point at level 10. Without `--setup`, the level-1 run expects zero free points and does not claim XP-bank or successful ability-learning coverage.

Normal command packets are `CMSG_MESSAGECHAT` 0x095 with uint32 SAY=1, uint32 Common=7, and NUL-terminated text. Selection is `CMSG_SET_SELECTION` 0x13D with a full uint64 player GUID. Local packet readers capture normal system chat, initial spells and the leading free-point count of player talent packets. The layouts were checked against pinned `Chat.cpp`, `Player.cpp` and `Opcodes.h`. `tests/realm_client.py` is unchanged.

## Remaining live gates

A bounded PASS is not overall native-v2 completion. These gates remain:

1. Execute both run modes against the intended live core. Offline unit tests only verify guards, manifest/queue literals and packet layouts. This implementation has not demonstrated live delivery, equip, setup quest XP or persistence.
2. Positive merchant purchase, exact voucher debit, purchase receipt/authorization, replay and equip of purchased gear. The runner currently exercises only purchase rejection without a selected merchant, plus positive equip of a direct legendary. It must not fabricate a creature runtime GUID from a database spawn GUID. Extend the client with nearby creature discovery and movement/teleport acknowledgements before automating the positive merchant case.
3. Spend talents through `CMSG_LEARN_TALENT` and test reserved points at later levels. Learn riding at the eligible level and test rank/prerequisite failures. The current checks cover permission delivery/free-point packets and, with setup, denied below-level riding learning only.
4. Test real AP-room ingress, checks, progression through gameplay, higher-level gates, crash recovery, full bags, concurrency, transfer restrictions and release criteria separately. Never attach these fabricated fixtures to a real AP room.

Suggested parent-owned client APIs are `system_messages`, `initial_spells`, player talent-state capture, nearby-creature GUID discovery, and narrow teleport acknowledgements. This runner implements the first three locally and proposes the latter two only. No empty merchant/talent action is counted as coverage.
