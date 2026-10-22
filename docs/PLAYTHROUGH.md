# Normal starter playthrough

## Graphical-shop acceptance, 2026-10-21

The actual stock client inspected all60 personal stock rows across four categories and seven pages. Each row had a physical tooltip hover. A1-voucher confirmation was cancelled without spending. A later cold-cache test exposed icons that stayed unknown until hover. That failed test remains preserved. The addon now requests uncached item data through one hidden private tooltip and uses an opaque background for readable rows.

A fresh cold-cache session resolved all12 visible weapon icons by one second without operator item queries. One physical Buy and matching Accept purchased stock18, Warleader's Shield15991, for one voucher. Actual server chat, the equipment-purchase toast, bag contents and the reopened shop agreed. Vouchers changed5 to4, remaining shop cost247 to246, and only stock18 became newly SOLD. Stock26 remained SOLD. New authorized soulbound instance591 is in bag298, slot5, unequipped. The old sword66, equipped axe590 and both bags remain unchanged.

Parent audited all122 character tables and all auth tables after normal logout. Previous items, other41 characters, old AP histories, eleven frozen rewards and the original room save stayed exact. Only the intended purchase and source-attributed native bookkeeping or ambient rows changed. Saved level3, XP1096, money1106 and health1088 remain unchanged. The actor did not move, fight or complete a quest. Release finished at575.61seconds, within the810-second input and900-second total limits.

Evidence is `docs/verification/graphical-shop.json`. The graphical-shop requirement is now checked, bringing the ledger to152/188. This does not complete purchase crash/concurrency/full-bag tests, equipment effects, the level1-to80 playthrough or final multiworld goals. Earlier sections retain their historical states and counts.

## Audited Stormwind arrival and first shop purchase, 2026-10-21

Apjourney reached Stormwind through normal ground movement and gained 70 exploration XP. Native check919701519 acknowledged through the preserved real room. Its Bag Upgrade arrived at receipt13 as Netherweave Bag instance589. The new bag remains unequipped inside the original equipped bag298.

The stock client bought stock26, Troggbane51795, once for eight vouchers. The balance changed from13 to5, and only that stock row became SOLD. One physical bag click equipped authorized instance590 at level3. The original tooltip still requires level80. Native strength increased by66, stamina by99, and maximum health from98 to1088. The original sword66 remains unchanged in bag298, slot4. No copper or potions were spent.

The final saved character is level3, XP1096, money1106, health1088, with ten Minor and five Lesser Healing Potions. Quests21 and3905 remain active. The final position is Stormwind Trade District, -8836.37,625.153,93.7211. Inputs were released at803 seconds, before the810-second cutoff. Character selection was verified at834 seconds, before the900-second total limit.

The final audit checked all122 captured tables. All preexisting item fields, the other41 characters and eleven frozen pending rewards stayed exact. The original room added exactly this check and one bag while preserving the prior13-item WoW receipt prefix and all peer state. Its canonical received total changed from14 to15. Evidence is `docs/verification/normal-stormwind-shop.json` and `.local/normal-stormwind-entry-shop/parent-audit.json`.

The earlier road attempt included one real Defias death and normal Spirit Healer recovery, including its25% durability cost. Those histories remain preserved. This is not a continuous Northshire-to-Stormwind walk or a completed level1-to80 playthrough. No combat, procs or set bonuses were tested with Troggbane. The bounded low-level equipment requirement is verified separately in `docs/verification/native-low-level-equipment.json`, bringing the ledger to151/187. Older sections below retain their historical states and counts.

## Worker turn-in and restart recovery, 2026-10-20

Quest 15 was turned in normally for 250 XP and 40 copper. The short slice finished in 4m35s. Apjourney saved at level 3 with 981 XP, 1106 copper, 13 vouchers, ten Minor and five Lesser Healing Potions. Active quests are 21 and 3905.

The bridge and AP server were absent. Parent captured native check919500015 with acknowledgement0, restarted the same native world and verified all42 characters and AP tables stayed exact. The check remained pending. The Hallow's End event12 timestamp changed at startup exactly as pinned source specifies. The shared worldstate guard was not relaxed.

