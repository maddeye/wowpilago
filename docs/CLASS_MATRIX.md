# Native class matrix executor

## Final-two completion run

Status: **PASS for the two fresh native fixtures.** Parent review verified the combined nine-class gates across both preserved runs and 90 phase snapshots. See `docs/verification/native-class-matrix.json`. This is not a one-shot nine-class run or combat/gameplay proof. The earlier seven results and partial GUID39 remain preserved.

Attempt `final-two/attempt-75f2df98abd6fef5626db97e` exited 0 after 15 minutes 56 seconds, within the fixed 1,800-second bound. Exactly two characters were created. Both completed bound, locked, early-permission, cap-bypass-denied, all four normal-level checkpoints, relog and identical replay.

| Class | Fresh GUID | Account | Saved selected ranks | Normal levels | Fresh packets | Duration |
| --- | --- | --- | --- | --- | --- | --- |
| Warlock | 40 | APV2C | Fear 5782 / 6213 | 8 / 32 | 20 | 474.6 seconds |
| Druid | 41 | APV2D | Hibernate 2637 / 18657 | 18 / 38 | 20 | 477.5 seconds |

Warlock's 45 and Druid's 44 starting spells came from actual native INITIAL_SPELLS packets, not default SQL rows. The post-run SELECT/artifact audit verified every raw packet hash and parsed set, baseline preservation, saved selected-rank gates, highest eligible active rank, manifest/binding identity, contiguous immutable receipt prefixes and identical replay. All preexisting GUIDs 1..39, the complete GM-role table and every preexisting binding/child table compare exactly equal before/after and in the final offline snapshot. All characters/accounts are offline. Final counts are B10/C10/D5/E4/F1. GUID39 remains preserved at its partial level 8.

Evidence is in `final-two/final-audit.json`, `final-protected-snapshot.json`, `artifacts.sha256.json`, and the attempt's `before.json`, `after.json`, `summary.json` and `run.jsonl`. All 31 earlier failure hashes and all 297 third-run files remained unchanged, including its FAIL summary and immediate GM13-online snapshot. The final raw packet log SHA256 is `11c7f19737b460162c21a74e21f4f24d4b3095d11e9e1a6714c4bf5181c493a4`. Candidate, world, image, CPP, manifest and base-manifest proofs still match the pins below. No native code, server restart, GUI, original-client login, real AP ingress or DK creation was used.

Offline checks passed 104 targeted tests and the full suite of 360 tests with 49 skips. Skipped tests are not native proof. No nine-class combat or real AP gameplay claim follows.

Parent authorized only two fresh fixtures in `.local/class-matrix-plan/final-two`: Human Warlock class 9 and Night Elf Druid class 11. GUID39 remains protected and cannot be resumed. The seven completed third-run cases are not repeated. The default offline plan still includes all nine; `--classes 9 11` selects only the fixed Catalog profiles, rejects duplicates, unknown IDs and DK before runtime access, and budgets two slots from fresh account SELECTs. No profile or race override exists.

The final-two live entry requires `authorized_classes` exactly `[9, 11]`, `creation_limit: 2` and `prior_partial_guid_preserved: 39` in its own matching release before runtime inspection. Old releases and attempt markers are not reused. This fixed two-case run has a new 1,800-second deadline, never modified after loading. The historical default runtime remains 3,600 seconds. All 20 player logins per complete case remain required. Protected snapshots now also include the complete GM-role table.

```sh
PYTHONPATH=.:tests .venv/bin/python tests/verify_class_matrix.py --classes 9 11
PYTHONPATH=.:tests WOWPILAGO_TEST_ACCOUNT_PASSWORD=test-only WOWPILAGO_DB_PASSWORD=test-only \\
  .venv/bin/python tests/verify_class_matrix.py --run --classes 9 11
```

Before creation, 104 targeted offline tests passed. Fresh SELECTs proved B10/C9/D4/E4/F1, exact marked private role0 credentials and all 39 characters/accounts offline. `preflight.py` made one normal GM13 login using original class-system ownership proof, then deliberately raised `RuntimeError` without any commands, creation or Store ingress. Matrix-local exceptional cleanup returned with exact protected before/after equality, GM13 Human Warrior unchanged and all accounts offline. See `probe-result.json`, `probe-before.json`, `probe-after.json` and the hashed raw `probe-run.jsonl`. The seven earlier complete cases also passed an artifact-only recheck in `prior-seven-recheck.json`.

