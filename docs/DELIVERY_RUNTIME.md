# Native delivery runtime

`src/APDelivery.h` and `.cpp` replace the protocol-1 fixed-potion delivery path. They do not register themselves through the existing loader. The parent must compile `APDelivery.cpp`, call `WoWPilago::RegisterDeliveryScripts()` once alongside progression registration, and remove the old `ArchipelagoDelivery` implementation from `mod_archipelago.cpp`. Never register both delivery workers. No bridge, catalog, schema, progression, merchant, or loader files were changed here.

## Public API

All calls run on the world thread. No Player pointer, item pointer, or State reference survives the blocking call. The world-update poll runs every 5 seconds, resolves online characters afresh, rejects bot/loading/closing/teleporting sessions, and processes pending protocol-2 receipts. There is no global LIMIT that lets one group of full inventories starve another character's rewards.

| Function | Result |
| --- | --- |
| `ApplyQueuedReward(Player*, uint32 index, uint32 sender)` | True only for a newly applied, durably verified reward. Sender must match the queued row. |
| `BuyStock(Player*, uint16 stockIndex)` | True only for a newly committed, verified purchase. Entry and price come from that character's saved stock and must match generated gear policy. |
| `EquipAuthorized(Player*, uint32 itemGuid, uint8 equipmentSlot)` | True when normal `SwapItem` leaves the authorized item in the requested equipment slot. |
| `UseAuthorized(Player*, uint32 itemGuid)` | True means submitted to the normal core item-use handler, not that a spell cast succeeded. |
| `RegisterDeliveryScripts()` | Registers the startup validation and world-update poll. |

Already applied rewards and sold stock return false without generating a candidate, issuing items, debiting, or repeating notifications. Historical receipt GUIDs can outlive a consumed/deleted item. Sold-stock replays require a matching durable entry/price receipt. An in-flight receipt pointing at a different candidate is not adopted or regranted: it fails stop as an unexpected concurrent writer.

Merchant and CLI callers must use these functions rather than implement another issuance path. False does not mean a database debit needs compensation. It means no new application/publication was reported. Startup rejects missing/non-InnoDB participating tables, wrong 21/16-argument procedure counts, and multiple CharacterDatabase workers. Progression also enforces the worker setting at config reload.

## Persistence and publication

1. Validate the queued AP ID against `State.allowedRewards` and generated `Rewards`, including the exact normalized kind/value and class mask. The bridge cannot turn an allowed generic AP ID into another effect or a class-incompatible ability/legendary. Validate merchant entry, price, non-legendary quality and class mask against generated `Gear`.
2. For physical work, find an empty backpack/equipped-bag destination with `CanStoreNewItem(entry,count)`. Require one exact destination for the entire count. Create a detached generic `Item` or `Bag`, retain its generated identity/random properties, bind authorized gear and clear refund/trade flags. Remove the detached candidate from the player's update queue before saving. No stacking, replacement, or automatic bag equip occurs.
3. Call the full transactional `Player::SaveToDB(trans,false,false)`, including the patched progression bank/level hook. Commit through the single asynchronous worker and wait. Confirm character/profile/progress and every saved inventory item, including equipped parents, bank bags and their contents. The inventory check compares complete serialized SQL metadata and exact placements/counts. A false save result or failed confirmation aborts because core may already have cleared dirty item states.
4. Submit the entire 21-argument reward or 16-argument purchase CALL with `CharacterDatabase.Execute` on that same worker. The CALL owns its transaction; there is no surrounding transaction. Follow it with ordered asynchronous queries and wait for their callbacks. A ready future or successful driver return is not evidence of application.
5. Confirm the receipt/sold state and exact applied value/GUID/entry/price, the complete expected character/progress transition, and candidate item ownership, entry, count, all serialized metadata, placement, and authorization. A pending outcome must leave the pre-CALL snapshot unchanged and have no candidate item, placement or authorization. Publish only a fully verified committed outcome. Any unavailable or contradictory outcome calls `ABORT()` before another player save can overwrite committed SQL state.

The ordered query helper deliberately blocks the world thread and polls callback readiness at 1 millisecond intervals. This relies on the pinned world's update occurring after map workers finish and on one realm owning this queue. No other native or bridge writer may apply these effects concurrently. A multi-realm deployment needs a lease and a different concurrency design, not a second worker.

The SQL strings use the core's escaping API. Module-owned routines/tables have no core prepared-statement enum entries. Arbitrary text fields are never concatenated without escaping.

## Effect policy

Bag rewards deliver one entry 21841. Consumables deliver five of 118/858/929/1710/3928/13446/33447 at actual-level thresholds 1/3/12/21/35/45/70. Direct legendaries deliver their generated named entry and authorize only that instance. Purchased and legendary items are soulbound, without BOP tradeability or refundability, before SQL persistence and before publication.

The CALL receives current saved money, never a gold delta. SQL scales gold and handles capacity. Native's independent expected-outcome calculation verifies credited copper. Native passes `sObjectMgr->GetXPForLevel(savedLevel)` for cap release. Only a verified cap receipt publishes committed `PLAYER_XP`; it never calls `GiveXP`, applies bonuses again, or grants a level. Ceiling receipts and early cap receipts follow SQL's exact bank/XP behavior.