Reopening the original room and bridge acknowledged the check and queued one Artisan Riding reward at index12. The reward is still unapplied while Apjourney is offline. Parent then stopped only the AP server, left the same bridge process alive and observed its disconnected status and retry loop. After the unchanged launcher passed its port probe, that same bridge reconnected automatically without changing reward, check, progression or stock rows. The first failed `EADDRINUSE` launcher attempt is retained.

The original save now has14 items. Previous13 items and six peer checks are unchanged. See `docs/verification/bridge-reliability.json`. The bridge requirement is verified, bringing the ledger to148/187. No character deletion, exact purchase crash window or final goal is claimed.

## Actual return cache and workers, 2026-10-20

The official preserved ChecksFinder game applied the new six-column board and one available check, then completed exactly Tile6 through visible-board mouse input. Its actual console sent Consumable Cache to Azeroth. Parent verified the original AP queues and native receipt11. The next normal level3 login delivered five Lesser Healing Potions858 while the ten Minor118 remained unchanged. The named incoming peer receipt line was not captured. Applied board effects, real queues and the native return are separately proven in `docs/verification/real-peer-return.json`.

Eight ordinary Kobold Worker kills completed quest15's objective. It was not turned in before logout, and parent confirmed no AP check was sent early. Confirmed corpse loot was23 copper, two apples, two candles and boots. Two earlier corpses were not fully collected. No potion was used and no death occurred. Saved state was level3/XP731/money1066,13 vouchers,10 Minor and5 Lesser potions. Grape Manifest3905 is also active. Explicit input release finished14m44s after launch. Logout input missed the13m30 cutoff by two seconds, but the total stayed under15 minutes.

The later gated regression passed523 tests without skips. World/auth were stopped and all production character/auth data and the real save stayed exact. Parent restored the same immutable world binary. A short quest15 turn-in slice now runs with room/bridge intentionally off. Its result needs a separate audit. Requirement count is147/187.

## Milly's Harvest and the return upgrade, 2026-10-20

Apjourney physically equipped the awarded Netherweave Bag and gained 16 slots. Wolfskin Bracers are equipped. Quest33 and Milly's introduction3903 are rewarded. Their real Voucher+1 rewards applied, as did the queued Voucher+5 from5261. Saved vouchers are13. Other41 characters and the historical eleven pending rewards stayed exact.

The first Milly slice collected eight grapes but did not turn in3904. Parent verified its native check was absent even with8/8 objectives. This slice released the client at15m04s, four seconds over its limit. The additional turn-in-only slice finished in4m41s. Actual chat confirms180XP and quest completion. Saved level3/XP251/money1043 and ten potions match the client. Only quest15 remains active at0/8.

Native check919503904 persisted with acknowledged1. The original AP save now queues the real Map Width80000 from Azeroth to ChecksFinder, sourced from that quest. Parent has started the preserved official peer game to verify actual application. Queue evidence does not prove application. See `docs/verification/normal-milly.json` and `.local/real-peer-return/queued.json`. The full playthrough and final goals remain open. Ledger remains146/187.

## Offline bridge and wolves, 2026-10-20

The next14m49s stock-client slice completed quest5261 for85XP. Eight Diseased Young Wolf kills yielded seven Diseased Wolf Pelts, item50432. Quest33 remains7/8. Quest15 is accepted at0/8. Saved level2/XP659/money1041 and ten potions match the actual client reads. No deaths or potion use occurred. Full bags prevented collection of one extra pair of pants. No items were discarded.

The room and bridge stayed off during gameplay. After normal logout, parent captured native check919505261 with acknowledged0 and the original AP save unchanged at eight items. The account remained connected at character selection until parent closed the launcher. No online flags were repaired.

