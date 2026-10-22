# Fresh Artisan native proof

Native PASS on the fixed candidate. This is fabricated AP ingress on a fresh fixture, not legitimate gameplay. The parent separately authorized deployment and this execution.

Run the safe plan from the repository root:

```sh
PYTHONPATH=.:tests .venv/bin/python tests/verify_artisan_runtime.py
PYTHONPATH=.:tests .venv/bin/python -m unittest tests/test_artisan_runtime.py tests/test_travel_runtime.py tests/test_native_mount_cast.py
```

## Parent execution handoff

1. Obtain explicit permission for the later owned runtime window. GUI40 and mail46 must release before deployment. The parent owns deployment, not this runner. Preserve Original4's normal journey outside the actual proof window. For the proof window only, require Original4, GUI40, and mail46 offline.
2. Wait for `.local/v2-build/20261019T191318.518327Z-mail-fixed/manifest.json` to report `success`. Deploy that candidate only. It preserves the completed first build and adds the independently tested login-mail callback fix in an isolated copy. The runner pins core/playerbots commits, protocol 2, image `55bfa1750408af5f5645166e47928aac6ecf0be92dd24005411cd96115f18ed9`, and APProgression.cpp `85e1a31476fe3d918dd61bfba685401c520707d72dcc3d4579788c3b4baa83c7`. It checks every module file against both current `src/` and the build snapshot, every installed file against the successful manifest, the read-only install mount, and both running `/proc/1/exe` and container-installed worldserver hashes. There is no build override or fallback. A runtime image that differs from the pinned image requires resolution by the parent, not weakening the guard.
3. After those releases and the new world are confirmed, create `.local/artisan-runtime-plan/fixed-owner-guard/release.json` with the following fields. Replace the placeholder with `installed_files_sha256["bin/worldserver"]` from that successful manifest. This file is the parent's attestation, not an automatic release detector. Do not create it during preparation.

   ```json
   {
     "owned_release": true,
     "gui40_released": true,
     "mail46_released": true,
     "world_sha256": "HASH_FROM_SUCCESSFUL_PINNED_MANIFEST"
   }
   ```

4. Only after explicit later authorization, run once with the existing private test-only credential environment:

   ```sh
   PYTHONPATH=.:tests .venv/bin/python tests/verify_artisan_runtime.py --run
   ```

   The runner queries APV2B's exact account ID, username, GM0 status, both private markers, password verifier, three existing offline characters, and free capacity. It logs their profiles without assuming that APV2B is account 2. It reserves one fresh creation through `FixtureOwner` and the shared client's CREATED-event/new-GUID authorization. GM13 is reused only through `MerchantRunner.reuse_control`, including its prior creation and release evidence, before player creation. No new TEST character is allowed.
5. Read `.local/artisan-runtime-plan/fixed-owner-guard/summary.json` and `run.jsonl`. Completion requires `PASS`, unchanged protected snapshots, both exact fast spells denied before Artisan and accepted after it, skill 300, and both saved native flight auras. Any failure preserves the fixture and all receipts. `attempt.json` prevents a second attempt. Do not remove it, reset flags, clear item history, delete characters, or substitute Player24. Escalate a failed attempt to the parent.

## What the native proof checks

| Stage | Native result required |
| --- | --- |
| 20, Apprentice receipt already pending | Ordinary 458 gives ground speed 11.2 |
| 40, Journeyman receipt already pending | Ordinary 23227 gives ground speed 14.0 |
| 60, Expert, Outland | 32239 gives flight speed 17.5; 32242 and 40192 each fail with 107 |
| 69, no Artisan | The same 32242 and 40192 each fail with 107 |
| 70, no Artisan | The same 32242 and 40192 each fail with 107; flags 7, skill 225, no training spell 34091 |
| 70, one appended Artisan receipt | Flags 15, including Expert/Artisan mask 12; native riding skill 300 and spell 34091 |
| 70, Artisan, same Outland map | The same 32242 gives 26.6 and saved aura amount1 280; the same 40192 gives 28.7 and saved aura amount1 310 |

The actual client Spell.dbc was read offline during preparation. 32242 is Swift Blue Gryphon, aura 207 base point 279. 40192 is Ashes of Al'ar, aura 207 base point 309. Both include mounted aura 78 and ground-speed aura 32. Runtime rechecks IDs, names, effect types, aura types, and base points, then records the DBC hash and full rows.

GM setup is restricted to forward levels through cap receipts, ordinary mount learning on the selected fresh fixture, and bounded online target travel. Riding training comes only from native receipt reconciliation. Client casts are ordinary self-target CMSG_CAST_SPELL packets. The imported client records native SMSG_SPELL_GO, SMSG_CAST_FAILED, speed, worldport ACK, and near-teleport ACK packets. No AP permission packet is forged.

The seed is private `private-fabricated-artisan-proof-*`. `Catalog.parse` validates the complete manifest. Received-item indexes start at zero and remain contiguous. Offline snapshots require prior receipt rows and immutable binding fields to stay unchanged. Logs include native flags, skill, receipts, item count, source identity, binary identity, and saved auras. Original1..3, Original4 during the window, and APV2B's existing three characters are snapshotted before and after. No gameplay SQL writes are used; `Store` owns synthetic bridge ingress only.

## Limits

This is fabricated AP ingress, not a real-room or normal-playthrough claim. No airborne position proof is attempted. Northrend Cold Weather and Kalimdor regressions are left to the earlier travel proof; they are not part of this bounded fresh run. No Druid or class switch is added. The production native-hook unit test covers aura 206 and the Artisan tier-3 guard.

Player24 already has Artisan index 13 and flags 31. Its history cannot supply a fresh pre-unlock check and remains intact. The old `6434b...` world is not acceptable evidence for this runner.

## Recorded execution

The passing run is `.local/artisan-runtime-plan/fixed-owner-guard/`. It created only fixture GUID 25 and reused proven GM 13. Both logged out normally. The parent independently observed level 70, online 0, riding flags 15 and skill 300. Protected snapshots match.

All 13 checks in `summary.json` passed on world binary `3b9b2bf9f946a1eeef5908e440ed917132c0559c4bc483ba14be199060641809`. Both fast mounts were denied at 60, 69 and 70 before Artisan. After the single Artisan receipt, the same spells produced speeds 26.6 and 28.7, with saved 280% and 310% auras. Ordinary 60%, 100% and 150% mount regressions also passed.

The first attempt failed before character creation because a preflight confused agent IDs 40/46 with character GUIDs. Its artifacts remain in the parent evidence directory. The corrected guard requires all characters offline and separately checks owner-release attestations. An executable regression covers both no-online success and any-online rejection. Fourteen Artisan offline tests pass. No receipt, attempt marker or failed fixture was deleted to retry.

The source-only callback fix also remains distinct from a controlled delayed-callback live replay. This successful native run includes normal login/logout on the linked fix, but does not claim the original database timing was reproduced.
