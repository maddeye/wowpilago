# Bounded native merchant verification

`tests/verify_merchant_runtime.py` exercises the pinned native2 world through authenticated SEC_PLAYER sessions. AP ingress is fabricated through `Catalog` and `bridge.v2.Store` for newly created fixtures only. This is not a real AP room, ordinary gameplay, a full playthrough, or cross-trade verification.

## Run safely

1. Print the network-free plan:
   ```sh
   .venv/bin/python tests/verify_merchant_runtime.py
   ```
2. Run the offline guards and packet tests:
   ```sh
   .venv/bin/python -m unittest discover -s tests -p test_merchant_runtime.py -v
   ```
3. Only after the class-system agent has finished and released TEST, run:
   ```sh
   run_dir=".local/merchant-live/$(date -u +%Y%m%dT%H%M%SZ)"
   mkdir -p "$run_dir"
   set -o pipefail
   WOWPILAGO_TEST_ACCOUNT_PASSWORD=test-only WOWPILAGO_DB_PASSWORD=test-only \
     .venv/bin/python tests/verify_merchant_runtime.py --run --account APV2D --peer APV2E \
     --reuse-control class-systems-13 \
     | tee "$run_dir/run.jsonl"
   ```

The runner requires `.local/class-systems/summary.json` to report PASS with its control character offline. It also checks current SQL account online state and capacity before any authentication or character creation. An offline SQL observation is not a lock against another operator. Coordinate TEST ownership before running. `--reuse-control class-systems-13` is the parent's explicit authorization to reuse only the previously created GM fixture GUID 13, Apsjxsocfsik, on TEST account ID 1. It is not an arbitrary existing-character bypass.

The private endpoints are auth 3724, world 8085 and MySQL 13317 on loopback. The only accepted database credential is the private root/test-only fixture credential. Do not use this runner against a shared or production realm.

A normal run creates one new TEST human warrior control and two new marked GM0 human warriors on distinct APV2D/E/F accounts. Without the reuse option, TEST still needs one free slot. Each player account always needs one. Repeated runs preserve failed fixtures and consume player slots.

The narrow reuse helper checks `.local/class-systems/summary.json` for PASS and offline GM 13, `before.json` for absence of both GUID and name, and `run.jsonl` for the exact unique `gm_fixture` creation event. It then validates the current TEST account ID/security/offline state, exact character GUID/name/account, human warrior profile, level 1, offline state and absence of an AP binding. Only after all checks does it seed the shared runner's known GUID/name records and request login with `guid=13`, not fresh creation. The new transcript records SHA-256 hashes of all three prior evidence files. GUIDs 1..4 cannot enter through this option. No deletion, history reset, raised limit or configuration change is needed.

## Assertions

| Path | Required observation |
| --- | --- |
| Native delivery | Primary gets one voucher receipt worth five and one Thunderfury receipt. Peer gets five vouchers. Actual `.archipelago status` confirms the balance. |
| Real NPC interaction | Offline GM `.tele name npc guid <fresh fixture> 9005000` places the primary at the installed Stormwind merchant. `.npc info 9005000` returns its loaded runtime GUID. Primary receives gossip from that GUID. No selection and a selected distant NPC both refuse purchase. |
| Ordinary vs authorized item | Thunderfury is unique, so GM gives the fresh peer one ordinary copy, while the primary owns the AP-authorized copy. Both are level-1 human warriors. The distinct, unauthorized peer instance fails normal CMSG_AUTOEQUIP_ITEM_SLOT with required-level error 1 and stays in its backpack. The primary's authorized instance fails `.archipelago equip` to the head slot, then saves in main hand at level 1. |
| Full backpack retry | GM fills only the primary's remaining backpack slots with ordinary nonstacking Wolfskin Bracers, entry 6070. Native buy refuses with all 16 slots occupied and leaves economics and placement unchanged. The normal player equips one bracer into its empty wrist slot, freeing one slot without deleting anything. Retry succeeds. |
| Exactly-once purchase | One purchase receipt, one sold stock row, balance `5 - price`, one owned physical item with binding flags and per-instance authorization. Sold-item command replay plus identical AP receipt replay and logout/relogin do not change economics or placements. |
| Insufficient funds | After the peer purchase, its four vouchers cannot buy unsold six-voucher stock. With free backpack space and actual nearby merchant gossip, native buy returns `Entry sold, invalid, or not enough vouchers.` Logout and fresh SELECT snapshots must show identical balance, stock, purchase/reward receipts, authorizations, item instances and placements. |
| Personal isolation | Primary purchase leaves peer stock and balance unchanged. Peer rejects primary's authorized item GUID and can buy its own same-index stock into a different physical item GUID. Peer purchase leaves primary economics unchanged. This is not a trade test. |

The command endpoint calls the native merchant selection/distance check and delivery code. The runner never calls the purchase stored procedure. Its observation connection accepts only single SELECT statements. Store owns the synthetic binding/queue writes. GM item and position changes go through native chat commands. No SQL currency, inventory or level mutation, original-character login, GUI control, configuration change, world restart or bot enablement is used.

