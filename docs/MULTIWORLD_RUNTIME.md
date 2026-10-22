# Two-game runtime verification

## Latest legitimate return, 2026-10-20

Normal Apjourney completed Milly's Harvest3904 through the stock client. Parent verified rewarded quest state and native check919503904 acknowledged1. The original room sent Map Width80000 to ChecksFinder. The preserved official game then showed six columns, five rows, five bombs and one available check. It completed exactly one board and visibly sent Consumable Cache back to Azeroth from Tile6. Its updated counter was6/25 with zero capacity. No hidden board data, fixture check or profile reset was used.

Parent inspected the actual game screenshots and original AP save. The only incoming peer upgrade was the real Map Width. Its named receipt line was not captured, so that line is not claimed as UI evidence. Applied board dimensions and unlocked capacity are observed effects. Native receipt index11 is the real Tile6 cache, queued while level3 Apjourney is offline. It has not yet been proved applied. Earlier queues and all eleven historical frozen rewards remain unchanged.

See `docs/verification/normal-milly.json` and `docs/verification/real-peer-return.json`. The official peer exited normally and parent stopped only its owned game and X93. The current room and least-privilege bridge remain running for the next native login. This is a legitimate bidirectional session, not complete goals. WoW remains level3 and ChecksFinder6/25. The release gate still requires both goals.

## Historical initial status

Real packaged AP generation used **World of Warcraft, Human Warrior**, plus **ChecksFinder**, not two WoW slots. Both directions have actual cross-game placements. The official unmodified ChecksFinder Linux game connected to real MultiServer and completed a board through mouse input. MultiServer queued its Tile 1 reward for Azeroth.

| Evidence | Result | Limit |
| --- | --- | --- |
| Packaged generation, slot data, placements | Passed | Generation is not gameplay |
| Official ChecksFinder board completion | Passed | One board, not a full playthrough |
| ChecksFinder Tile 1 to Azeroth | Passed, Talent Point Unlock in current legitimate room; voucher in historical room | WoW bridge/native delivery not exercised |
| Bidirectional AP `ReceivedItems` | Passed in a separate fixture-only room | Both checks fabricated by explicitly named protocol fixture clients |
| Official ChecksFinder applies Map Height | Passed, board grew from five to six rows | Source WoW check was fabricated in fixture-only room |

**Real WoW gameplay to ChecksFinder and native WoW reward delivery remain unverified.** No realm, account, or character database was modified. No bridge was bound. The parent's native build and fresh-character run are separate gates.

## Preserved-room resume source check

The later resume rejection came from one test-only change in `apworld/wowpilago/test/__init__.py`. Parent verified all seven original room artifacts and the unchanged generation helper. No production AP source, catalog identity, slot manifest or placement differed. See `NEW.local/real-room-resume-review/FINDINGS.md`.

Parent restored all15 original AP source/example files from the immutable room package and player YAMLs into `.local/real-room-frozen-source`. Its byte-identical helper now passes its original `check-current` guard against the SAME room. No guard was disabled, source rolled back in the working tree, save replaced or seed regenerated. Both save hashes remained exact. Proof is `.local/real-room-frozen-source/readiness.json`.

Future authorized server startup must use that mirror's helper with the original absolute room path. Parent's offline interpreter check loaded WoW directly from the original room APWorld, ChecksFinder and MultiServer from the pinned upstream, and reproduced both datapackage checksums without changing saves. See `.local/real-room-frozen-source/environment.json`. Actual save loading and live network resume remain unverified.

The first environment report exposed platformdirs4.7.1 instead of upstream's4.10.1. Parent installed the exact existing dependency into an isolated `.local/room-dependency-overlay`, leaving the original interpreter environment unchanged. With that overlay, all seven observed server-dependency versions match upstream requirements and both original datapackage checksums still match. See `environment-pinned.json` and `dependency-overlay.json` beside the mirror. This is not a lockfile proof for every optional world/GUI dependency. No server started. Source-currentness and imports alone do not prove live resume. Keep the native3b9 safety fixes.

## Read-only preserved-room runtime resume

Parent later started the SAME room using the frozen-source helper and isolated dependency overlay. Actual server output loaded seven received items for two players and all three embedded datapackages. An unauthenticated observer verified RoomInfo seed98284801054971523741 and the exact WoW/ChecksFinder/Archipelago datapackage checksums, including98 WoW item names and300 location names.

The observer sent only GetDataPackage. No slot logged in, bridge started, check or reward was sent. The server handled normal shutdown and exited0. The active save's bytes and every decoded field remained exactly equal to the pre-start backup, SHA256 `d7a6744dac9404f1c4dd60b10fcedb1a25aed67f10f14f1b3b8f7ca335be84b3`.

