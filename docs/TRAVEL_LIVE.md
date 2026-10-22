# Bounded native travel verification

`tests/verify_travel_runtime.py` uses one fresh APV2F SEC_PLAYER human warrior and the explicitly authorized TEST control GUID 13, Apsjxsocfsik. AP ingress is fabricated through `bridge.v2.Store` with a complete Catalog-validated manifest. It never contacts a real AP room or claims normal gameplay.

## Run and scope

1. Print the offline plan:
   ```sh
   .venv/bin/python tests/verify_travel_runtime.py
   ```
2. Run packet and safety tests:
   ```sh
   .venv/bin/python -m unittest discover -s tests -p test_travel_runtime.py -v
   ```
3. With exclusive parent-authorized TEST ownership, on the private realm only:
   ```sh
   mkdir -p .local/travel-live
   WOWPILAGO_TEST_ACCOUNT_PASSWORD=test-only WOWPILAGO_DB_PASSWORD=test-only \
     .venv/bin/python tests/verify_travel_runtime.py --run \
     > .local/travel-live/run.jsonl 2> .local/travel-live/stderr.log
   ```

Do not repeat the live command after creation. The runner refuses if `creation.json` exists or APV2F already has a character. A failure preserves the fixture, binding, receipts, and transcript. There is no reset, deletion, resume-by-arbitrary-GUID option, or SQL character repair.

TEST is full at 10/10. No TEST character is created. The runner imports `verify_merchant_runtime.MerchantRunner.reuse_control` unchanged. That helper checks the class-system summary PASS/released control, absence of GUID/name in the before snapshot, exact unique GM creation event in the original run, current TEST account ID/security/offline state, exact control profile and absence of an AP binding. Prior evidence hashes are logged. APV2F requires the private email marker, security 0, offline state, and an unused account. No other account can authenticate through this runner.

Only loopback auth 3724, world 8085, and MySQL 13317 are used. Root/test-only is private fixture access, not production configuration. The observation connection accepts SELECT statements only. Store writes only the synthetic binding/NetworkItem ingress. Character creation, forward levels, selected-player ordinary mount learning, and online positioning use native packets/GM commands.

## What counts as proof

The pinned `cs_tele.cpp::DoNameTeleport` distinguishes connected targets from offline targets. The connected branch calls `Player::TeleportTo`, which invokes `OnPlayerCanAccessMap` with the destination coordinates before changing maps. Its offline `SavePositionInDB` branch bypasses that hook and is excluded here. Each setup command requires the fresh fixture to be online. The client processes the native `SMSG_NEW_WORLD` and sends `MSG_MOVE_WORLDPORT_ACK`. Near teleports use the server's `MSG_MOVE_TELEPORT_ACK` opcode and the native packed-GUID/sequence response.

The ordinary portal path was inspected in `MiscHandler.cpp::HandleAreaTriggerOpcode`: it validates the client's `CMSG_AREATRIGGER` against actual map/radius, invokes script handling and map admission, then calls `TeleportTo`. This bounded runner uses online targeted native teleport instead, not a forged distant trigger. This proves native destination access, not walking through the Dark Portal, a portal/boat journey, or normal player travel.

Actual mount use is separate. The player sends ordinary `CMSG_CAST_SPELL`, with cast counter, spell ID, zero cast flags and zero self-target mask. Successful checks require a matching own-caster `SMSG_SPELL_GO` and a native speed-change packet. Negative checks require the matching `SMSG_CAST_FAILED`, not merely an absent learned spell. Ground spell 458 and flying spell 32239 also require native saved `character_aura` rows after logout. The client inherits the shared persistent 30-second ping schedule unchanged. Saved spell queries use `spell,specMask`.

The intended bounded sequence is:

| Check | Observation |
| --- | --- |
| Access before receipts | Online target attempts to Hellfire Peninsula 530 and Borean Tundra 571 remain on map 0. |
| Pending riding | Synthetic apprentice/journeyman/expert/Cold Weather permissions at level 1 do not train their riding spells. Casting 458 is refused. |
| Ground use | At 20, 458 gives native 11.2 run speed and a saved mount aura. At 20, 23227 is refused; at 40 it gives 14.0 run speed. |
| Flight restriction and Outland | At 60 with Expert, 32239 is refused on Azeroth map 0. A real native synthetic Outland receipt then permits online map 530 entry and a 32239 cast with 17.5 flight speed and saved aura. |
| Northrend | Before its receipt, the online attempt remains in Outland. After its receipt, entry to 571 succeeds, but flight is refused at 60. At 77 with native Cold Weather training, 32239 gives 17.5 flight speed and a saved aura. |

