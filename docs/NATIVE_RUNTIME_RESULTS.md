# Native progression fixture results

## Scope

The private linked worldserver executed these checks on a new security-0 fixture character. `tests/verify_runtime.py --run --account APV2B --setup` used fabricated AP ingress and authenticated GM setup. This is native callback verification, not legitimate AP gameplay, a complete playthrough, or proof of real quest difficulty.

The successful fixture is GUID 9, binding 4, named `Apsvbwuiwevq`. Its seed is `fabricated-native-smoke-8e86aef3e5750a13eec1eee5`. The normal playthrough character GUID 4 and original characters GUIDs 1, 2, and 3 were not used as targets.

## Observed results

| Native path | Observed result |
| --- | --- |
| Actual level-10 quest XP award at cap 10 | Level stays 10, ordinary XP stays 0, bank receives 10 XP. |
| Actual AP cap receipt | Cap becomes 20, bank clears, ordinary XP becomes 10, level stays 10. |
| Selected ability before AP permission | Charge spell 100 remains absent after the setup actor attempts learning. |
| Selected ability after AP permission and eligible level | Charge persists with specMask 255. |
| Apprentice permission received before level 20 | Permission bit persists; riding spell 33388 remains absent at level 10. |
| Talent permission received early | One permission persists; the actual level-10 talent packet reports the normal one point, not an extra point. |
| Voucher effect | Exactly five vouchers persist. |
| Direct bag effect | One bound Netherweave Bag, entry 21841, instance GUID 130, backpack slot 24. |
| Direct legendary effect and normal-player equip command | Bound Thunderfury, entry 19019, instance GUID 131, main-hand slot 15 at actual level 10. |
| Purchase without a selected nearby merchant | Refused, stock unsold and no debit or purchase receipt. |
| Identical ingress replay, full logout, and relogin | Progress, exact seven receipts, item rows, placements, authorization, spells, and stock remain unchanged. |

The bag and legendary both have instance flags 1. The character is offline after the successful run. Actual database queries confirm cap_items 1, banked_xp 0, talent_unlocks 1, riding_flags 1, vouchers 5, level 10, XP 10, victory 0.

The run log is `.local/native-runtime-smoke-third.log`. The exact assertions are in `tests/verify_runtime.py`.

## Test-client defects found and corrected

The first run queried obsolete `character_spell.active` and `disabled` columns. The pinned schema has `guid`, `spell`, and `specMask`. Snapshot queries now use that schema.

The second run was disconnected by the server's over-speed ping guard. `RealmClient.stay()` reset its timer on every short wait and used a ten-second interval. The client now keeps one sequence and thirty-second schedule across calls. An executed fake-clock test verifies repeated short waits send only the expected pings. Server ping enforcement was unchanged.

The two failed fixtures and their indexed history remain preserved. No reset, SQL repair, direct character-stat write, or mutation of the normal playthrough character was used to make the third run pass.

## Remaining verification

This run did not fill the XP bank to its maximum, exercise cap 30 or later, spend or respec talents, switch dual specs, learn eligible riding, enter restricted expansion maps, buy from a real merchant, test normal same-entry items, observe legendary procs in combat, attempt transfers, or kill a process between commit and publication. Real-client gameplay and the remaining release gates stay open.