See `docs/verification/preserved-room-resume.json` and `.local/room-readonly-resume/`. The first observer assertion omitted the server's explicit Archipelago game entry; source line559 established that entry, and the corrected exact three-game assertion passed. The failed observation log remains preserved. This proves room reload/network identity, not native bridge reconnection, crossback or either final goal. Server and bridge are currently off.

## Current legitimate room, seed 919000205

The final curated Human Warrior room is `.local/v2-multiworld/run-79mlu0ta`, internal seed name `98284801054971523741`, ChecksFinder slot 1 and Azeroth slot 2, loopback port 38283. The official Linux game connected through Play Online using fresh `XDG_DATA_HOME` at `run-79mlu0ta/actual-peer-game-home`. Seven ordinary left clicks solved the first visible 5x5, five-bomb board. Only screenshot-visible numbers informed the retained solver. No protocol fixture or manual check sends were used.

`actual-peer-sent.png` shows `ChecksFinder sent Talent Point Unlock to Azeroth (Tile 1)`. `actual-peer-board-complete.png` shows the solved board. Read-only decoding of the server save confirms location 81000 checked by slot 1 and item 919100020, sender 1, queued for slot 2. `actual-peer-evidence.json`, `actual-peer-server-save.apsave`, and `actual-peer-server.log` retain the checksummed snapshot and server evidence. There are no WoW checks in this snapshot, and item cheats, release, and collect are disabled. **Queued does not mean delivered to native WoW.** The bridge/player was not bound during this peer test.

The release ZIP hash matches the official download below. Actual versions were title v2.0.8 from release tag v2.0.9, AP client 0.6.1, MultiServer 0.6.8, Python 3.13.11, Godot 4.4.1.stable.official.49a5bc7b6, Mesa 26.2.2-arch3.2 using llvmpipe LLVM 22.1.8. Xvfb display 93 used 1280x900x24; the game was 972x648 and console 1152x648, both moved to 0,0. Displays 0 and 94 were not used. Startup logged a TLS handshake error, but the local AP connection and check succeeded. The compressed WebSocket compatibility warning still applies.

Only Tile 1 was played. Tiles 2 through 5 remain available without incoming upgrades, so there is no immediate item blocker. Upstream rules require one Map Width/Height/Bombs item for Tile 6 and another for each following tile. Tile 2 is placed as Equipment Voucher +3 for Azeroth. Legitimate crossback routes include Milly's Harvest 3904 for Map Width and Bounty on Garrick Padfoot 6 for Map Bombs after their normal prerequisites. Neither was completed here. Initial Elwynn entry rewards WoW's own Consumable Cache, not a ChecksFinder upgrade.

The peer left the board with its GUI Exit button, then stopped its game and private Xvfb. The parent's server was left running. Preserve `actual-peer-game-home`; `actual-peer-handoff.md` contains parent-owned background restart commands and GUI connection coordinates. Restart/reconnect was not tested. Older room saves and realm/auth databases/native client were untouched.

## Generate with the current catalog

Run from the repository using your Archipelago Python environment. Upstream must be commit `54803be064fc7e80c4628777ed0b46a9390f255f` at `/tmp/archipelago-upstream`, or supply `--upstream`.

```sh
AP=/path/to/archipelago-venv/bin/python
"$AP" tests/verify_multiworld.py generate --seed 919000203
```

Each invocation creates a NEW `.local/v2-multiworld/run-*` directory, packages the current `.py` and `.json` world files into that directory's `worlds/wowpilago.apworld`, copies both current example YAMLs, and runs upstream Generate/Main. It never installs over the upstream checkout. The two profiles are `examples/player.yaml` and `examples/checksfinder.yaml`.

The output includes `manifest.json`, the AP ZIP/spoiler, extracted `.archipelago`, `slot-data.json`, and `placements.json`. Slot IDs are discovered from multidata, not assumed. Placements include both games' location/item names and numeric IDs. The helper asserts the Human Warrior profile, protocol 2, exact selected WoW location set, 25 ChecksFinder locations, and cross-game placements in both directions.

The manifest records upstream commit, Python version/path, generator checksum, catalog version, all world source/YAML hashes, and generated artifact hashes. Generation fails if sources change during the run. In-flight curation is not an atomic filesystem snapshot, so discard any failed run directory.

```sh
RUN=/absolute/path/printed/by/generate
"$AP" tests/verify_multiworld.py check-current "$RUN"
"$AP" tests/verify_multiworld.py server "$RUN" --port 38283
```

Use a background terminal for the server. Wait for `server listening on 127.0.0.1:38283` before connecting clients. The helper binds only loopback, refuses reserved port **38282**, checks availability, disables item cheats/release/collect, and verifies source/artifact hashes before startup. Saves are the `.archipelago` sibling `.apsave` inside the NEW run directory. This pinned upstream parses `--savefile` but its main does not apply it, so the helper relies on the verified per-run sibling default instead.