Run the live command only once in the parent's exclusive window after the offline tests and SELECT preflight pass. The exclusive marker prevents retry. Final-two evidence and the optional single GM13 read-only exception probe remain separate from all historical summaries. A combined seven-plus-two native result requires parent review; it is not a nine-class one-shot, GUI, real AP gameplay or nine-class combat proof.

## Preserved third-run history

Status: **PARTIAL, NOT a nine-class PASS.** The parent-authorized third run in `.local/class-matrix-plan/third-reviewed-run` stopped at the 3,600-second scheduling deadline. Seven classes passed, Warlock is partial and Druid was not created. Both earlier failed attempts and their exclusive markers remain protected history. The first attempt created GUID30 and incorrectly expected Core-derived starting spells in saved SQL rows. The second created GUID31 and failed because PyMySQL returned an empty tuple where the receipt guard expected a list. Parent fixed shared `Runner.query` to return `list(cursor.fetchall())`. Neither failure required a native or gameplay SQL repair.

Before the third run, 77 targeted unit tests passed. SELECT-only actual-driver preflight verified GUID31's empty receipts as a list, passed `guard_receipts([], [], [])`, checked all accounts offline and verified the matching release and live candidate. Actual counts were B=10, C=1, D=4, E=4, F=1. `capacity_budget` assigned exactly nine fresh characters to C, filling it to ten without using B or TEST. Evidence is in `third-reviewed-run/unit-tests.log` and `read-only-preflight.json`.

## Third-run native results

Attempt: `third-reviewed-run/attempt-ec4bda0bfebd4870253b7396`. The real `--run` exited 1 after 60 minutes 22 seconds, including normal logout cleanup. No retries, restarts, native changes or gameplay SQL writes were used. Exactly eight fresh characters were created, all on APV2C. Final account counts are B=10, C=9, D=4, E=4, F=1.

| Class | GUID | Result | Starting spells | Fresh INITIAL_SPELLS packets |
| --- | --- | --- | --- | --- |
| Warrior | 32 | PASS native fixture gates | 54 | 20 |
| Paladin | 33 | PASS native fixture gates | 48 | 20 |
| Hunter | 34 | PASS native fixture gates | 45 | 20 |
| Rogue | 35 | PASS native fixture gates | 45 | 20 |
| Priest | 36 | PASS native fixture gates | 42 | 20 |
| Shaman | 37 | PASS native fixture gates | 44 | 20 |
| Mage | 38 | PASS native fixture gates | 42 | 20 |
| Warlock | 39 | PARTIAL, deadline, saved level 8 | 45 | 13 |
| Druid | none | NOT EXECUTED | none | none |

Each PASS includes bound/locked/early-permission/cap-bypass-denied, all four normal-level checkpoints, relog and identical replay. Independent artifact checks matched each saved phase to its login sequence, parsed the raw packet, checked its SHA256, baseline preservation, selected-rank SQL and highest-active native rank. Mage GUID38 produced actual Frost Armor 168 SPELL_GO and matching aura packets. There is one matching SPELL_GO, plus 35 matching aura observations across Mage's connections, not 35 casts. No nine-class baseline combat claim follows.

The deadline stopped Warlock before queuing the next needed cap item. Its last completed gates include level 7 and level 8; rank 5782 was eligible at 8, while 6213 remained ineligible. No level-31/32, relog or replay PASS is claimed. Do not reuse GUID39 or a prior failed GUID by inserting it into `known`.

The original `summary.json` remains FAIL with `protected_unchanged: false`. `protected-diff.json` shows its sole difference was GM13 `online: 0 -> 1` immediately after exceptional cleanup. The shared `Runner.login` performs its offline wait after its context block, which an exception skips. Native logout packets completed, but the immediate snapshot raced the saved offline flag. Subsequent SELECT-only checks found all characters/accounts offline and every protected table exactly equal to `before.json`, including all old failed queues and originals. Evidence: `cleanup-read-only-verification.json`, `final-protected-snapshot.json` and `independent-final-audit.json`. All 31 hashed prior-failure files remained unchanged. Do not rewrite the original summary or snapshot to turn it green.

