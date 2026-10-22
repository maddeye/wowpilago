# Live protocol-2 connectivity

## Verified session

The real build-12340 client logged into the private native realm as `Apjourney`, GUID 4, account `APV2A`, security level 0. The character was created at level 1 and bound while offline. No GM command, fabricated AP check, or synthetic reward populated this character.

The actual AP seed name is `98284801054971523741`, team 0, WoW slot 2 named `Azeroth`. The generator seed argument was `919000205`; those identifiers are different. The room and save are in `.local/v2-multiworld/run-79mlu0ta`. The official ChecksFinder peer occupies slot 1.

| Actual event | Durable result |
| --- | --- |
| Official ChecksFinder client completes Tile 1 through mouse input | AP item 919100020, location 81000, sender 1, received index 0. |
| Native worldserver applies that queued reward after login | One talent permission. Actual level remains 1, earned talent points remain 0, and the status reports one pending eligibility. |
| Apjourney enters its initial Elwynn Forest zone | Location 919700012 persists and the real AP server acknowledges it. |
| The room sends that location's Consumable Cache back to Azeroth | Received index 1, AP item 919100051, sender 2. |
| Native transaction commits the physical cache before publication | Item GUID 69, entry 118, count 5, owner 4, backpack slot 24. |
| Actual client displays receipt feedback | Private potion alert and native receipt chat appear in the game. |
| Actual `.archipelago status` command | Level 1, cap 10, XP bank 0, one talent unlock, no riding, vouchers 0, remaining shop cost 255, remaining checks 212, no pending deliveries. |
| Bridge process stops and reconnects to the real room | The same two immutable indices remain applied; no extra effect or item appears. |
| Ordinary client logout completes, then the same character logs in again | One talent permission, five potions, and one acknowledged check remain unchanged. The actual backpack displays the stack of five. |

The initial connectivity run used private root fixture credentials. The real bridge now authenticates as `wowpilago_bridge_v2` from the actual Docker gateway using a random password stored in a mode-0600 private file. Its grants match `sql/bridge_permissions.sql`. Actual authentication and heartbeat pass; attempted character updates and item-instance reads are denied. No public service or production credential was used. `SECURITY.md` documents the trust boundary.

## Inspectable artifacts

The current realm binary and source digests are in `.local/v2-build/20261019T150600.624050Z/post-curation-manifest.json`. The exact matched binary was started with `.local/v2-realm/override.yaml`.

The peer's real-game evidence is `.local/v2-multiworld/run-79mlu0ta/actual-peer-evidence.json`. It contains no fabricated checks. The separate earlier protocol-fixture room is not evidence for this session.

Actual client captures are under `.local/v2-client/`:

- `normal-first-hud.png` shows the private potion receipt and native talent receipt chat.
- `normal-native-status-command.png` shows actual cap, pending talent eligibility, riding, voucher, and remaining-check values.
- `normal-relogin-backpack.png` shows the saved stack of five after normal logout and relogin.

The character remains a normal fresh-playthrough character. Its only earned location so far is initial zone entry. Source images and the user's client files remain unchanged. `CLIENT_RUNTIME.md` documents the private stock-data layout needed to avoid a crash in the supplied custom patch set.

## Remaining scope

This establishes the connectivity milestone and an actual inbound cross-game reward. It does not establish all reward kinds, XP caps or bank release under combat, talent spending or level-80 eligibility, merchants, low-level authorized equipment, transfers, every check type, process-crash recovery, outgoing WoW-to-ChecksFinder delivery, either final goal, or the complete level-1-to-80 playthrough. Those TODO tasks remain open.