Parent restarted the original room and least-privilege bridge. The native check changed to acknowledged1, and one real Voucher+5 arrived at index8. A second actual bridge reconnect left all check, reward, progression and stock rows exact. The gracefully saved room now contains nine items. All earlier eight receipts and peer checks remain unchanged. The five new vouchers remain queued while Apjourney is offline. Global pending rewards are twelve, comprising eleven historical frozen rewards and this one new normal reward.

Evidence is `docs/verification/native-check-reconnect.json` and `.local/normal-wolves-disconnected/parent-audit.json`. Parent verified all41 other characters and unrelated rows remained exact. The durable-check requirement is now verified, bringing the ledger to146/187. This does not prove every check type, complete multiworld goals or the full playthrough. The next normal action is to equip the awarded Netherweave Bag, finish the last pelt and turn in quest33.

## Kobold quest and first loot, 2026-10-20

Apjourney completed five ordinary Kobold Vermin kills, looted every corpse and turned in quest 7. The 12m21s stock-client slice stayed within its 15-minute budget. The first visible loot window contained four copper and a Melted Candle. Actual chat and inventory proved collection. Total loot was 16 copper, two Melted Candles, a Frayed Belt and Refreshing Spring Water.

The saved character is level 2 with XP220 and 1041 copper. Quest 7 awarded 170 XP and 25 copper. Both quests 7 and 783 are rewarded. No quests remain active. Real check 919500007 reached the original AP room, persisted as acknowledged and produced receipt index7, Consumable Cache. Native delivery added five potions, bringing the saved total to ten.

Parent inspected actual screenshots, compared all122 raw tables and decoded the original room save. Other41 characters and unrelated owner rows stayed exact. Eleven frozen rewards remain untouched. The original seven receipts and five ChecksFinder checks stayed unchanged. The new save has eight received items. Client, bridge and room processes are now absent after the Goal pause. All42 characters and accounts are offline. Native world, auth and database services remain running.

Evidence is `docs/verification/normal-quest7.json` and `.local/normal-kobolds-connected/parent-audit.json`. The audit records one source-confirmed event respawn and one elapsed Wintergrasp defense separately. Shared runtime guards were not loosened. This proves legitimate level1-to2 progress and real same-slot delivery. It does not prove a returned cross-game upgrade, the full playthrough or final goals. Requirement count stays145/187.

## Actual GUI attempt, 2026-10-19

The attempt started at 19:28 Europe/Stockholm and finished normal logout at 19:50. It exceeded the requested 15 minutes. The earlier smoke-gate report is historical and did not govern this attempt.

The first fresh screenshot showed a disconnected login screen, not the reported character selection. Normal APV2A login succeeded, followed by Enter World and a fully rendered Northshire HUD. All input used display 94, window 8388611. Display 0 and the source client were not accessed.

Actual gameplay results:

- Accepted 783, A Threat Within, from Deputy Willem through the GUI.
- Walked into Northshire Abbey and turned in 783 to Marshal McBride. Actual chat showed completion and 40 XP. Quest 7, Kobold Camp Cleanup, became active.
- Native AP check 919500783 persisted with acknowledged=1. The resulting Gold Cache, received index 2, applied 1000 copper. This is an actual acknowledged quest check and inbound reward, not proof of delivery to ChecksFinder.
- No combat or loot occurred. Quest 7 remains at 0/8. Neither Milly's Harvest nor Garrick's Bounty was reached.
- Logged out normally. Fresh character-selection screenshot and read-only SQL both confirm logout. The GUI, realm and bridge were not stopped.

## Saved state

`final-db.json` confirms GUID 4, Apjourney, level 1, XP 40, money 1000 copper, online 0. Saved position is -8911.4, -166.328, 82.2088, orientation 2.64863, inside Northshire Abbey. Quest 783 is rewarded; quest 7 is active with all objective counters zero.

`final-ap-db.json` confirms the real seed 98284801054971523741 and connected binding 1. Both initial Elwynn entry 919700012 and quest 919500783 are acknowledged. One talent permission remains; banked XP is zero. Four further real peer rewards arrived after logout, indices 3 through 6, and remain unapplied: two three-voucher rewards, one level-cap reward, and one bag reward. They were observed read-only, not exercised by this attempt.