After execution, matrix-local `login` gained an exceptional-path offline wait, without changing shared login or native code. Regression tests cover nested player/control logout ordering and fresh-packet validation failure. The post-fix suite passed 99 tests; actual SELECT-only `offline(13)`, empty-receipt and full protected-snapshot checks also passed. This cleanup fix has not had another native execution. An independent audit's first SELECT incorrectly referenced a nonexistent `character_spell.disabled` column; that read-only query failure is preserved separately, and the corrected audit reads actual rows using the executor's existing `get` convention.

Timing is the remaining harness assumption: completed classes took 463.4 to 482.9 seconds, with 20 player login/logout sequences each. Nine cannot fit in 3,600 seconds with this sequence. The deadline was not extended. Any future execution needs parent review of the scheduling plan and a new exclusive release namespace; this run authorizes neither additional creation nor partial-fixture continuation.

Binary/source evidence was rechecked after cleanup. Candidate `20261019T191318.518327Z-mail-fixed`, world `3b9b2bf9f946a1eeef5908e440ed917132c0559c4bc483ba14be199060641809`, image `sha256:55bfa1750408af5f5645166e47928aac6ecf0be92dd24005411cd96115f18ed9`, APProgression.cpp `85e1a31476fe3d918dd61bfba685401c520707d72dcc3d4579788c3b4baa83c7`, manifest `6ac13239c2b11940904ece49ea6064c72980e433d6ef06aff587f36babc51553`, and base manifest `0edea8dba721f996f00cf0b5c95e3576fff1ad4dd6e637fd8c0ad45b06f1285b` still match. Run-time Python source hashes are in `read-only-preflight.json`; post-cleanup-fix hashes are separate in the final audit.

## Offline checks

```sh
PYTHONPATH=tests:. .venv/bin/python tests/verify_class_matrix.py
PYTHONPATH=tests:. .venv/bin/python -m unittest test_class_matrix test_runtime_runner test_realm_client
```

The default command prints a Catalog-valid plan using local Spell.dbc. It does not write an attempt or contact services. Unit tests use synthetic DBC rows, mocked native connections and Store boundaries. They check orchestration and packet guards, not worldserver behavior.

`tests/verify_class_matrix.py` owns a single `MatrixRunner`, not nine login implementations. Shared `Runner.login` and `guard_character` accept an optional expected profile, defaulting to Human Warrior. Existing smoke, merchant, trade, transfer, class, travel, Artisan and crash callers retain that default. Shared snapshots remain Human-Warrior-only and are not used for matrix player snapshots. TEST explicitly rejects a non-Human-Warrior profile. A runner-local client factory supplies the matrix packet allowlist without replacing any global guard or client.

## Profiles and capacity

| Class | Race | Faction | Selected ranks | Normal levels |
| --- | --- | --- | --- | --- |
| Warrior | Human | Alliance | Charge 100 / 6178 | 4 / 26 |
| Paladin | Human | Alliance | Lay on Hands 633 / 2800 | 10 / 30 |
| Hunter | Orc | Horde | Freezing Trap 1499 / 14310 | 20 / 40 |
| Rogue | Human | Alliance | Evasion 5277 / 26669 | 8 / 50 |
| Priest | Human | Alliance | Psychic Scream 8122 / 8124 | 14 / 28 |
| Shaman | Orc | Horde | Purge 370 / 8012 | 12 / 32 |
| Mage | Human | Alliance | Polymorph 118 / 12824 | 8 / 20 |
| Warlock | Human | Alliance | Fear 5782 / 6213 | 8 / 32 |
| Druid | Night Elf | Alliance | Hibernate 2637 / 18657 | 18 / 38 |

Catalog version remains `4611c269173e443bff425e85a255fa086315ffdec0657c9098982d8e6fe9e1b0`. The selector rejects drift and checks actual Spell.dbc column 39 against Catalog levels. Only ranked chains without reagent, skill or totem setup are selected. Required baseline forms must already be starting-known. No class/race modification or unrelated GM spell learning is permitted.

