# Protocol 2 SQL effects

Import `sql/v2.sql`, then `sql/v2_effects.sql` into CharacterDatabase using a schema administrator. All involved tables must use InnoDB. The schema installs one `BEFORE DELETE` trigger on `characters`, in addition to the AP tables. MySQL 8.4 is tested. The trigger definer must retain the privileges needed to read the old GUID and update the binding. Do not grant schema privileges to the bridge.

Existing realms need a reviewed trigger migration. The private provisioner still refuses changed source receipts and unverified existing objects. It does not automatically migrate the running realm. Reimporting the routine file replaces procedures, not history.

## Exact public signatures

```sql
mod_archipelago_v2_apply_reward(
    p_binding BIGINT UNSIGNED,
    p_index INT UNSIGNED,
    p_level TINYINT UNSIGNED,
    p_money INT UNSIGNED,
    p_next_xp INT UNSIGNED,
    p_item_entry INT UNSIGNED,
    p_count INT UNSIGNED,
    p_item_guid INT UNSIGNED,
    p_bag_guid INT UNSIGNED,
    p_bag_slot TINYINT UNSIGNED,
    p_slot TINYINT UNSIGNED,
    p_creator INT UNSIGNED,
    p_gift INT UNSIGNED,
    p_duration INT,
    p_charges VARCHAR(64),
    p_flags INT UNSIGNED,
    p_enchantments TEXT,
    p_random SMALLINT,
    p_durability SMALLINT UNSIGNED,
    p_played INT UNSIGNED,
    p_text TEXT
)

mod_archipelago_v2_purchase(
    p_binding BIGINT UNSIGNED,
    p_stock_index SMALLINT UNSIGNED,
    p_item_guid INT UNSIGNED,
    p_bag_guid INT UNSIGNED,
    p_bag_slot TINYINT UNSIGNED,
    p_slot TINYINT UNSIGNED,
    p_creator INT UNSIGNED,
    p_gift INT UNSIGNED,
    p_duration INT,
    p_charges VARCHAR(64),
    p_flags INT UNSIGNED,
    p_enchantments TEXT,
    p_random SMALLINT,
    p_durability SMALLINT UNSIGNED,
    p_played INT UNSIGNED,
    p_text TEXT
)
```

Every parameter is `IN`. There are exactly 21 and 16 parameters. Neither procedure returns a result set. `mod_archipelago_v2_insert_item` is an internal helper with an OUT boolean and no transaction control. Never invoke it directly from the bridge or native module.

State-only rewards require every item parameter, starting at `p_item_entry`, to be zero or the empty string for string fields. In particular `p_bag_slot=0`, not 255. Physical delivery into the backpack uses `p_bag_guid=0`, `p_bag_slot=255`, and `p_slot=23..38`. Equipped bag delivery uses the persisted parent GUID and equipment slot 19..22. The helper locks and verifies the owned equipped parent, then locks the destination and uses plain INSERTs. An occupied destination is a normal pending outcome, never replacement or merging.

Native must use `CanStoreNewItem` to select an empty destination with valid template capacity and bag-family compatibility. SQL verifies parent identity/ownership and a maximum slot of 35, but cannot infer template capacity from the character schema. Do not supply arbitrary inner-bag slots. The helper preserves serialized item fields, except authorized gear flags described below. Metadata must not be NULL.

## Reward policy

The transaction locks binding, queued reward, allowed reward ID, saved character, and progress. Purchase locks binding, stock, character, and progress. Both serialize inventory decisions through the saved character lock. A pending reward requires a nonarchived protocol-2 binding, an allowed AP ID for that binding, and matching saved character class, race, and account. `p_level` must equal saved `characters.level`, be 1..80, not decrease below `last_level`, and not exceed the earned cap. A bank below cap is rejected. Disconnected bindings may receive effects; archived or deleted characters may not.

| Kind | Normalized value | Effect |
| --- | --- | --- |
| level_cap | 10 | Increment cap count to at most 7 |
| outland / northrend | 1 / 2 | Set access bit 1 / 2 |
| riding | 0..4 | Set corresponding bit, without learning a spell |
| talent | 1 | Increment unlock count to at most 12 |
| ability | Base spell ID | Insert permission once, without learning a spell |
| vouchers | 1, 3, 5 | Add that amount |
| bag | 21841 | Deliver one Netherweave Bag |
| gold | 1 | Add scaled copper |
| consumable | 1 | Deliver five scaled healing potions |
| legendary | Item entry | Deliver one item and authorize its GUID |

Permission rows and flags do not bypass riding, talent, spell level gates or prerequisites. Native owns those gates. The installed allowed-reward catalog and queued normalized kind/value are trusted bridge data; SQL checks allowed membership and normalized values, not an independent compiled AP catalog.

Gold uses saved levels 1..9 = 1,000 copper; 10..19 = 10,000; 20..39 = 50,000; 40..59 = 200,000; 60..69 = 500,000; 70..80 = 1,000,000. `p_money` must match saved money for gold. Insufficient capacity below 2,147,483,647 leaves the entire reward pending, with no partial credit. Voucher overflow likewise stays pending.

Potion thresholds were read from the local pinned `acore_world.item_template` on port 13317. Each stacks to 20. Policy chooses the highest eligible entry, delivers five, and verifies caller entry/count exactly.

| Minimum level | Entry |
| --- | --- |
| 1 | 118 |
| 3 | 858 |
| 12 | 929 |
| 21 | 1710 |
| 35 | 3928 |
| 45 | 13446 |
| 70 | 33447 |

