# Native trade refusal

## Result

PASS on existing owned fixtures 22 and 23, with no creation, GM setup, SQL writes, movement, item disposal or completed trade. Both AP items failed the native tradable-slot-0 offer path. Each attempt first proved the same session's target handshake and an unbound positive offer, then ended with CANCEL.

Evidence directory: `.local/trade-live/20261019T182520.981914Z/`.

- `run.jsonl` contains 236 directional CMSG/SMSG payload records, parsed trade replies, source/module hashes and before/after SELECT snapshots. Packet headers are decrypted by the imported client; `raw` is the complete opcode payload, not a network capture.
- `before.json` and `after.json` are identical. They include both inventories and complete item-instance rows, AP bindings, account markers/security, progress, rewards, purchase receipts, stock, authorization, spells and character level/XP/money. Character population and original GUIDs 1..4 also match.
- `summary.json` reports PASS and transcript SHA-256 `9fd531268af15d66541121669739f76b58025d76815c04b7a2588360a19e71fd`. `independent-check.json` records a separate hash, packet-policy and snapshot comparison.

Both fixtures finished offline after normal `CMSG_LOGOUT_REQUEST`, successful `SMSG_LOGOUT_RESPONSE` and `SMSG_LOGOUT_COMPLETE`. There was no CMSG acceptance, character creation, chat command or trade-money packet. Voucher balances remained four each. Authorized Thunderfury 269 and purchased Tunnel Pick 285 remain owned by 22; ordinary Thunderfury 270 and purchased pick 286 remain owned by 23. Item flags, placements and all AP economics are unchanged.

## Observed protocol

Both level-1 human warriors were already at map 0, `-8833.38, 628.628, 94.0066`. No teleport or movement was needed.

For each pair, 22 sent `CMSG_INITIATE_TRADE 0x116` with target GUID 23. Peer 23 received `SMSG_TRADE_STATUS 0x120`, status 1 and trader GUID 22. Peer 23 sent `CMSG_BEGIN_TRADE 0x117`; both received status 2, OPEN_WINDOW.

| Pair | Positive control offered first | AP offer refused next |
| --- | --- | --- |
| Equipped | Recruit's Shirt, GUID 250, entry 38, equipment slot 3 | Authorized Thunderfury, GUID 269, entry 19019, main-hand slot 15 |
| Backpack | Worn Greatsword, GUID 256, entry 49778, slot 24 | Purchased Tunnel Pick, GUID 285, entry 756, slot 38 |

SELECTs verified both control item flags were zero and real templates had bonding zero. Both AP item flags were exactly 1, soulbound, without BOP-trade flags. Their authorization rows and placements were checked before login.

`CMSG_SET_TRADE_ITEM 0x11D` carries three bytes: trade slot, packet bag, inventory slot. The four payloads were `00ff03`, `00ff0f`, `00ff18`, `00ff26`. Database inventory bag 0 maps to native `INVENTORY_SLOT_BAG_0 = 255`, not packet bag 0.

Each positive control produced owner status 7, BACK_TO_TRADE, and peer `SMSG_TRADE_STATUS_EXTENDED 0x121` with view 1 and the expected entry/count in trade slot 0. The pinned `TradeData::SetItem` sends the item update to the peer, not an own-view extended packet. The parser checks the 21-byte header and seven 73-byte item records.

Each subsequent AP offer returned exactly status 3, TRADE_CANCELED, to 22, with no extended item update and no inventory error. Native rejection sends this status but does not itself destroy the server's trade data. The control therefore remained in the offer. The runner explicitly sent `CMSG_CANCEL_TRADE 0x11C` and required status 3 on both sessions before starting the next pair. Neither control moved out of its original inventory position.

## Why this isolates binding

The inspected pinned source is `.local/v2-build/20261019T150600.624050Z/source/`. The transcript hashes `TradeHandler.cpp`, `TradeData.cpp/.h`, `Item.cpp`, `PlayerStorage.cpp`, `Player.h`, `SharedDefines.h`, `ChatHandler.cpp` and `Opcodes.h`. Chat opcodes are `CMSG_MESSAGECHAT 0x095` and `SMSG_MESSAGECHAT 0x096`; the runner blocks outgoing chat commands entirely.

