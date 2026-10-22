# Verification and design decisions

## Publication checks

The publication-prep source-only export passed 405 test cases with no failures or errors. Unittest reported 527 runs and 126 skip entries, including four class-level skips outside the run count. Private archives, external core/client data and connected SQL inputs were deliberately unavailable. The run used Python 3.14.7 with networking disabled and neither the original checkout nor private paths mounted. Generated catalogs, README links, Python 3.12 syntax and both licensed package archives also passed. Hosted GitHub Actions and actual Python 3.12 execution have not run yet.

Source-only CI does not re-verify the private native evidence below. The revised portable GUI helper has mocked tests, not a new native-client acceptance run. Publication preparation did not operate a realm or change gameplay code. Local runtime material remains ignored.

## Protocol 2 status

The current requirement audit is `tools/audit_todo.py`, backed by `docs/requirements-evidence.json`. The project is not release-complete. Native fixtures, actual AP logic and legitimate gameplay have separate evidence scopes.

The requirement ledger currently verifies154/188 tasks. The latest retained-source offline regression passed513 tests and skipped52 SQL-gated tests,565 total. A separate isolated MySQL8.4 regression passed35 bridge/effects tests with no skips. All55 pre-existing synthetic databases on that sandbox retained identical row data. The sandbox is stopped with its databases retained. See `docs/verification/character-delete-archive.json`. The earlier isolated public copy passed383 tests with122 reported integration skips. Both private-root aliases, host core/client-data paths, and network access were masked. The copied files and original public tree stayed unchanged during that run. Missing optional inputs now skip explicitly, while present corrupt inputs still fail. This is not native proof or a fresh-OS portability claim. See `docs/verification/clean-source-tests.json`. See `docs/verification/goal-ecbd80-offline.json`. The graphical shop passed Lua callback tests for 30, 60 and 120 rows and bounded native acceptance. The real client rendered all60 stock rows, resolved12 cold icons by one second, and completed one physical1-voucher purchase. Full122-table and auth audits protected previous items, other41 characters, frozen11 and the original room. The initial cold-cache failure remains preserved. See `docs/verification/graphical-shop.json`. The area-entry callback fix compiled and linked against the pinned core in an isolated candidate. That candidate is not deployed. See `docs/verification/graphical-shop-offline.json` and `docs/verification/area-producer-build.json`. The historical full SQL-gated regression passed all 523 tests before 32 unused Mage prototype guards were quarantined. World and auth services were stopped for those SQL tests. All 122 production character tables, all auth tables and the real AP save stayed exact. See `docs/verification/sql-lifecycle.json`. The bridge now accepts APWorld's existing0..10 legendary range. Seven manifest tests,34 packaged AP tests and actual0/5/10 generated-slot round-trips passed. The level1 stock client also rendered all30 rows and prices of a valid configured fixture. This is not actualdefault60-rowlevel1GUI proof. The first offline run correctly rejected a stale bridge source pin. Parent preserved the old source and inventory before reviewing the new hash, then reran with all guards intact.

Curated-check tracing found a level-milestone durability window. The actual level-change callback could reach the check publisher before the pending character save. Source now defers level checks until the full save commits and saved level, last_level, bank and XP are confirmed. Three compiled-production regressions cover the save barrier, failed/mismatched outcomes and short-logout/relog recovery. The retained old source fails all three enabled-check fixtures. A fresh pinned-core/playerbots candidate compiled and linked with this change. Parent verified actual source and binary hashes. The initial build attempt remains failed after concurrent parent test/docs edits; a fresh recovery passed preservation checks. User-approved world-only deployment now runs the actual `a20ecb1f7917616a3a84eae1cc9bfcb2dec5e0f504fc647204a1e0695b4b5296` executable. All42 complete character rows and all AP tables are exact. Parent reviewed the new uptime row and seasonal event12 timestamp against pinned startup code without widening old guards. Auth/database services are unchanged. A subsequent actual stock-client test of this same binary in a NEW isolated realm passed all six representative check types: physical783 reward, level5/10 save barrier, Elwynn zone entry, five natural Wailing Caverns bosses and its fifth-only clear, and natural Lucifron raid credit. All11 outbox rows and all AP tables survived normal logout/relog exactly. No received rewards/cap/access grants, source-row credit inserts or original-realm gameplay were used. A real owned-row lock wait plus989 samples demonstrated saved-level-before-credit ordering; separate level10 used743 samples. Original42 characters and all original player/AP/auth-account rows are exact. Original Wintergrasp4024 advanced14->15, rejected by the unchanged strict guard; pinned-source timed-defense attribution is recorded without rebaselining. Own services/GUI stopped cleanly, volume retained. Independent review supports only basic curated support, now154/188 requirements. No normal combat/travel/XP threshold, new AP transport, crash/failure, party/bot, all-content or release claim. See `docs/verification/native-curated-checks.json` and `docs/verification/curated-check-support.json`.