**After any catalog/package change, generate again. Never resume an old seed against a changed catalog or an existing bound character.** `check-current` and `server` reject stale sources, including provenance-only file changes. An already-running server cannot see later edits; stop it and regenerate before the next test. A matching numeric seed does not make two catalog versions interchangeable. The helper does not reset or migrate any binding/save.

Leave `/tmp/wowpilago-world-test-jz4anl1m` and its port 38282 alone. Everything downloaded/generated here is ignored through `.local/`.

## Official ChecksFinder UI

Upstream setup instructions are `worlds/checksfinder/docs/setup_en.md`. They link the free official GitHub releases and `https://suncat0.itch.io/checksfinder`, including its web version. This run used:

```text
https://github.com/jonloveslegos/ChecksFinder/releases/download/v2.0.9/ChecksFinder_linux.zip
SHA256 7ccce7aa629b75b7eda9ff4f7cb104bbc37e5ca33efd11964976069605fdb4ee
```

The release tag is v2.0.9, but the shipped game's title screen displays v2.0.8. Its AP connection advertises 0.6.1. Do not silently equate those versions. The ZIP, release API metadata, executable/PCK checksums, and extracted runtime are under `.local/v2-multiworld/downloads` and `checksfinder`.

To repeat the headless UI test, start these as background commands, using an unused display number:

```sh
Xvfb :93 -screen 0 1280x900x24 -nolisten tcp
DISPLAY=:93 XDG_DATA_HOME="$PWD/.local/v2-multiworld/new-game-home" \
  .local/v2-multiworld/checksfinder/ChecksFinder_linux/ChecksFinder.x86_64 \
  --rendering-method gl_compatibility
```

Create `new-game-home` first. Use a different data directory for another room so local game state cannot contaminate the test. No Wine is needed for this Linux release. The legacy upstream `ChecksFinderClient.py` file bridge is not needed either; this release connects directly.

1. Use `xdotool search --onlyvisible --name '^ChecksFinder$'` to find the game window. Move it to `0 0`, then click Play Online at `485 452` for the default 972x648 window.
2. Find `'^Archipelago Console$'`, move that window to `0 0`, and focus it. With its default 1152x648 geometry, enter IP at `1040 58`, port at `1040 109`, and slot at `1040 159`. Use **127.0.0.1**, **38283**, **ChecksFinder**, no password. Click Connect at `920 300`.
3. Raise/focus the game window. Capture screenshots with `DISPLAY=:93 import -window root screenshot.png`. Solve the visible Minesweeper board using ordinary left clicks and, when needed, flags. Board layouts and dimensions vary; do not replay fixed click coordinates for a different seed or reward state.

Moving both windows to the origin avoided unreliable click placement with this bare Xvfb setup. Keyboard entry worked before that but button clicks were unreliable. No client code, memory, save contents, or AP messages were patched to complete the board. The retained `solve-visible-board.py` enumerated boards from visible numbers only; it sent no packets and read no game internals.

MultiServer warns that this client lacks compressed WebSocket support. It worked with the pinned server; future server compatibility is not established.

## Separate protocol fixture

Generate a NEW run and use another available loopback port, such as 38284. Never point this command at a gameplay room. It deliberately submits generated location IDs without playing either game.

```sh
"$AP" tests/verify_multiworld.py generate --seed 919000204
FIXTURE=/new/run/path/printed/above
# Background command. Wait for the listening log before the next command.
"$AP" tests/verify_multiworld.py server "$FIXTURE" --port 38284
"$AP" tests/verify_multiworld.py protocol-fixture "$FIXTURE" --port 38284
```

The fixture connects two explicitly named fixture identities, verifies slot data against the selected run, requires empty checked-location sets, submits one cross-game check each way, and asserts the exact item/location/sender in real `ReceivedItems`. Its `protocol-fixture.json` says the checks are fabricated. This is not a legitimate game client or proof of quest completion, progression eligibility, SQL persistence, or native delivery. Generate another fresh run to repeat it; do not clear saves.

Connecting a fresh official ChecksFinder UI to the fixture room additionally demonstrated that its queued Map Height item changes the actual board to six rows. That verifies the receiving game runtime, not the fabricated WoW source event.

## Retained evidence and native handoff

The first gameplay run is `.local/v2-multiworld/run-q6bi44sg`, seed 919000203. Its `server.log` and `actual-checksfinder-send.png` show `ChecksFinder sent Equipment Voucher +1 to Azeroth (Tile 1)`. Its server save contains location 81000 checked by slot 1 and item 919100031 queued for WoW slot 2. `actual-game-evidence.json` records the extracted queue and a checksummed save snapshot. No synthetic checks were submitted to this room.