Seven progressive cap receipts permit the forward GM level setup. This is not legitimate XP progression. The runner does not repeat the native class-system suite's five training thresholds or grant riding training through GM `.learn`. Only the three ordinary mount spells are learned by selected-player setup.

## Evidence

`.local/travel-live/` contains the complete manifest, creation identity, raw directional world packets, every GM command/reply, durable progress/receipt/inventory/spell/aura/location snapshots, offline test logs, and summary. `run.jsonl` includes source and DBC hashes and running world binary SHA-256 `6434b132b68a581a2046319c25795f9f5c1211ab2096b56898702a12542d83e8`. Module bytes must match the pinned private source before authentication.

Before/after SELECT snapshots assert GUIDs 1..3 unchanged. GUID 4 is deliberately excluded from equality because its parent-owned legitimate GUI journey is active. No GUI control, APV2A login, real AP checks, config change, world restart, native C++ edit, SQL character/XP/money/inventory/spell write, or history deletion is part of this task.

## Recorded result

The live run passed all 14 bounded assertions in 2 minutes 27 seconds. It created only GUID 24, Apsfjnnrfebe, APV2F account 7, binding 14. Reused GM 13 and fixture 24 are both offline afterward. TEST remains at 10/10; APV2F is security 0 with one character. GUIDs 1..3 have identical before/after snapshots.

The transcript contains 2,143 raw directional packets. Both initial denied destinations returned `SMSG_TRANSFER_ABORTED` with native reason `0x10`, `TRANSFER_ABORT_MAP_NOT_ALLOWED`; Northrend returned it again from Outland before its receipt. Saved access flags progressed from 0 to 1 to 3. Riding flags were 23, without Artisan. Ground 458 saved aura `amount1=60`, `base_amount1=59`. Flying 32239 saved `amount1=150`, `amount2=60` at both level 60/map 530 and level 77/map 571. These match the DBC effects and observed native speeds, rather than merely spellbook membership.

All 46 offline tests passed: 11 travel tests, 19 shared runtime tests, and 16 shared client tests. `run.jsonl` SHA-256 is `34bbbb1ad830730aa3a8b792f6e57461ff6f99330d1b7cd7ecdea95daf755664`. The immutable run and read-only final observations are indexed under `.local/travel-live/`.

No native defect appeared in the original bounded run. Map 1 and Artisan were outside that run; the extension below covers them. Portal walking, actual flight movement, a normal XP journey, and real AP-room ingress remain untested. Online native teleport proves the access hook, not an unprivileged portal journey. An assertion failure in any future run is not a PASS. Reproduce native defects against the pinned binary without editing/rebuilding the live core; rebuilding belongs to the parent.

## Owned-fixture extension

`tests/verify_travel_extension.py` extends only GUID 24, Apsfjnnrfebe, APV2F account 7, binding 14. Its default invocation prints an offline plan. It never calls the original fresh-creation command. The live invocation is one-shot and refuses an existing `.local/travel-extension/attempt.json`; do not rerun it or remove that guard.

Before seeding the login allowlist, it verifies pinned SHA-256 hashes for the original creation, manifest, run and summary; exact unique creation/binding events; fixture account marker/security/offline state; name, account, human-warrior profile, creation timestamp and level 77; the complete existing manifest/checksum/binding; all 13 original receipt rows; and saved progression, spells and riding skill 225. GM 13 uses the unchanged original `reuse_control` guard. Store reopens the existing seed and manifest, then appends only Artisan NetworkItem 919100013 at exact next index 13. No old item is resubmitted.

The actual Spell.dbc identifies spell 32242 as Swift Blue Gryphon, with effects `(6,6,6)`, aura types `(78,207,32)` and base points `(0,279,99)`. Only this ordinary mount spell is learned through selected-player GM setup. Neither `.learn 34091` nor a riding-skill command is sent.

The Kalimdor destination is pinned `game_tele` row 252, Darnassus, map 1, coordinates `9949.56,2284.21,1341.4`, orientation `1.59587`. The target stays online during `.tele name`; its ordinary worldport ACK is captured. Casting 32239 then returns native `SMSG_CAST_FAILED`, reason 60, `SPELL_FAILED_NOT_HERE`.