The private GUI launcher now records cleanup signals and errors and fails after forced or incomplete termination. Five modeled child-process cases cover status propagation and remaining-child cleanup. They do not prove actual native shutdown or strengthen historical cleanup evidence. See `docs/verification/gui-cleanup-status.json`.

Physical receipt toasts now request cold item metadata once and refresh the visible name/icon every 0.5 seconds for at most 5 seconds. They retain fallback, FIFO ordering and strict deduplication without reanimation or late overwrite. Lua and package checks pass, but corrected native cold-receipt rendering has not been observed. TODO205 remains open. See `docs/verification/receipt-toast-cache.json`.

The schema now archives and detaches a character's binding in a `BEFORE DELETE` trigger. Actual isolated InnoDB tests cover deletion without a native lookup, a binding added after a lookup miss, rollback after a late SQL error, unrelated NULL bindings and idempotent installation. All35 bridge/effects tests pass. The callback retains its ID-capture fallback for legacy schemas. Its earlier nine-test MySQL composition and linked core candidate remain historical pre-trigger evidence. The trigger migration is now installed in the test realm following explicit user approval. Its exact definition is verified. Full before/after captures keep all42 character rows, all items, spells, achievements, AP history and all22 auth tables exact. Two background system tables passed their separate natural-drift guards. The migration itself deleted no character or restarted any service. At installation time, candidate4dc44 was undeployed and old3b9 was still running. The later a20 rollout and isolated native checks are recorded above. See `docs/verification/character-delete-archive.json`.

A subsequent stock-client test created only fresh Human Warrior Apdeltarget/GUID43, configured binding32 with a genuinely generated new seed, and physically confirmed its deletion. It never entered the world or received a reward. The trigger archived/detached the binding and retained its manifest, progression,60 stock rows and213 enabled checks. All original42 characters, old items/spells/achievements/AP histories, frozen11 and original room stayed exact. Launcher exit0 and cleanup.forced=false prove normal owned closure. Existing native absence, outage, restart and logout evidence plus this new deletion proof complete TODO207 in the configured physical-delete realm. The independent closure review preserves separate SQL versus native scopes. Crash/commit windows, soft deletion/restoration and full M7 remain open. See `docs/verification/native-lifecycle.json` and `docs/verification/native-character-delete.json`.

The synthetic Mage38 sequence observed an early Ice Block permission at20, absence at29, same-connection learning at30, and persistence after one relog. Its original run remains `FAILED_PARTIAL` because the strict preservation audit rejected an existing aura countdown. Exact natural timing remains unproven. The private CLI failure-status and capture-clock bugs are fixed without replay. Existing Rogue35 GUI evidence already shows Evasion retained across physical spec switches and relogs in both groups, so no duplicate spec run is needed. Earlier native Warrior12 records also cover direct internal GM learning below and at an eligible rank level, with the learning gates unchanged in the deployed build. Paid trainer, LEARN_SPELL wrapper and pending-prerequisite release coverage remains open. See `docs/verification/ability-native-queued.json`.