The fixture runtime run is `.local/v2-multiworld/run-tqmiqsm_`, seed 919000204. See `protocol-fixture.json`, `fixture-receive-console.png`, and `fixture-receive-board.png`. The return item is Map Height, AP ID 80001, from WoW location 919510324. The source quest was NOT completed in WoW. See `verification.json` in the artifact root for final verification paths and status. These directories preserve historical evidence, not permission to reuse them after catalog changes.

The inspected candidate GUI client's `Wow.exe` is an x86 PE executable with SHA256 `bd87720d0fb7299f19b41c5e7f5bf65f3f628066b3765ce382e81c5871b0a2a3`. Wine and Xvfb are installed. This investigation did not launch that client, validate its build, change its realm/config/addons, or log into any account. After the parent supplies the finished realm and authorized fresh character, Wine plus focused `xdotool` keyboard/mouse input and screenshots is a possible unpatched GUI automation route. Its reliability is untested. Do not call `tests/realm_client.py` real gameplay; it explicitly lacks movement/gameplay emulation.

For the native handoff, generate once more from the final curated package. Bind the approved fresh offline level-1 Human Warrior through the documented bridge procedure, not this helper. Complete an ordinary WoW check whose placement targets ChecksFinder and capture the actual board change. Complete a ChecksFinder board whose reward targets WoW and verify the real bridge receipt, native effect, and addon/UI result. Native SQL receipt replay, reconnect behavior, and the full playthrough remain the parent's work.

## Legitimate continuation through Tile 5

This later observation supersedes the earlier one-board limit for `run-79mlu0ta`. Evidence is retained only under `.local/v2-multiworld/run-79mlu0ta/boards-remaining/`. The official Linux peer resumed the exact preserved `actual-peer-game-home` on private display 93 and reconnected to the existing parent server at 38283. Tiles 2 through 5 were completed with real left mouse input using screenshot-visible numbers only. Tile 5 needed one ordinary retry after a guessed mine. No fixture command, synthetic check, save patch, memory read, or profile reset was used.

| Tile | Outgoing reward to Azeroth | AP ID | Location | Full received index | Sender | Flags |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | Equipment Voucher +3 | 919100032 | 81001 | 3 | 1 | 2 |
| 3 | Equipment Voucher +3 | 919100032 | 81002 | 4 | 1 | 2 |
| 4 | Progressive Level Cap | 919100001 | 81003 | 5 | 1 | 1 |
| 5 | Bag Upgrade | 919100040 | 81004 | 6 | 1 | 2 |

`server-save.apsave`, `server.log`, `all-rewards-console.png`, and each tile's screenshots retain actual runtime proof. `evidence.json` records names, indices, senders and flags for every queue entry, including the filtered remote-only queue. The full slot 2 queue has existing index 0 Talent Point Unlock from sender 1 at 81000 with flags 2, index 1 Consumable Cache from sender 2 at 919700012 with flags 0, and index 2 Gold Cache from sender 2 at 919500783 with flags 0, followed by the four rows above. ChecksFinder's incoming queue remains empty. There was no incoming ChecksFinder reward and no dimension or bomb-count change.

Read-only SQL on authorized loopback port 13317 confirms the bridge naturally persisted all four new `ReceivedItems` receipts at indices 3 through 6 with matching IDs, locations, senders and flags. `readonly-native-receipts.json` retains the queries and rows. No raw WebSocket frames were captured. The new rewards are **received but unapplied**, not native-effect proof. The character was offline at observation. Existing index 0 Talent Point Unlock is applied and `talent_unlocks=1`; the new rewards leave `cap_items=0` and `vouchers=0` until native delivery runs. SQL identified GUID 4 as `Apjourney`, not the task's `APV2A` label; no binding or character changes were made.

Stopped at the legitimate Tile 6 item gate. `gate-after5.png` shows 5/25 checks and zero remaining check capacity. Tile 6 needs one Map Width, Map Height or Map Bombs item. The UI can still generate practice boards, but none was solved past this gate. The save confirms exactly 81000 through 81004 checked for slot 1. Item cheats, release and collect remain disabled.

The peer left through GUI Exit, then only its owned game and Xvfb :93 were stopped. Parent MultiServer, WoW bridge, display 94 and old rooms were left untouched. `parent-processes-after.txt` confirms the parent server still listening on 38283. `handoff.md` contains restart commands, the full reward table and observed geometry. Reconnect with the same preserved data home is now verified. Screen geometry remains 1280x900x24, game 972x648 at 0,0, console 1152x648 at 0,0; current board centers are x=67,202,338,472,607 and y=65,195,325,454,582. Read a fresh screenshot after any incoming upgrade rather than replaying these coordinates. Native application of the four new rewards, a legitimate crossback upgrade and full multiworld completion remain unverified.