Before packets, the runner checks command/parser source tokens, hashes the relevant pinned source, compares all four merchant/delivery files with the pinned module, and checks the running world binary SHA-256 `6434b132b68a581a2046319c25795f9f5c1211ab2096b56898702a12542d83e8`. It imports the shared client unchanged, including its persistent 30-second ping schedule and specMask snapshot schema.

## Evidence and current result

Native PASS is recorded in `.local/merchant-live/20261019T174525Z/run.jsonl`. All assertions in the table completed on the pinned binary with fabricated AP ingress. The 15 offline merchant tests, 19 shared runtime tests and 16 shared client tests also pass.

The run used fresh GM0 primary GUID 22 and peer GUID 23, bindings 12/13, and verified reused GM control 13. Loaded merchant runtime GUID was `17379406069905752682`, not spawn ID 9005000. Both bought personal stock index 0, item entry 756, for one voucher each. Separate physical item GUIDs 285/286 were persisted, and both balances are four. Ordinary Thunderfury GUID 270 on the peer returned required-level error 1. Authorized Thunderfury GUID 269 on the primary rejected the head slot and persisted in main hand at level 1. Full-backpack refusal, normal bracer equip, purchase retry, sold/receipt replay and cross-player isolation all passed.

`summary.json` records the run hash, reused ownership-evidence hashes and checkpoints. The final read-only observations in `observed-state.json` and the run's `after.json` confirm GUIDs 13..23 offline, TEST still at 10/10, and APV2D/E each at 4/10 with security 0. Failed fixtures and bindings remain intact. Original GUIDs 1..4 were unchanged across the passing run. The other agent's normal journey on display 94 was not controlled by this runner. No world restart, SQL character mutation, history reset, deletion or raised account limit was used.

Evidence is under `.local/merchant-live/`. Each attempt has its own timestamped directory and JSONL transcript. `.local/merchant-live/latest-run.txt` identifies the latest launched attempt. `unit-tests.log`, `shared-runtime-tests.log`, `shared-client-tests.log` and `plan.json` are offline evidence. Use `.venv/bin/python`; system Python lacks PyMySQL.

Earlier failed fixtures remain preserved. The rejected-teleport attempt kept GUIDs 14/15/16 and bindings 6/7. The asynchronous-position attempt kept GUIDs 17/18/19 and bindings 8/9. The GM success reply was not a commit fence because `PlayerMisc.cpp` queues `CharacterDatabase.Execute`. The corrected helper polls read-only position observations for at most 10 seconds and services the GM ping schedule. Its delayed-success and wrong-height timeout tests pass, and the native replay now reaches actual merchant gossip.

The first authorized-control reuse attempt, `20261019T174230Z/run.jsonl`, kept new players 20/21 and bindings 10/11. It reached the loaded merchant but stopped when native `.additem` refused a second Thunderfury on the primary. Read-only `item-template-observation.json` confirms `MaxCount=1`, `RequiredLevel=60`. The comparison now uses an ordinary instance on the fresh peer and the authorized instance on the fresh primary. No unique-item rule was bypassed.

## Narrow insufficient-funds rerun

The parent authorizes only the existing peer GUID 23, Apsgiylwpuwg, on APV2E account 6, binding 13, from the merchant PASS. Run without creating characters or taking TEST ownership:

```sh
WOWPILAGO_TEST_ACCOUNT_PASSWORD=test-only WOWPILAGO_DB_PASSWORD=test-only \
  .venv/bin/python tests/verify_merchant_runtime.py --run --funds-only owned-peer-23
```

This option pins the creation transcript SHA-256 `701eaa733913ac95ca1a36bbb2573e794d24c13202bf7a640dabe92a2527c98d`, checks its unique fresh peer login event and PASS against `.local/merchant-live/summary.json`, then checks current fixture email, SEC_PLAYER security 0, account ID, offline account/character, exact GUID/name/human warrior/level-1 profile and binding owner/seed. Only then are GUID 23 and its name admitted to the shared runner for existing-character login. No arbitrary GUID option exists. The known runtime merchant GUID is `17379406069905752682`; its actual gossip response must arrive before purchase. No GM, fabricated ingress, SQL writes, GUI control or server restart is used. The ordinary full runner now includes the same funds assertion immediately after the peer's purchase.

The actual funds-only run passed in `.local/merchant-live/funds-20261019-peer23/`. Peer 23 had four vouchers and 13 free backpack slots. Unsold stock index 1, real catalog item 868, cost six vouchers. Merchant gossip arrived from the runtime GUID and native buy returned the expected refusal. Fresh post-logout SELECT snapshots show no item, inventory, voucher, stock, receipt or authorization changes. GUID 23 finished offline; character population and original GUIDs 1..4 were unchanged. `run.jsonl` includes raw gossip/chat packets and snapshots; `before.json`, `after.json` and `summary.json` expose the comparison and evidence hashes. All 17 merchant, 19 shared-runtime and 16 shared-client tests pass. Only the funds-only path was run live for this change; the larger playthrough was not repeated.

## Still open

Real AP-room ingress and gameplay, GUI merchant interaction, other cities/classes, concurrent purchases, transfers/trades, process-crash recovery, combat effects and a normal level-1-to-80 playthrough are not proved by this runner. Do not mark those release gates complete from these fixtures.