- The latest verified deployment is `a20ecb1f7917616a3a84eae1cc9bfcb2dec5e0f504fc647204a1e0695b4b5296`, described above. Historical native cases used `3b9b2bf9f946a1eeef5908e440ed917132c0559c4bc483ba14be199060641809`, which includes the Artisan cast guard and login-mail callback fix. That earlier build remains archived at `.local/v2-build/20261019T191318.518327Z-mail-fixed/manifest.json`; it is not the current deployment.
- Actual native tests cover cap/XP banking, all nine supported class gates across two preserved runs, ordinary unbound DK exclusion, mount casts, merchant purchases, trade/mail/auction refusal, same-entry instance isolation and composite two-SIGKILL recovery. Stock-client Rogue35 respec/dual-spec/relogs and all ten native city merchants also passed. The public `docs/verification/native-*.json` summaries state each fixture and proof limit. This does not prove all-class combat or every fault window.
- The earlier package passed 2,000 restrictive fills. The new critical-travel graph passed 34 actual AP tests, 1,403,776 rule comparisons, 1,094 successful category fills and 52 additional seed fills, with catalog and slot manifests unchanged. The reference arithmetic is 300. Default Human still has 213 locations and 49/36 filler. Generated logic does not prove a normal leveling route or literal 100/72 filler.
- Legitimate gameplay has completed quests 783, 7, 5261, 33, 3903 and 3904. Apjourney now saves at level 3 with 1096 XP, 1106 copper, 4 vouchers, ten Minor and five Lesser Healing Potions. The graphical-shop acceptance test bought one Warleader's Shield15991/GUID591 for one voucher. It remains unequipped in bag298, slot5. Only stock18 became newly SOLD; the previous Troggbane purchase and every old item remained unchanged. The audited Stormwind session added one genuine Bag Upgrade and bought Troggbane for eight vouchers. The stock client physically equipped its original level-80 weapon at level 3. All previous item instances and the other 41 characters stayed exact. See `docs/verification/normal-stormwind-shop.json`. The separate direct legendary fixture and native negative authorization controls complete the bounded low-level equipment test in `docs/verification/native-low-level-equipment.json`. Combat, procs, set bonuses and broader compatibility remain unverified. Quest 15 is rewarded. Its pending check survived an actual world restart and later acknowledged through the original room. A real AP outage also proved automatic reconnection of the same bridge process without duplicated rows. The official peer applied the real Map Width effect and completed Tile6. Its returned cache became five level-appropriate Lesser potions through native receipt11. Parent verified actual client effects, real AP queues and unchanged prior histories. See `docs/verification/real-peer-return.json` and `docs/verification/reward-scaling.json`. The complete playthrough and both final goals remain unverified.

Current commands and setup are in `README.md` and `docs/BUILD.md`. Do not run the historical commands below. Protocol-1 production invocation is retired, and its room and receipts must remain intact.

## Historical protocol-1 prototype

The remaining sections record the earlier potion prototype. Their counts, binary pins, capabilities and commands are historical, not current release claims.

### Observed results

All 44 Python tests passed with MySQL 8.4 and a real Archipelago 0.6.8 room enabled.
This includes bridge validation and reconnects, 13 inventory routine tests, and the headless realm protocol checks.
The SQL checks covered concurrency, replay, occupied slots, rollback after failed inserts, and disconnect before commit followed by retry.
No database tests were skipped in the final run.

Five APWorld tests passed under Python 3.13.
The verification script loaded the packaged world, generated a seed, and checked its actual multidata.
The tested Archipelago checkout was `54803be064fc7e80c4628777ed0b46a9390f255f`.

The addon checks passed under Lua and LuaJIT.
They exercised self-whisper filtering, numeric bounds, item name/icon output, queued alerts, uncached-item fallback, and notification deduplication.
The C++ codestyle check passed.
The module object also compiled against upstream AzerothCore revision `d5e818f28ee80f5a39115c3bbaa695a6f859303e` through `tests/Dockerfile`.

## Real realm delivery

A full worldserver was built, linked, and started using the supplied `~/dev/probe/wow-test/azerothcore` checkout.
Its base revision was `9fb906bb7296212ff42fc95ff73a92aaf8554f0d`, with its existing local source changes retained in the temporary build copy.
The copied build included the Archipelago and NPC enchanter modules, not playerbots.
The source checkout and original Docker images were not edited.
The archived build reports an unknown revision because its temporary source copy has no Git metadata.

`tests/verify_delivery.py` connected the headless build-12340 client to the actual realm as the new `Approbe` character, GUID 3.
It connected the real bridge to slot `Azeroth`, submitted the connection check, and received the generated potion.
The client observed these packets.

```text
ITEM_PUSH {"guid": 3, "received": 1, "created": 0, "show_chat": 1, "bag": 255, "slot": 24, "item": 118, "suffix": 0, "random_property": 0, "count": 1, "total": 1}
ADDON {"sender": 3, "receiver": 3, "message": "WOWPILAGO\tITEM\t0\t118\t1", "tag": 0}
PASS delivery for character 3
PASS reconnect without duplication for character 3
```