The historical 25-character population is not a capacity guarantee. Future `--run` reads all five `APV2B..F` counts, account offline state, exact email and reg_mail markers, role0 security and matching private credentials. It checks the private server UUID and requires every character/account offline before reserving nine total slots against the ten-character account limit. The reservation and actual snapshots are saved before authentication. It rechecks account capacity before each creation. No SQL creates, deletes, gameplay writes, overflow, retry or reset fallback exists.

Create exactly one fresh character per class. APV2A and originals 1..4 never enter a login path. TEST gets zero creations. The only reused GUID is GM13, proved by `MerchantRunner.reuse_control` through Artisan, including original class-system creation logs, exact account/name/GUID/profile and offline release. Its expected profile is always Human Warrior, independent of the player class.

## Parent release and provenance

The executor's `--run` requires `.local/class-matrix-plan/third-reviewed-run/release.json` before any network or database access. Parent explicitly authorized copying the matching release from `fresh-baseline-proof/release.json` into this new namespace. Existing markers in the original root and `fresh-baseline-proof` remain unchanged; no continuation of GUID30 or GUID31 is authorized.

1. The deployed candidate is `.local/v2-build/20261019T191318.518327Z-mail-fixed`, not the first full build directory. Its world hash is `3b9b2bf9f946a1eeef5908e440ed917132c0559c4bc483ba14be199060641809`. Image is `sha256:55bfa1750408af5f5645166e47928aac6ecf0be92dd24005411cd96115f18ed9`, module APProgression.cpp is `85e1a31476fe3d918dd61bfba685401c520707d72dcc3d4579788c3b4baa83c7`, and combined core patch is `76342b88b9864f85525771ba51de7c2b78467343027075b83184bc76356aca6c`.
2. The first full build `.local/v2-build/20261019T183021.602493Z` remains unchanged. The candidate preserves its provenance in `base-manifest.json`, SHA256 `0edea8dba721f996f00cf0b5c95e3576fff1ad4dd6e637fd8c0ad45b06f1285b`. Require that digest and the candidate manifest's `base_manifest_sha256`; do not invent a `first-full-manifest.json` or rewrite the base to match the candidate.
3. Reuse Artisan's strict build/process evidence: success, pinned commits/image/module inventory, source helpers, installed files, read-only candidate install mount and matching mounted/running executable hashes. Artisan release is `.local/artisan-runtime-plan/fixed-owner-guard/release.json`; its native summary records 13 checks. That release does not authorize the matrix.
4. Matrix release fields must include `owned_release: true`, `mail_lifetime_fixed: true`, matching candidate `manifest_sha256`, `world_sha256`, and the exact `base_manifest_sha256` above. Parent must review crash evidence and explicitly authorize ownership before supplying it. A release boolean is not crash-regression proof.
5. Future execution creates an exclusive root `attempt.json` and unique attempt directory. An existing reservation refuses another invocation before runtime inspection; the executor never deletes it or retries failed creation. Parent must review partial history before considering any new authorization. Private password variables must both equal `test-only`. Before runtime inspection, reuse the crash verifier's read-only `no_other_runners` check; never call its kill/restart helpers.

The third run uses `PYTHONPATH=.:tests .venv/bin/python tests/verify_class_matrix.py --run`, with both private password environment variables set to `test-only`. The new exclusive marker prevents a second invocation. Crash recovery, release ownership and service maintenance remain the parent's responsibility. No restart, fault test or native change is part of this run.

## Native sequence

Estimate 30 to 60 minutes. One shared 3,600-second scheduling deadline covers all classes. The original 20-minute estimate did not account for ordinary 20-second logout waits across nine classes and multiple checkpoints. Check the deadline before each class, phase, command, queue and outgoing packet. On expiry, schedule nothing further. Logout and bounded offline cleanup remain allowed afterward. Preserve partial results rather than extending the deadline during a run. Preserve partial characters and append-only AP history.