## Input limitation and evidence

Navigation, not a stale smoke gate, consumed this attempt. Keyboard movement and turning visibly worked, but facing and camera alignment were repeatedly misjudged around abbey walls. Client click-to-move walked directly into obstructing walls rather than routing around them. A physical click plus window focus was used; the first key after loading was not relied on. No single underlying Wine input defect was established.

The normal client `autoInteract` setting was temporarily enabled for click-to-move and finally disabled. A session G binding to INTERACTTARGET was set through the permitted client API. No addon, production code, server configuration or database state was edited. No GM commands, teleports, forged checks, combat bot, memory patches or fixture-character actions were used.

Fresh screenshots are `.local/v2-playthrough/01-enter-world.png` through `38-final-logout.png`. Useful captures are `03-loaded.png`, `28-mcbride.png`, `29-reward.png`, `31-completed.png`, and `38-final-logout.png`. The folder also contains the start timestamp, final saved character/quest SQL and final AP SQL.

Next GUI action: Enter World, refresh focus with a physical click, and navigate out of the abbey before heading north toward the Kobold Vermin. No combat, quest-7 turn-in, outbound ChecksFinder reward, or full leveling result is claimed.

## Navigation lever and first combat, 2026-10-19

Added `tests/gui_navigation.py` and `tests/test_gui_navigation.py`. The tool sends normal chat commands and bounded W/S/A/D events only to display 94, window 8388611. `probe` self-whispers permitted `GetPlayerFacing` and `GetPlayerMapPosition` results. `turn CURRENT DESIRED` takes the shortest heading difference, holds A or D for approximately radians/pi seconds, then probes again. The operator must read the fresh probe before walking. Three unit tests cover angle wrapping, fresh-marker parsing and rejected unbounded input.

GUI work began at 20:05 Europe/Stockholm; login into the world occurred at 20:09:40. Normal logout finished around 20:28. Thus the full GUI work exceeded the requested 20-minute limit by about three minutes, although this login's played time was 1087 seconds. No further GUI work followed logout.

The initially visible character-selection session disconnected on entry. Normal APV2A/test-only login restored Apjourney. Real queued rewards 3 through 6 applied naturally at 18:09:40 UTC: six vouchers, one cap item and Netherweave Bag item GUID 298. Client chat and `final-ap-db.json` agree. No reward, check or character data was written outside normal gameplay.

The client chat file stayed buffered during play, even after disabling LoggingChat. The tool therefore reports that condition instead of treating an older line as a fresh measurement. Screenshot-visible probes supplied the heading feedback. The log became available after logout and was copied into the evidence directory. Lua true/false are used for LoggingChat; numeric zero is truthy. A delay after opening chat and slower typing prevented dropped leading slashes observed during software rendering.

The actual abbey door was crossed. The useful route from the saved position was east into the circular main hall, north to approximately X=-8907, west through the interior doorway toward Y=-151, then southwest into the entry vestibule. The exit jamb required a westward correction toward Y=-136. `22-door-center.png` shows Northshire Valley outside the abbey. The route is an observed recovery, not a collision-free waypoint promise. Facing probes plus position changes distinguished actual movement from contact with walls. Read-only creature coordinates and Elwynn WorldMapArea DBC bounds guided the subsequent outdoor northward walk.

Actual results and limits:

- Two normal Kobold Vermin kills advanced quest 7 to 2/8. `25-combat.png`, `26-first-kill.png` and `34-secondfight.png` show combat, skill gains and objective progress. Read-only saved quest counters confirm two kills.
- Loot was attempted with G and ordinary corpse clicks, but no loot window, item receipt or money increase was observed. First loot is NOT achieved or claimed. Foliage and loss of the dead target prevented reliable corpse selection; this is the remaining task, not evidence of an input defect.
- Final saved GUID 4 is level 1, XP 143, money 1000, online 0, position -8788.8, -135.529, 82.1212, facing 4.50845. Quest 783 remains rewarded; quest 7 remains active. No quest-7 check or turn-in is claimed. AP checks remain only the two previously acknowledged checks.
- Normal logout is proven by `40-logout.png` and `final-db.json`. Evidence is under `.local/v2-navigation/`, including the private chat log, source NPC coordinates, character/inventory SQL and AP reward receipts. Original characters 1 through 3, display 0, original installation, other fixture accounts and running services were not operated or modified by this attempt. All SQL issued here was SELECT-only.