Only a cap increase while the saved level equals the old cap releases banked XP. It clears the bank and sets saved XP to `min(bank, floor(p_next_xp/2))` in the receipt transaction. `p_next_xp` must be nonzero in that case and must come from native's next-level XP table. Early cap receipts leave ordinary XP unchanged. SQL never changes character level, awards milestones, or sets victory. Native bank/save/check logic must use the same ordered persistence path so a stale save cannot restore a cleared bank.

Applied receipts record timestamp, `applied_value`, and physical `item_guid`. Applied values are credited copper, voucher amount, physical count, cap increment 10 or 0 at ceiling, talent increment 1 or 0 at ceiling, or the normalized flag/spell value. Replays return before considering candidate GUIDs, even after character deletion. Pending rows cannot apply after deletion. The schema's `mod_archipelago_archive_character` trigger archives and detaches only the deleted character's binding before the FK clears ownership. Its update shares the character DELETE transaction, so rollback restores both. It does not depend on a successful native lookup and sees a binding created after an earlier lookup miss. Unrelated NULL bindings and all binding-keyed histories stay unchanged. The native callback remains a fallback for older schemas, where its documented lookup limitations still apply. This covers physical deletion, not soft deletion or restoration. Deleting an item removes its authorization through the existing FK, but leaves historical receipt GUIDs intact.

## Purchase and authorization

Entry and price come only from locked stock. Insufficient vouchers or occupied destination returns normally with no changes. Delivery, voucher debit, sold flag, receipt and authorization commit together. SQL failures roll everything back and propagate the error. Duplicate GUIDs and inconsistent preexisting receipts are errors, not replacement grants. A sold stock replay requires its receipt and ignores a different candidate GUID.

Purchased gear and direct legendaries force SOULBOUND and remove BOP_TRADEABLE and REFUNDABLE. Source proof is the pinned core's `src/server/game/Entities/Item/ItemTemplate.h:107..121`: flags are 1, 256 and 4096. SQL applies `(flags | 1) & 4294962943`, clearing exactly the latter two bits. Authorization joins item GUID, binding and entry; native must also verify current item ownership and active character binding. No template-global level exemption exists. Native owns transfer restrictions and the required-level-only equip bypass.

## CharacterDatabase integration contract

1. Require `CharacterDatabase.WorkerThreads=1` and InnoDB. Pause overlapping effect attempts for the character. Save current character state and parents through the ordered asynchronous worker before submitting the CALL. Capture level/money and serialized candidate fields from that save. Escape strings through the core database API.
2. Enqueue the whole CALL on that same asynchronous CharacterDatabase worker. Do not run it on a synchronous pool connection or split it into individual statements. The procedures own START TRANSACTION, COMMIT and ROLLBACK. START TRANSACTION commits an existing transaction, so never wrap a CALL with unrelated writes in a supposed outer transaction.
3. Queue receipt/progress/item confirmation after the CALL on that worker, using the existing ordered query callback pattern. A CALL returning no SQL error does not prove application: full bags, insufficient funds and money capacity intentionally leave work pending. Confirm exact receipt, GUID, owner, entry, placement and authorization before publication. Reload saved progress and money rather than calculating the effect a second time.
4. Publish inventory and progress to the live player only after confirmed durable outcome. On replay, load the receipt's actual GUID, not the discarded candidate. If confirmation is unavailable or contradictory, stop or disconnect before a player save can overwrite committed SQL state. Serialize level changes, money changes and bank saves with this path.

The inspected driver at `src/server/database/Database/MySQLConnection.cpp:175..200,555..650` retries the entire Execute string after connection loss. A commit may already have happened. This is why idempotency is per whole CALL, not per individual INSERT. Deadlocks are not retried by bare Execute; retry the complete CALL through native's ordered pending-work path. Execute does not consume arbitrary result sets. All SELECTs inside these procedures use INTO, and neither CALL emits result rows. The completion status is checked by a separate ordered query. Do not add debugging SELECTs to the procedures.

This file does not change the native or bridge implementation. Their owners must wire and verify the contract above. No additional column or bank/check helper is proposed.

## Reproducible SQL evidence

Use a running, dedicated MySQL sandbox. The test recreates its fixture tables. Keep unrelated data out of the owned test schemas.

```sh
WOWPILAGO_TEST_DB_PORT=13318 WOWPILAGO_DB_PASSWORD=test-only \
  .venv/bin/python -m unittest discover -s tests -p test_v2_effects_sql.py -v
```

Both the port and password must be explicit. Missing either skips the SQL cases. Two connection-mock tests still run and verify that a missing port cannot fall back to the realm.

The latest isolated MySQL8.4.11 run passed all32 tests across `test_bridge_v2` and `test_v2_effects_sql`. The effects module includes15 SQL cases and two connection-mock tests. See `docs/verification/goal-ecbd80-offline.json`. The earlier15-case run took108.682seconds. `information_schema.PARAMETERS` confirms the exact ordered21/16 public signatures, also asserted by the suite.

The test connects only to `127.0.0.1` at the supplied port as root with the environment password. It writes only the per-process `wowpilago_v2_test_<pid>` schema, recreates its fixture tables, and installs both SQL files. No original realm character or world database is mutated. Fixtures use legal class/race profile1 and JSON `{}` manifests, without a compiled catalog dependency.

Coverage includes all kinds, both progression ceilings, early permissions, 204 vouchers across 88 receipts, XP release without level/victory, potion/gold boundaries, full destinations, owned bag parents, profile/allowed-ID checks, duplicate candidate GUIDs, two bindings' separate stock, concurrent purchase, failures at every purchase INSERT and reward receipt update, mid-CALL connection kill and replay, no result sets, and nullable character GUID/history preservation. The committed replay tests exercise the ambiguous-after-commit case at the SQL state boundary; they do not inject a network cut precisely between COMMIT and its response. Native publication, real player saves, bag template compatibility and level-gated learning require native integration tests.
