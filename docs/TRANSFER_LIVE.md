# Native mail, auction and same-player item checks

## Status: native refusal and same-player comparison PASS

After the parent released the completed nine-class/DK windows, `20261019T220903.914230Z` exited0 in23seconds. Direct legendary269 and purchased item285 received four native mail refusals and two bound auction refusals. The enabled Alliance auction hello and ordinary-owned-single-item overcount refusal preceded the two AP sell attempts. Exact mail/auction phase snapshots remained identical, with no debit, attachment or listing. Three sell packets were actually sent. There was no completed transfer.

The separate instance run `instance/20261019T221116.444624Z` exited0 in11seconds. Player23 equipped authorized AP286 at level1, then its ordinary525 copy of the same entry756 received error1 and required level24. The denial changed nothing. One ordinary item was created through reserved native GM fixture setup; the comparison baseline starts afterward. See `INSTANCE_EQUIPMENT_RUNTIME.md`, `docs/verification/native-transfer-refusals.json` and `docs/verification/native-instance-equipment.json`.

The first fixed-candidate retry `20261019T220146.649187Z` stopped before any sell packet because a harness waited for offline while its socket remained open. Its failure remains preserved. Shared/transfer login cleanup now closes the socket before waiting, including body/logout/connect exceptions. Order-sensitive tests passed, followed by one native GM13 login with an intentional exception and no commands. That probe returned with exact saved-state equality and everyone offline in `cleanup-probe-20261019T220809.201253Z`.

These are headless fixture proofs, not stock GUI, completed ordinary transfers or a full playthrough. Original characters1..4, the saved real AP session and stopped GUI/bridge remain untouched. The earlier preparation below performed no live operations; its former release prerequisites are not new authorization.

## Preserved earlier evidence

The original `.local/transfer-live/` directories remain unchanged. In `20261019T183643.621382Z`, both AP items returned exact native mail bound errors alone and after the ordinary control. Mail snapshots match. The actual enabled auction hello was house 2, enabled 1. The old expectation used house 1 and stopped the runner. No sale packet was sent.

`20261019T183747.068829Z` repeated all four mail refusals with matching snapshots. The world then exited 139 while the client awaited auction hello. Its transcript hash is `d6a937f904932066a7ec8289cdeb9fc3a0d2acf7ff17666de533a81fdc0a7534`. No `CMSG_AUCTION_SELL_ITEM` was sent. `independent-check.json` and `interrupted-after-select.json` preserve the checks and unchanged interrupted auction state. No listing, transfer or debit was observed. Failed records and the stale online flag were not repaired by this work.

The actual core establishes a null `Player*` in the asynchronous login server-mail callback after logout, NOT an auction parser fault. See [AUCTION_CRASH.md](AUCTION_CRASH.md) for the stack and callback identity. Its deployment-pending language describes that investigation's earlier state, not the parent's later fixed candidate.

The parent subsequently built the combined callback and Artisan fixes. `.local/artisan-runtime-plan/fixed-owner-guard/summary.json` records actual Artisan PASS on fixture 25. `.local/crash-runtime-plan/continuation29/20261019T195911Z/summary.json` records composite PASS with two original world-process SIGKILLs and two fresh relogs, unchanged durable/protected state and no new characters or kills in the continuation. The original failed run remains preserved. Neither result substitutes for auction or same-player evidence, nor releases the current native matrix owner's accounts.

The one-gold setup happened only in `20261019T183515.560707Z/run.jsonl`, SHA-256 `81a103ca41e7f1edcfec64a30c63a4065dd07bf278062fddfe90555cd870a286`. Current expected money for 22 is exactly 10000 copper. The retry verifies that transcript and amount. It has no money command or top-up path.

## Fixed candidate and release gate

`tests/verify_transfer_runtime.py` uses only `.local/v2-build/20261019T191318.518327Z-mail-fixed`. There is no `--build` override. Its pins are:

- World `3b9b2bf9f946a1eeef5908e440ed917132c0559c4bc483ba14be199060641809`, image `sha256:55bfa1750408af5f5645166e47928aac6ecf0be92dd24005411cd96115f18ed9`.
- Manifest `6ac13239c2b11940904ece49ea6064c72980e433d6ef06aff587f36babc51553`, base manifest `0edea8dba721f996f00cf0b5c95e3576fff1ad4dd6e637fd8c0ad45b06f1285b`.
- Combined core patch `76342b88b9864f85525771ba51de7c2b78467343027075b83184bc76356aca6c`, Artisan `APProgression.cpp` `85e1a31476fe3d918dd61bfba685401c520707d72dcc3d4579788c3b4baa83c7`.

The runner reuses Artisan's `build_evidence` for commit/image/protocol, all module hashes, working-tree/archive agreement, source inventory and installed-file checks. It additionally verifies the fixed manifest, combined patch, base provenance and transfer/item/command/callback source hashes against that inventory. Runtime checks reuse Artisan's helper for the running private compose service, exact image, read-only fixed install mount, `/proc/1/exe` and installed world hashes. The old `6434b...` binary and 15:06 archive are historical evidence only.

Before any future authentication, the parent must create `.local/transfer-fixed-plan/release.json` with `owned_release`, `gui40_released`, `mail46_released` and `native_matrix_released` all boolean true; `world_sha256` equal to the fixed hash; a nonempty `release_id`; and timezone-aware `issued_utc` and `expires_utc`. The issuance must already have occurred, the expiry must be in the future, and the entire grant lasts at most 1800 seconds. No usable release file is supplied by this preparation. The parent must explicitly release matrix ownership, not merely observe no packets.

Both runners check the grant before runtime checks and again before every authentication. Before fixture reuse they require ALL character and account online flags to be zero. Existing strict merchant creation proof, fixture account markers/security, human-warrior profiles, binding IDs and seeds remain mandatory. `authenticate(..., ready_timeout=30)` bounds realm readiness. The shared helper's default zero and shared Runner's existing timeout/profile behavior are unchanged.

## Transfer retry

Only existing 22/APV2D/account 5/binding 12 and 23/APV2E/account 6/binding 13 are admitted. Ownership remains pinned to the merchant creation PASS transcript `701eaa733913ac95ca1a36bbb2573e794d24c13202bf7a640dabe92a2527c98d`. GM13 still needs its original trusted class-system creation/release evidence. No creation fallback, arbitrary GUID/account, SQL gameplay write, repair or reset exists. Peer23 remains offline as mail recipient during this runner.

Native GM teleports and summons happen before each phase baseline. The runner re-queries `.gobject info guid 100156` and `.npc info 79705` after setup to obtain actual loaded runtime GUIDs. Spawn database IDs are lookup arguments, not runtime counter IDs. Old low IDs such as 1011, 466 or test counter 123 must never be reused after restart.

Mail uses observed mailbox entry 195603 and zero money/COD to owned `Apsgiylwpuwg`. It tests AP269 and AP285 alone and after ordinary256. Only exact `SMSG_SEND_MAIL_RESULT (0,0,1,72)` passes. Ordinary-only successful mail is blocked. The mixed attachment loop gives source-backed preceding validation of ordinary256, not a completed ordinary transfer.

Auction hello must return the observed auctioneer GUID, Alliance house 2, enabled 1. First send ordinary unbound256 with quantity TWO against factual owned count ONE. Then send bound AP269 Thunderfury and AP285 Tunnel Pick individually with quantity one. The packet allowlist prohibits ordinary quantity one and all other listing routes. Each expected result is `SMSG_AUCTION_COMMAND_RESULT (0,0,2)`. Auction code 2 is shared, not independently causal proof of binding.

Source-backed preconditions matter. Every tracked item is owned by 22, count one, duration zero, without enchantments or an existing attachment/listing. Ordinary256 has flags zero and is in backpack24; AP269/285 have flags exactly one and exact authorization. Weapon templates are not bags, conjured or account-bound. Native owned-item lookup precedes the combined `CanBeTraded`/quantity guard. Binding rejects AP items at `CanBeTraded`; ordinary count one is below the requested two. Deposit computation is later, and insufficient-money error is code 3. Equipment required-level checks do not run on this path. Code 2 alone proves neither a successful ordinary listing nor a unique refusal branch.