State-only calls pass zero for every numeric item argument, including bag slot, and empty strings for charges, enchantments and text. Physical backpack calls use bag slot 255 and parent GUID zero. The shared serializer emits all fourteen arguments after reward entry/count or purchase binding/index: GUID, parent GUID, parent slot, slot, creator, gift creator, signed duration, charges, flags, enchantments, signed random property, durability, played time, text. The resulting public calls contain exactly 21 and 16 arguments.

On success, native publishes saved money/XP, calls `RefreshState`, stores the already persisted detached item without creating another GUID, then calls `Reconcile`. Progression handles early ability/riding/talent permissions, vouchers and future eligibility. Failed/full-bag/insufficient-capacity work neither refreshes over the live bank nor clears it. No success message or item glow is sent for pending work.

## Client fallback and receipts

Equipment fallback requires the actual owned authorized instance in inventory or equipment. It uses `SwapItem`, not `EquipItem` or an equip-error override. The patched `IsAuthorized` hook bypasses only required level. Normal class, proficiency, skill, unique, combat and other swap restrictions remain. Bank-source commands are deliberately rejected even at a banker; move the item into ordinary inventory using normal bank interaction first.

Item-use fallback selects an ON_USE spell from the actual item's template. It checks normal item usability and equipped-state requirements, constructs a server-owned CMSG_USE_ITEM packet with the selected unit or self, and calls `WorldSession::HandleUseItemOpcode`. No user-selected spell ID, GM cast, or `TRIGGERED_FULL_MASK` path exists. Core still owns cooldowns, charges, scripts, targets, cast eligibility and errors.

Explicit targets other than unit/self are rejected with a clear chat message. Ground, source/destination, item-enchant, gameobject and other specialized-target items need audited catalog/target support before this fallback can handle them. This is not full ON_USE coverage. The first ON_USE spell drives the packet; the normal core handler handles the item's spells. A successful dispatch does not promise a successful cast.

After verified publication, native sends a normal GUID-overload addon self-whisper with prefix `WOWPILAGO`, not a GM chat packet:

```text
WOWPILAGO\tITEM\tindex\tentry\tsender
WOWPILAGO\tSTATE\tindex\tap_id\tapplied_value\tsender
WOWPILAGO\tSHOP\tstockIndex\tentry
```

Physical publication also sends the normal new-item notification. State receipts send readable chat naming the reward, current cap and voucher balance. The parent/addon agent owns addon receipt display and deduplication. SHOP uses stock indices, never AP receipt indices. Disconnect/crash after commit but before notification may lose the notification, not the item/effect. Replays do not promise notification recovery.

## Executed verification and remaining gates

`python3 -m unittest discover -s tests -p test_native_delivery.py -v` passes four tests. They compile production header policy and extracted production serializer, ordered-query helper and candidate verification into executables with C++17, `-Wall -Wextra -Werror`, and undefined-behavior sanitization. Coverage includes all generated reward/class combinations, forged IDs/kinds/values, every potion/gold boundary, cap/talent ceilings, early/capped XP release, unrelated bank preservation, exact empty/physical argument serialization, metadata escaping, incomplete item/placement/authorization outcomes, and unavailable-query fail-stop behavior. Core/DB doubles exercise these extracted functions only, not actual Player or MySQL behavior.

`APDelivery.cpp` compiled to an object with `-O0 -g0 -Werror` in `wowpilago-module-check:latest`. The compile mounted a fresh archive of pinned commit `9fb906bb7296212ff42fc95ff73a92aaf8554f0d`, patched with `tools/apply_core_patch.py`, read-only at `/core`; it did not substitute the image's newer base source. The core C++ codestyle script passed on this project's `src` directory. Host core source was not edited.

Remaining runtime gates belong to the parent realm run. None are claimed passed here:

- Link and start the combined loader/progression/delivery/merchant build with the updated bank save hook and one DB worker.
- Exercise every reward and purchase against real character/inventory tables, including full bags, pending money/voucher capacity, bag-family restrictions, saved parent movement and existing refundable/random-property items.
- Inject CALL rollback, deadlock, disconnect before/after COMMIT and failed confirmation; prove full-save/unknown-outcome fail-stop and restart recovery without stale bank/XP/money/item overwrites or duplicate grants.
- Test low-level equip and ON_USE with a stock 3.3.5a client, wrong class/proficiency, offhand swaps, combat, cooldowns, selected/self targets, ground-target rejection, ownership and bank rejection, and transfer restrictions.
- Verify addon ITEM/STATE/SHOP handling and human-only polling in the integrated realm. Selfbots with ordinary sessions remain outside the available `WorldSession::IsBot()` contract.

The synchronous world-thread waits and full-inventory confirmation are correctness-first and can pause a busy realm. Measure this before increasing deployment scale. Unit executions and object compilation do not establish a release-ready full TODO implementation.