`HandleSetTradeItemOpcode` looks up the factual bag/slot and calls `CanBeTraded(false, true)` for tradable slots. A false result sends status 3 before the module trade hook or `IsBindedNotWith` check. In `Item::CanBeTraded`, soulbound items without BOP-trade permission return false immediately, before `CanUnequipItem`. Flags exactly 1 establish that first condition for both tested AP items. The later module `OnPlayerCanSetTradeItem` protection would instead return CLOSE_WINDOW, status 12, and was not the observed branch.

Thunderfury's template requires level 60 and the pick requires level 24. Neither required-level check runs on this native offer path. `CanUnequipItem` also has no required-level check, and the binding check returns before it here. Successful equipped and backpack controls prove that target, proximity, handshake, bag encoding and ordinary offering work. Generic failure alone would not pass this runner.

This proves refusal to enter the transferable offer and unchanged persistence after cancellation. It does not claim an attempted completed transfer: acceptance was deliberately prohibited. Native slot 6 is nontraded enchantment handling and bypasses this native tradable-item check; module policy may still reject it. Slot 6 was not tested.

All eight module `.cpp`/`.h` files matched the pinned module before and after the run. The running world binary remained SHA-256 `6434b132b68a581a2046319c25795f9f5c1211ab2096b56898702a12542d83e8`. No world restart, config/native edit or AP fake ingress was used.

## Ownership and bounded rerun

The runner admits only GUID 22, Apsqlkruenob, APV2D/account 5/binding 12, and GUID 23, Apsgiylwpuwg, APV2E/account 6/binding 13. It pins `.local/merchant-live/20261019T174525Z/run.jsonl` to SHA-256 `701eaa733913ac95ca1a36bbb2573e794d24c13202bf7a640dabe92a2527c98d` and checks its unique PASS against `.local/merchant-live/summary.json`, the existing summary location. It validates unique fresh creation events for both GUIDs/names, binding creation seeds and prior offline release. Current SELECTs must match exact names/accounts, fixture email marker, security 0, offline account/character, human warrior level-1 profiles and exact binding ownership/seed. Both must validate before either is admitted.

The shared client's login guard and persistent 30-second ping implementation are imported unchanged. An outgoing opcode allowlist blocks creation even if enumeration fails to find the existing fixture. TEST/13, the busy pilot and GUI are never used. SQL observation uses root at private test port 13317, with the inherited SELECT-only query guard. Root is not a database-enforced read-only principal; this script issues no SQL writes.

1. Print the offline plan: `PYTHONPATH=tests .venv/bin/python tests/verify_trade_runtime.py`.
2. Run checks: `PYTHONPATH=tests .venv/bin/python -m unittest test_trade_runtime test_runtime_runner test_realm_client`. Current result: 11 trade tests and 35 shared tests pass.
3. Coordinate exclusive ownership of accounts APV2D/E, then run:

   ```sh
   WOWPILAGO_TEST_ACCOUNT_PASSWORD=test-only \
   WOWPILAGO_DB_PASSWORD=test-only \
   PYTHONPATH=tests .venv/bin/python tests/verify_trade_runtime.py --run
   ```

Each run creates a new evidence directory under `.local/trade-live`. Failures retain the transcript and fixtures without repair/reset. Normal logout and after-snapshot collection run on assertion failures once sessions are connected. A transport failure can still prevent normal logout; offline observation must then succeed before any claimed PASS. Offline SELECT guards are not a lock against another operator.

## Remaining gates

Mail and auction-house routes need separate money/NPC prerequisites and were not exercised. No completed-transfer attempt, nontraded-slot test, real AP-room ingress or gameplay/playthrough claim is made here. Existing wrong-owner equip refusal is separate evidence, not a substitute for this trade test.