Each phase takes full before/after SELECT snapshots after setup and normal logout. Inventory, item rows, authorizations, rewards, purchases, stock, vouchers, spells, level/XP/money, account markers/security, bindings, mail/attachments/listings, original characters and population must match exactly. Directional payloads, native GUID queries, source/runtime evidence and snapshots are retained in a NEW timestamped directory under `.local/transfer-fixed-plan/`. A failed attempt stays failed. There is no history cleanup.

## Same-player instance proof after auction PASS

`tests/verify_instance_runtime.py` is separate so expected equipment swaps do not weaken transfer's unchanged-snapshot checks. It first requires a hash-verified fixed-candidate transfer PASS. It reuses the same parent release gate and strict 22/23/GM13 ownership checks.

Peer23 already owns purchased, authorized AP756 GUID286. Before setup the runner checks level-one human warrior, normal two-hand axe skill172 at 1/5, purchase receipt and exact authorization. Actual template756 must be weapon class2, subclass1, two-hand inventory17, required level24, no separate required skill/rank and nonunique `MaxCount=0`. No race/class/level/skill/proficiency setup is allowed.

The only setup command is GM13 selecting 23 and issuing `.additem 756 1` ONCE. Before authentication for setup, an exclusive persistent `instance/setup-reservation.json` reserves that one attempt. A second add is blocked even if transport fails. Any interruption before a complete attestation requires parent inspection, not deleting the reservation or retrying the command.

After logout, exactly one NEW ordinary756 GUID must be owned by23, count one, flags zero, unequipped and absent from all entry756 authorizations. Setup may change only that item and its inventory row. `setup-attestation.json` records the exact instance and no-authorization acknowledgment, with hashes of `setup-before.json`, `setup-after.json` and `setup-command.json`. Reruns reuse only this exact instance and proof. No other ordinary copy is accepted or added.

The test baseline is AFTER setup. Native `CMSG_AUTOEQUIP_ITEM_SLOT 0x10f`, payload uint64 item GUID plus uint8 destination15, equips AP286 at level1. After logout it must persist in mainhand15 and original starting49778 GUID266 must naturally swap from mainhand15 into AP286's former backpack25. No other saved state may change. A fresh login sends the SAME opcode/destination for the attested ordinary756 on the SAME player23. It must return exact native level error1, naming that ordinary GUID and required level24, and leave the equipped snapshot unchanged. Authorization, skills, class, profile and economics must remain unchanged throughout.

This closes the earlier Thunderfury comparison's other-player limitation without creating another unique Thunderfury. It does not claim ordinary authorization or a per-entry/per-player bypass. Wrong-slot coverage is not repeated; the previous TF head-slot check remains separate. A run that has already equipped AP286 cannot replay the initial positive transition without reset; it stops rather than rearranging equipment. Persistent setup still prevents a duplicate add.

## Checks and future execution

1. Offline only: `PYTHONPATH=tests .venv/bin/python -m unittest test_transfer_runtime test_instance_runtime test_trade_runtime test_runtime_runner test_realm_client`. This preparation passed 72 tests, including source pins, release freshness, all-offline gates, exact packets, ownership, one-shot reservation and native source facts.
2. Parent action only: obtain explicit release of all native matrix ownership and a fresh exclusive grant, verify all offline. Do not authenticate while matrix owns GM13/accounts. No release is inferred from prior Artisan/composite PASS.
3. Only after that release: `WOWPILAGO_TEST_ACCOUNT_PASSWORD=test-only WOWPILAGO_DB_PASSWORD=test-only PYTHONPATH=tests .venv/bin/python tests/verify_transfer_runtime.py --run`.
4. Only after actual fixed transfer PASS and while the grant remains fresh: use the same command environment with `tests/verify_instance_runtime.py --run`. Without `--run`, either script prints a network-free plan.

The SQL guard is application-side SELECT-only; root at private port13317 is not a database-enforced read-only principal. Release attestations and offline guards are not a concurrency lock. Transport loss can prevent normal logout and final snapshots. Preserve failures and ask the parent to inspect, never repair/reset automatically. No live AH refusal, same-player result, real AP ingress, GUI playthrough, completed mail or successful auction listing is claimed here.