1. Reserve creation before authentication, then use normal `RealmClient.connect(race=..., class_id=...)`. Its authorization callback reads the actual server character row and rejects wrong race/class/account/name before the very first CMSG_PLAYER_LOGIN. Matrix additionally requires GUID >4, fresh offline level 1 and no binding before first login. All relogs recheck exact profile and owned GUID. Save authorization, creation and starting spell evidence separately, including partial failures.
2. Log out and recheck fresh offline/unbound identity before Store binding. Generate a unique runtime seed and complete class-specific Catalog manifest. Store owns AP binding/ingress writes only. Preserve seed, GUID, binding, manifest and receipt history. Starting spell packets must contain the named class baseline, must not contain the selected chain, and must satisfy baseline-form prerequisites. Every player login checks a fresh native INITIAL_SPELLS packet before yielding to player actions. Every saved phase performs a normal observation-only reload and checks the entire initial baseline again, then reads saved SQL rows after logout. No previous connection's spell set substitutes for a fresh packet.
3. Try both selected `.learn` ranks without permission and verify neither saves. Append the class ability permission at level 1, wait for contiguous applied native receipts, try both ranks again and verify level-pending denial. Send one exact initial negative cap probe targeting level 11 while cap is 10 and assert saved level stays 1. This is separate from the forward-within-cap setup allowlist.
4. Visit base-minus-one, base, second-rank-minus-one and second-rank levels. Release only enough normal cap receipts for each target, use forward-only GM fixture level setup, and try the two selected learns. Assert selected-rank absence below each normal level and presence at eligibility in saved learned rows, with base learned before the second rank. Native INITIAL_SPELLS must omit locked/ineligible ranks and contain the highest eligible selected rank. Core can hide a superseded lower rank from the active packet while preserving its saved learned row. Native `.learn` tests the learn gate, not trainer gossip or pricing. Log out/save after every phase, checking actual level/profile, all starting spells, cap receipts and immutable binding. Then relog and replay identical ingress, asserting unchanged saved spells, progress, binding and applied receipt prefix.
5. Mage must have ordinary starting Frost Armor 168. Send actual CMSG_CAST_SPELL on self, require matching native SPELL_GO and AURA_UPDATE/AURA_UPDATE_ALL for that GUID/spell, and log raw packets. No Python CanLearn substitute or GM learn fallback exists. Preserve before/after protected snapshots and per-class partial results on failure; do not replace fixtures.

The client permits only protocol authentication/enumeration/login/logout/ping/time-sync, exact expected-profile creation, GM selection of the owned player, exact approved fixture chat, and Mage's normal Frost Armor packet. No talent spending, teleport, purchase, equip, arbitrary cast, aura cancellation or gameplay packet extension is enabled.

Protected snapshots cover every preexisting character's spells, talents, auras, inventory, skills and owned item instances, plus all preexisting AP bindings and AP child tables, including archived history. Character rows must remain unchanged except GM13's login bookkeeping; its identity/level/offline state and other saved tables remain protected. Originals 1..4, APV2A and failed prior fixtures are included. Errors and partial GUIDs remain in attempt evidence. SQL observation is SELECT-only; Store is the only AP writer.

## Baseline observation fix and parent review

`baseline` means the actual native starting spell set, not saved learned rows. GUID30's original `class-1/initial.json` contains 54 distinct spell IDs, including Heroic Strike 78 and Battle Stance 2457, without Charge 100/6178. Its `fresh-offline.json` records an empty `spells` array. The original summary says `protected_unchanged: true`. These observations are compatible, not evidence of lost baseline spells. Parent's later SELECT also found no `character_spell` rows. No product or SQL repair is needed.

Source references below are relative to `.local/v2-build/20261019T191318.518327Z-mail-fixed/source/src/server/game/`. They describe the pinned deployed candidate, not an upstream guess.