The script checked the actual inventory placement, one receipt, one delivered queue row, and no Archipelago mail.
It logged out through the WoW protocol and logged back in.
The potion remained in inventory, without another grant or notification.
The real Archipelago server announced that `Azeroth` completed its goal.
The full local transcript is [.local/live-delivery.log](.local/live-delivery.log).

## Live failure and capacity checks

`tests/verify_inventory_edges.py` used the separate new `Apbags` character, GUID 2.
It filled all backpack slots through GM commands and queued one fixture reward.

The actual realm passed these checks.

- Full backpack for seven seconds. The reward stayed pending with no new potion, receipt, item-push packet, or addon success message.
- Explicit logout and seven seconds offline. The reward stayed pending.
- Free slots with a fixture-scoped trigger rejecting the receipt insert. The transaction rolled back and no success notification appeared.
- Trigger removal and retry. The character received one potion, one receipt, one item-push packet, and one addon success message.
- Achievement records before and after delivery were identical.

The fixture trigger was removed in cleanup.
No character or delivery history was deleted.
The local transcript is [.local/inventory-edges.log](.local/inventory-edges.log).
The pre-existing `Test` character was not used for these fixtures.

## What changed after investigation

The original mail version compiled, but its direct transaction used item-save prepared statements registered only for asynchronous database connections.
That path was not runtime-safe on the supplied core.
The core driver can also reconnect and replay individual statements inside a transaction without preserving the original transaction boundary.
Compilation alone did not reveal either issue.

The replacement creates a detached item and commits its instance, inventory placement, receipt, and delivery flag inside one idempotent stored procedure.
The procedure owns its transaction, so replaying the complete call cannot create a second reward.
A normal inventory save is queued separately before the procedure.
One character database worker preserves ordering with prior saves.
Only after authoritative verification does the module publish the item into live bags and emit success notifications.

This version deliberately requires an empty slot.
Updating existing stacks safely needs additional coordination with normal inventory saves.
An unknown final verification result stops worldserver instead of allowing the player to overwrite a possibly committed item.
The core's general persistence behavior after later consumption, trade, or movement is outside this module's guarantee.

The runtime probe also needed actual WoW protocol behavior rather than guessed packets.
GM commands use SAY and the human character's Common language, not SYSTEM or Universal.
Closing TCP leaves a disconnected character online during AzerothCore's grace period.
The probe now sends a logout request and waits for logout completion.
These packet and lifecycle cases have regression tests.

## Local test setup

The local realm remains separate from production.
Its untracked [.local/test-realm.override.yaml](.local/test-realm.override.yaml) mounts the built binary and its Boost runtime libraries.
It supplies the existing configuration file explicitly and exposes MySQL only on loopback port 13317.
It disables automatic database migrations and disables Warden only for the headless test client on this private realm.
The existing compose file and worldserver configuration file were not edited.

Use both compose files when managing this verified local binary.

```sh
docker compose -f ../wow-test/compose.yaml -f .local/test-realm.override.yaml up -d --no-deps database authserver worldserver
```

The Archipelago room used `/tmp/wowpilago-world-test-jz4anl1m/output/AP_65396539461970401801.zip` on loopback port 38282.
The character binding is permanent for that seed and slot.
Do not clear its delivery history to test reconnection.
The bridge configuration for `Approbe` is [.local/bridge.toml](.local/bridge.toml).
The local worldserver, authserver, database, bridge, and Archipelago room were stopped at the user's request after visual verification.
Their processes and listening ports were checked after shutdown. Database volumes and room files were preserved.
To resume, start the realm services, host the same saved room, and restart the bridge with this command.

```sh
WOWPILAGO_DB_PASSWORD=test-only .venv/bin/python bridge/client.py .local/bridge.toml
```

The test item has already been delivered. Reconnecting must not show another delivery popup or grant another potion.
After installing the addon, the user logged into `Approbe` and confirmed the connection.
One additional potion was requested through the real Archipelago room.
Inventory increased from one potion to two, delivery index 1 was recorded, and the user confirmed the achievement-style popup appeared.

## Not verified

Simultaneous display with a real achievement alert was not checked. A private toast may overlap it.

A whole-worldserver crash between database commit and publication was not injected.
The SQL disconnect/rollback/replay tests are not a substitute for that process-level fault test.
Production TLS, room passwords, cross-game routing, and unrelated inventory-modifying modules were not exercised.
Only the fixed potion reward and empty-slot delivery are supported.

No production realm was deployed or changed.
This project directory is not a Git repository, so no commit or pull request was created.
