# Private visible pilot telemetry

Live rendering, ROI and advancing-frame decoding were verified on existing fixture24 using the stock client on private display95. See `AIRBORNE_RUNTIME.md` and `.local/flight-visible/`. Captures decoded health8108, map-area487, facing0.2464 and advancing sequences1481/1483. This does not measure general end-to-end latency or prove a normal gameplay controller.

The addon uses only permitted read APIs and UI painting. It performs no input, memory reads, networking or world writes. Only the private `.local/v2-client/game/Interface/AddOns/WoWPilagoPilot/` folder is installed. Production addon/dist, EXE, original game files and display0 are untouched. The completed display95 client exited0; do not launch another client during an exclusive native maintenance window.

The normal UI overlay paints at most 10Hz. Its 16x16 opaque 4px blocks occupy client-content ROI `64x64+8+8`. Reciprocal UIParent scale requests physical pixels. Parent must verify origin/colors on first launch, keep the corner unobscured, and restart after UI scale changes. It uses Wrath `CreateTexture:SetTexture(r,g,b,a)`, no modern texture APIs or mouse interception.

## Schema v1

Row-major blocks, LSB-first bits, unsigned little-endian integers. Exactly 32 bytes. Offsets: magic `WP` 0; version u8 2; sequence u16 3; flags u8 5; validity u8 6; map area u16 7; x/y u16 9/11; facing u16 13; player/target health u32 15/19; current money u32 23; quest7 first-objective count u8 27; repeated sequence u16 28; checksum bytes 30/31. Fletcher checksum starts a=b=0, then a=(a+byte)%255, b=(b+a)%255 over bytes 0..29; append a,b.

Flags bits 0..6: target exists/dead/attackable, player combat, target combat, loot window open, player dead. Loot events indicate an open window, not corpse lootability or successful item acquisition. Validity bits 0..6: map, facing, player health, target health, money, quest, flags. Invalid/unavailable fields decode as null. No target means null target health. Quest absence, collapsed entries or unparseable objective text mean null, never quest selection/expansion.

Map x/y round 0..1 to 0..65535. Facing rounds modulo one turn to u16; decode as value*2*pi/65536. Both angle 0 and 2*pi encode 0. Map 0,0 means unknown, including indoors; individual coordinate edges remain valid. No world xyz guesses. Existing SourceWorldMapArea/Elwynn bounds stay in `.local/v2-navigation`; see `docs/NAVIGATION.md`. SetMapToCurrentZone runs only on entering/zone events and skips an open world map. Map telemetry is invalid while that map is open.

## Check now, capture later

`python3 -m unittest discover -s tests -p test_pilot_telemetry.py -v` tests actual Lua under LuaJIT's Lua 5.1-compatible runtime with stubs, plus RGB decoding. It is not client render evidence.

Only after the current maintenance owner releases the client window, use this external read-only stream. It was exercised with the fixture24 launch; do not run it against a stale or unrelated window:
```sh
while :; do DISPLAY=:94 import -window "$WINDOW_ID" -crop 64x64+8+8 +repage -depth 8 rgb:-; sleep .15; done | python3 tests/pilot_telemetry.py
```
Default input is cropped 64x64 tightly packed 8-bit RGB. Offline: `python3 tests/pilot_telemetry.py capture.rgb`, always `fresh=false`. Full raw screenshots accept `--size WIDTH HEIGHT --origin 8 8`. No headers, alpha, resizing or JPEG. Block centers require every channel <=80 black or >=175 white. Ambiguous pixels, size/schema/checksum/torn-copy errors emit no JSON.

Live stdin primes once, then requires advancing modulo-65536 sequences within 0.5 seconds. Repeated/reversed frames emit no JSON. Corruption resets priming; gaps over 0.5 seconds re-prime. `Freshness.observe` requires captures taken now, not buffered/replayed files. Sequence cannot prove absolute capture age. Consumers must discard output older than 0.5 seconds. This tool never acts, even on `fresh=true`. Checksums detect corruption, not malicious forgery or every collision.

Local API evidence: `../wow-addons/ForeverDungeonJournal-3.3.5a/tools/vendor/` contains `client-ui/WorldMapFrame.lua` for map area, money, quest reads and numeric SetTexture; `quests/pfQuest-wotlk/database.lua` for GetQuestLink/GetQuestLogLeaderBoard; `guides/DBM-4.60` for map position, SetMapToCurrentZone, health and combat; `client-ui/GameTooltip.lua` for UnitCanAttack. Existing `tests/gui_navigation.py` and prior NAV screenshots establish GetPlayerFacing/GetPlayerMapPosition. Missing APIs remain unknown. The fixture24 launch verified pixels and advancing-frame decoding. Recheck ROI after UI scale changes; general capture latency remains unmeasured.