- `Entities/Player/PlayerStorage.cpp:5591-5594` loads default skills and custom starting spells before `_LoadSpells`. `_LoadSpells` at 6673 reads additional persisted learned rows; an empty result is valid.
- `Globals/ObjectMgr.cpp:4593-4632` loads `playercreateinfo_spell_custom` into race/class `PlayerInfo.customSpells`. `Entities/Player/Player.cpp:12104-12127` applies these when the custom-spell configuration is enabled. Skill-derived defaults also enter through default skills and `LearnSkillRewardedSpells`; the non-world path at 12328-12330 uses temporary `addSpell`.
- `Entities/Player/Player.cpp:3322-3326` marks temporary additions `PLAYERSPELL_TEMPORARY`. `Entities/Player/PlayerStorage.cpp:7928-7969`, `_SaveSpells`, skips temporary entries and only inserts NEW/CHANGED spells. Not every native starting spell needs a `character_spell` row.
- `Entities/Player/Player.cpp:2809-2834`, `SendInitialSpells`, emits active, current-spec native spells, excluding removed entries. `addSpell` at 3179 onward deactivates superseded lower ranks. This is why packet and persisted selected-rank assertions differ.

New `login-N.json` evidence records the actual raw INITIAL_SPELLS payload, payload SHA256, GUID, sequence and parsed set, including semantic failures. Each saved phase records its own `lastFreshNativeSpellSet` after a normal reload. This is historical evidence for that sequence, not a permanent current-state cache. The original run did not log raw INITIAL_SPELLS, so its parsed `initial.json` cannot be retroactively claimed as raw-packet evidence.

Offline regression checks cover zero saved rows with baseline present in a literal packet, missing baseline in a fresh packet, missing fresh packets, locked selected ranks in a packet, saved selected-rank gates and all nine pre-CMSG_PLAYER_LOGIN profile guards. Shared profile-aware helpers and AUTH readiness logic remain untouched.

Historical review proposals after the first failure, superseded by the parent's separate third-run authorization above. These are not continuation permissions:

1. Review `.local/class-matrix-plan/baseline-fix/`, including the copied original failure, copied root marker, offline test log and independent artifact inspection. Original failure status remains FAIL. Native composite crash PASS and all eleven frozen pending histories remain separate preserved evidence.
2. Smallest proposed rerun path is a NEW namespace such as `.local/class-matrix-plan/baseline-fix/reviewed-run-1`, with its own parent-issued release and exclusive attempt marker. It must pin these reviewed source hashes and candidate hashes, record the prior failure path/hash, enforce the same one-creation-per-class and 3,600-second bound, and freeze GUID30/binding history as preexisting protected data. This is a proposal only; no namespace switch or runnable bypass is added by this fix.
3. Alternative is a typed GUID30 continuation, not generic resume. Before any login, prove original creation/run artifacts and their hashes, exact APV2B account/name/profile/security/markers/credentials, offline state, manifest/seed and actual binding identity/checksum/history. Do not authorize by adding a pinned GUID to `known`. A diagnostic may do only one normal relog, with no GM, Store ingress or creation. No diagnostic was performed for this fix.
4. Recheck all actual character/account SELECT counts and exclusive runtime ownership. Parent reported APV2B holds nine characters, GUIDs 5/7/9/25/26/27/28/29/30, so one slot remains there; all nine fresh cases still fit across B..F subject to new SELECT proof. Agent/task IDs 40/46 are not proof of created characters and must not enter a future ownership guard. Parent chooses the next execution path and its separate authorization; this document grants none.

## Limits and DK exclusion

All AP ingress is tagged `fabricated AP ingress; NOT real AP client, gameplay, or release-gate evidence`. A future class PASS means bounded native fixture gates, not a legitimate class playthrough. Baseline combat for the other classes remains unproved without actual fights. Frost Armor alone does not establish combat viability. GUI gameplay, trainer economy and real AP-room ingress are excluded.

The earlier Warrior talent proof spent six points on rows 130/126. All twelve releases make 71 points available at level 80; this matrix need not spend every tree or repeat that proof nine times.

DK is EXCLUDED AP v1. Catalog rejects class 6 before Store binding, and APWorld has no DK class option. No DK is created by this executor. A future separate unbound native DK case needs parent-approved eligibility/capacity and ordinary level-55 start, starting spells/map, no AP binding/rewards and no GM level setup. APV2F's historical level-77 character is not current eligibility proof. Source-only exclusion tests are not a native DK creation PASS.