**Native defect: fast-flight use does not require Artisan.** Before the Artisan receipt, ordinary `CMSG_CAST_SPELL` 32242, cast counter 2, produced own-caster `SMSG_SPELL_GO` and flight speed `26.600000381469727`. Saved riding flags were still 23, skill was 225, and spell 34091 was absent. The extension records this negative check as a failure and continues only to observe the separately authorized post-receipt case. It must not be reported as an all-five-riding-tiers PASS.

The pinned `src/APProgression.cpp::ProgressionSpells::OnSpellCheckCast` checks Apprentice mount eligibility, Journeyman eligibility for ground speed at least 100%, and native zone flight permission. `ProgressionPlayer::OnPlayerCanFlyInZone` requires Expert in Outland or Cold Weather in Northrend. Neither path checks Artisan for the +280% flight aura. This explains the learned-mount cast bypass; ordinary item/vendor acquisition was not tested. No live C++ change or rebuild was made.

The live extension completed in 149 seconds with **FAIL**, solely for the pre-Artisan cast bypass. Index 13 is the only new receipt, Artisan 919100013, applied once. Native reconciliation learned 34091 and raised riding skill from 225 to 300 and flags from 23 to 31. Subsequent ordinary casts in both Outland and Northrend produced own-caster `SMSG_SPELL_GO`, flight speed 26.6 and saved `amount1=280` auras. The pre-Artisan successful cast also saved an `amount1=280` aura, making the failed gate durable rather than a packet-only observation.

All 54 offline tests passed: 19 travel/extension tests and 35 shared runtime/client tests. The transcript contains 1,977 raw directional packets, three worldport ACKs and eight pings. Original receipt rows 0..12 and immutable binding fields remain identical, original evidence hashes still match, and GUIDs 1..3 have equal before/after snapshots. GM 13 and fixture 24 are offline. Level 77, XP, money, inventory and item instances remain unchanged. Read-only final observations are saved in `.local/travel-extension/final-observations.json`. `run.jsonl` SHA-256 is `64884b7b3179db8d06df906e39878e05dc173b17805f616f1852b0fc6c7af9a4`.

Evidence is isolated under `.local/travel-extension/`, including raw directional packets, durable snapshots, protected before/after snapshots and the deliberately failing summary. Actual airborne movement remains unproven because no airborne-position test is sent. The original `.local/travel-live/` evidence is not changed.

### Artisan cast defect fix, source only

`src/APProgression.cpp::ProgressionSpells::OnSpellCheckCast` now requires `Progression::RidingEligible(state, level, 3)` when an effect's `CalcValue(player)` is at least 280 for mounted-flight aura 207 or druid-flight aura 206. This covers +280% and +310% without a spell-ID exception. The existing ground-speed, Expert, Cold Weather and map checks remain unchanged. Unbound players still return before these AP checks.

The pinned `SpellAuraDefines.h`, actual `Spell.dbc` SHA-256 `d5cce1a83550dcfa9eb2f0251dbb11fd24c272534b2b1a9b230924a44d817ab3`, `spell_gen_mount`, and `spell_dru_swift_flight_passive` establish the effect shapes. Druid passive 40121 has aura 206 with base points 279, and its script can raise the amount to 310. Adaptive wrappers such as 47977 have mounted and dummy auras plus a script effect, not a fast-flight aura. Their native script selects a concrete child by skill and zone. The new guard leaves the wrapper and +150% child eligible for Expert and rejects a +280% child without Artisan. It does not classify every potentially flying wrapper as fast flight.

`tests/test_native_mount_cast.py` extracts and executes the production cast hook and zone-flight hook with small C++ boundary stubs and the real `RidingEligible` policy. Before the fix, it failed on 32242 with flags 23, level 77 and map 530, returning success instead of spell unavailable. After the fix, both strict and completion checks pass for the regression matrix, including +150%, +280%, +310%, druid passives, Artisan levels 69/70, Cold Weather levels 76/77, ground +60%/+100%, map restrictions, adaptive wrapper/child effects, and unbound players. Run it with `.venv/bin/python -m unittest discover -s tests -p test_native_mount_cast.py -v`. The new test and nearby progression, travel, extension, class-system, runtime-runner, realm-client and core-patch suites passed all 73 tests. The pinned core C++ codestyle check passed against repository `src`.

This is an offline source fix, not new live proof. No authentication, SQL write, GUI action, live binary change, restart, rebuild, host-core edit, or linked-source-archive edit was performed. The parent must create a fresh pinned build and obtain native cast rejection before Artisan plus successful post-Artisan casts. The recorded extension remains FAIL, actual airborne movement remains unproven, and the Artisan live-proof TODO is not complete.