Private client settings used were auto-loot enabled, tutorials hidden, G bound to INTERACTTARGET, and an attempted groundEffectDensity=0 foliage adjustment. No protected movement API, memory access, GM command, teleport, server script execution, world restart or fabricated check was used.

Next bounded action: inspect `.local/v2-navigation/34-secondfight.png` and `38-lookback.png` before another login. Obtain one visible corpse selection and actual loot receipt; do not repeat long blind corpse clicks or claim quest completion from 2/8.

## Kobold continuation blocked before world entry, 2026-10-19

This bounded attempt ended by 20:59:52 Europe/Stockholm, within 15 minutes. Evidence is `.local/v2-kobolds-next/`, with exact start and release timestamps. The initial screenshot showed a disconnected login screen. Normal APV2A login reached realm selection, but selecting the realm did not enter character selection. Escape returned normally to login. Input was responsive; the earlier assumption that realm selection was ignoring clicks was not established.

Read-only socket inspection found auth 3724 and database 13317 listening, but no world listener on 8085. `listeners.txt` preserves that observation. No service was restarted and no client, server, product code or configuration was changed. GUI 94 is released, all movement/modifier keys were released, and the private client remains at login. No world session began, so no in-world logout was possible or claimed.

Fresh SELECT-only observations in `final-db.json` confirm GUID 4 offline, level 1, XP 143, money 1000 copper, quest 7 still 2/8 and quest 783 rewarded. Inventory remains items 38, 39, 40, 49778, Hearthstone 6948, five potions 118 and one Netherweave Bag 21841. No actual loot, kill or quest turn-in occurred in this attempt.

`final-ap-db.json` contains only the live acore_characters observations for binding 1. Real seed 98284801054971523741, slot 2, six vouchers, one cap item, one talent permission and zero banked XP remain saved. Reward indices 0 through 6 are applied. Only checks 919500783 and 919700012 exist, both acknowledged=1. There is no quest-7 check. The discovery query also read test-schema tables without writing them; these unrelated rows were excluded from the final AP evidence.

Next action belongs to the parent: restore the world listener when its native build is ready, then reserve GUI 94 for another bounded normal-play attempt. No progress should be inferred from this failed entry.

## Visible-telemetry continuation, 2026-10-20

The normal GUI94 slice killed one Kobold Vermin. Quest7 advanced from2/8 to3/8 and XP from143 to197. Parent independently confirmed the saved level1, money1000, objective3/8 and offline character/account. No loot window, receipt, inventory gain, copper gain, turn-in or check919500007 was proved. Full playthrough remains open.

Fresh visible telemetry decoded the physical64x64 ROI, advancing sequences and the new objective count. The historical G binding was stale; the live normal API reported TARGETLASTHOSTILE before the operator rebound INTERACTTARGET. This proves neither corpse selection nor loot acquisition.

The preserved real room failed check-current with `Source/catalog changed. Generate a NEW room; do not reuse this seed/save.` The operator did not regenerate or bypass that refusal. Room and bridge stayed off; parent is investigating exact fingerprint differences before any resume. Captured AP rows and eleven historical pending receipts remain unchanged.

The client exited0 after normal logout. Total GUI time was15m34s,34 seconds beyond the requested bound. Evidence is `.local/normal-kobolds-telemetry/observations.md`, `verification.json`, telemetry frames and screenshots. Parent inspected `11-overhead.png`. Next normal slice needs five more kills, immediate corpse interaction after death and actual loot evidence, not another claim based on interaction keys alone.
