# World-process crash/restart verifier

The WORLD PROCESS scenario now has a composite live PASS from the original GUID 29 run plus its narrowly authorized two-relog continuation. The original one-shot summary remains FAIL and is preserved unchanged. No additional crash or character was needed. See the recorded execution section below. Earlier preparation and failed attempts remain documented as history.

## Safe commands now

```sh
PYTHONDONTWRITEBYTECODE=1 python tests/verify_crash_runtime.py
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_crash_runtime.py -v
```

The first command prints the plan without creating artifacts or contacting anything. The second runs mocked/pure behavior tests. Do not run the full SQL test suite as part of this preparation.

## What the later live run does

One newly created, marked SEC_PLAYER human warrior on APV2B is the only login target. No GM or TEST login is used. Existing characters on APV2B do not need deletion; the account needs a free slot, exact `wowpilago-fixture@invalid` email marker, security zero, and offline status. Shared `Runner`/`realm_client` creation authorization rejects every preexisting GUID. Subsequent logins require this invocation's known-created GUID greater than 4 and exact account/name/race/class ownership.

The independent `fabricated-world-crash-*` seed uses `Catalog` and the shared full valid manifest fixture. `Store.bind`, `Store.status`, and `Store.receive` provide synthetic ingress. No AP room is contacted, no real journey is rebound, and no historical receipts/check acknowledgements are reset.

1. Create, cleanly log out, bind the offline level-1 fixture, and snapshot its starting state. Queue bag AP ID `919100040` and five-voucher AP ID `919100033` at indices 0 and 1. Prove both receipts are durable and unapplied with no inventory/progress effects.
2. SIGKILL only `wow-test-worldserver-1`. Confirm stopped exit code 137. Use `docker start` on the same container. Verify identity, image, config/mounts, restart policy, and `/proc/1/exe` hash. Require the pending queue to be byte-for-value unchanged. Login the owned fixture and wait for exactly one bag and five vouchers, then logout and prove persistence across relog.
3. Queue another bag/voucher pair at indices 2 and 3 while that same fixture is online. Wait for actual applied database receipts and prove the exact item rows, authorization, placement, and ten-voucher total. Confirm the player is still online, disable clean logout for that socket, close it abruptly, and SIGKILL the world. Restart the same container and compare the entire durable snapshot to the pre-kill proof.
4. Relog twice, staying seven seconds each time, beyond the five-second native queue poll. Require identical receipts, physical GUIDs, inventory, progress, stock/purchases, spells, and check rows. The final total is two bags and ten vouchers, one bag per physical receipt, not two effects from either receipt.

Each bag must have one item instance, owner equal to the new GUID, entry 21841, count one, flags exactly 1 (soulbound, not wrapped), one backpack placement at bag zero/slot 23..38, and exactly matching per-GUID authorization. Owned orphan items fail. Starter inventory and non-reward state must remain unchanged. The initial bound login may naturally record starting-area checks; their exact timestamps/acknowledgements then remain unchanged across the second batch and relogs. Item `playedTime` alone is excluded because elapsed online time is not a reward effect.

Preexisting character/private AP data is snapshotted before and after, including GUIDs 1..4, other fixture characters, legacy AP tables, and the normal journey's binding/history. These are private observation artifacts, never login targets. The observer accepts only single SELECT statements. Only Store writes AP rows; native protocol actions own character/inventory writes. No SQL character, inventory, currency, or spell writes, deletes, triggers, SQL connection kills, or history resets are used.

## Parent execution guard, later only

The parent must first release every GUI/native/AP bridge runner and maintenance owner, and finish logging out the normal AP journey. This cannot be inferred merely from a quiet socket. The release file is an explicit parent attestation, not a lease that can exclude every external host/operator.

1. Reserve an exclusive maintenance window. Stop/release the GUI94, normal4, travel APV2F/TEST13, bridge, and all other fixture owners through their owners. Do not use this verifier to force them offline.
2. Observe all current character/account online flags as zero, enumerate every existing GUID, and inspect the current full world container ID. Require every unrelated binding to be exactly `disconnected` and no unrelated Store advisory-lock owner. Preserve all pending receipts and the normal AP room/history. Never clear, repair, or log in failed fixtures to satisfy this guard.
3. Create a private JSON release file using the schema below. Use a fresh Unix `issued_at`, the full observed world ID, the complete offline GUID roster, and `frozen_pending_sha256` generated below over **all** previous unapplied rows. The checked-in template is deliberately unapproved. Never populate it while another owner is active.
4. Only then invoke the live command below. Review the saved summary and protected snapshots before releasing maintenance.

```json
{
  "world": "wow-test-worldserver-1",
  "image": "sha256:55bfa1750408af5f5645166e47928aac6ecf0be92dd24005411cd96115f18ed9",
  "world_id": "FULL_64_CHARACTER_OBSERVED_CONTAINER_ID",
  "issued_at": 0,
  "all_agents_released": false,
  "normal_ap_journey_offline": false,
  "exclusive_maintenance": false,
  "offline_guids": [],
  "frozen_pending_sha256": "REQUIRED_SHA256_OF_ALL_PREVIOUS_UNAPPLIED_ROWS"
}
```

### Generate the frozen-history field, parent only

After all owners explicitly release maintenance, use the parent's already authorized read-only DictCursor connection. This is a recipe, not a command executed during preparation. It does not connect, authenticate, write SQL, or issue a release by itself:

```python
import sys
sys.path.insert(0, 'tests')  # Run from the repository root.
from verify_crash_runtime import FROZEN_PENDING_SQL, frozen_pending_digest

# cursor is the parent's existing pymysql DictCursor, with native value types.
cursor.execute(FROZEN_PENDING_SQL)
frozen_pending_sha256 = frozen_pending_digest(cursor.fetchall())
# Put this exact string into the parent release's frozen_pending_sha256 field.
```

The query is exactly:

```sql
SELECT * FROM acore_characters.mod_archipelago_reward WHERE applied=0
```

Do not filter by binding, GUID, account, protocol, or status. Keep every column and duplicate row. The helper serializes each full row with `json.dumps(default=str, sort_keys=True, separators=(',', ':'), ensure_ascii=True)`, sorts these row strings lexically, joins them with commas inside `[]`, and SHA-256 hashes the UTF-8 bytes with no trailing newline. Use native DictCursor values, including timestamps, rather than a CLI-rendered TSV/JSON export. Empty history still requires the explicit digest `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`. A missing or malformed field fails before external access; a well-formed but wrong digest fails at the read-only preflight before creation.

The reported read-only observations were binding 3/GUID 7 with seven pending receipts, binding 7/GUID 15 with one, and binding 9/GUID 18 with one, all offline/disconnected without owning Store locks. Counts are context, not an attestation or a substitute for full rows. They do not authorize execution. Normal4 pilot40 and mail46 remain active; this preparation does not release or stop them.

Future execution command, **not executed during preparation**:

```sh
WOWPILAGO_TEST_ACCOUNT_PASSWORD=test-only WOWPILAGO_DB_PASSWORD=test-only \
  python tests/verify_crash_runtime.py --run --release /private/path/maintenance-release.json
```

`--run` without a structurally valid release fails before Docker or database access. Releases expire after 900 seconds. The exclusive guard rechecks the release, online flags, disconnected bindings, roster, frozen digest, and unrelated Store locks before creation/login, on login-context exit, before every state snapshot, before/after ingress and applied-receipt waits, before each kill, after restart/offline proof, and at final protection. Only this invocation's new binding may be excluded from the digest, after verifying it belongs to the fresh GUID outside the released roster. Applied own receipts may disappear from that pending selection; no preexisting receipt may disappear, become applied, change any column, or be joined by an unknown pending row. There is no ignore/allow-pending flag.

The existing full protected snapshots additionally compare all preexisting character/AP history, including already applied receipts and bindings. Both protected snapshots must match the released pending digest as well. This reuses the full snapshots rather than introducing another history store. The verifier takes a nonblocking local maintenance file lock and rejects other local Python runtime/GUI/bridge/provisioning processes. Parent attestation remains mandatory for external runners, tools not recognized by the process scan, and maintenance owners that use no common lock. A concurrent writer can still race these observations; do not run without the exclusive reservation. Provisioning guards are unchanged.

### Why pending offline history is safe to freeze

Read-only source inspection of the pinned archive's `source/modules/mod-archipelago/src/APDelivery.cpp` shows `DeliveryWorld::OnUpdate` selecting only `r.applied=0` rows joined to `characters` with `c.online=1`, then resolving `ObjectAccessor::FindPlayer` before calling `ApplyQueuedReward`, around lines 329..340. `ApplyQueuedReward` immediately requires `Available(player)`, lines 348..351. `Available`, lines 58..63, requires a live session, matching session player, no loading/closed socket, `IsInWorld()`, and no teleport/removal. Disconnected status alone does **not** prevent native delivery. Unrelated characters/accounts must stay offline at every guard, and their owners must remain released. This is source evidence for the frozen-history premise, not live validation.

## Runtime pins and failure behavior

The reference topology is `../wow-test/compose.yaml` plus `.local/v2-realm/override.yaml`, project `wow-test`, ports 3724/8085/13317. Those files are not edited or applied. The verifier never runs compose, rebuilds, recreates containers, or starts from a mutable tag.

The required image ID is `sha256:55bfa1750408af5f5645166e47928aac6ecf0be92dd24005411cd96115f18ed9`. The fixed candidate world binary SHA-256 is `3b9b2bf9f946a1eeef5908e440ed917132c0559c4bc483ba14be199060641809`. Every native module file must match its successful manifest and copied source. The read-only install mount must reference `.local/v2-build/20261019T191318.518327Z-mail-fixed/install`. This candidate includes the Artisan cast guard and login-mail callback lifetime fix. Its completed base build remains unchanged. Composite live verification is recorded below; no new one-shot PASS is claimed.

The restart policy must already be `no`; otherwise the run refuses before creating a character. It never changes policy, so there is nothing to restore. Auth/database must remain running with unchanged container IDs and start timestamps. They are never killed, restarted, or recreated.

### Challenge readiness

Implemented the readiness fix identified in `docs/RESTART_CLIENT.md`. Docker proxy TCP accept is no longer sufficient. `read_world_challenge(timeout=2)` receives a complete unencrypted build-12340 `SMSG_AUTH_CHALLENGE` from world port 8085 without sending bytes. It requires header `00 2a ec 01`: big-endian size 42, little-endian opcode `0x01ec`, followed by all 40 payload bytes. Fragmented reads share one two-second deadline, not a fresh timeout per fragment.

`health()` retries EOF, proxy close, and socket errors/timeouts within its existing 120-second readiness deadline. Each probe is capped by the remaining deadline. Wrong size/opcode raises `ProtocolError` immediately, without retry or a blanket `RuntimeError` catch. The half-second interval only paces failed probes; elapsed sleep never establishes readiness. Container ID/image/config/mount checks, executable hash, and auth/database container IDs/start timestamps remain required.

Validation: `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_crash_runtime.py -v` passed all 27 tests. Six new tests cover accepted socket then EOF followed by a valid challenge, partial header, partial payload, truncated header/payload retry, wrong opcode/size fail-closed behavior, and socket/overall deadlines. The changed-identity health fixture now supplies a full challenge. Existing empty-PyMySQL-tuple canonicalization and frozen-history tests remain intact.

The current running container `4b7de1464f41e8106a954718adb09ca6753a10e409e9b905d488d429d4eb905c` passed passive `health()` plus a separate helper read in 0.1845 seconds total. Header was `002aec01`, payload length 40, binary `3b9b2bf9...`, image `55bfa175...`; identity/binary/auth/database checks passed unchanged. The local process census found no runtime verifier, GUI, bridge, or AP server. No process was stopped or restarted for this check. No SRP, authentication, character creation/login, SQL access, or gameplay occurred.

Re-run only the passive challenge helper from the repository root while all runtime owners remain stopped:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests python - <<'PY'
from verify_crash_runtime import no_other_runners, read_world_challenge
no_other_runners()
packet = read_world_challenge()
print('header=' + packet[:4].hex(), 'payload_bytes=' + str(len(packet) - 4))
PY
```

This fixes readiness only, **not crash-recovery PASS**. No fourth crash attempt was made. Failed GUID 27/binding 17 and its pending bag/voucher were not resumed, applied, deleted, or reset. Frozen-history protection still covers all 11 pending receipts, the nine older rows plus these two. The preserved GUID 26 SELECT check and snapshot canonicalization fix were not changed. Shared `verify_runtime.py`, `realm_client.py`, native code, and configuration were not edited.

Native delivery waits 45 seconds per batch, shared offline waits 35 seconds, and subprocess/database/socket operations have finite timeouts. There are at most two SIGKILLs, with no fault retry loop. A failed kill/start/identity check stops the scenario. Failure can leave the world stopped; the parent must inspect saved evidence before deciding whether to start that same pinned container. No cleanup deletes fixtures or hides failed evidence. A new invocation creates another fresh fixture, never resumes or overwrites a failed run's history.

Artifacts go to a unique mode-0700 `.local/crash-runtime-plan/run-*/` directory. Available release/source/runtime records, manifest, creation GUID, queued/applied/relog snapshots, protected before/after state, bounded world log tail since this invocation began, and summary are retained. Treat these DB snapshots as private. Preflight failures can occur before a scenario summary exists; the nonzero exit/exception is not a PASS. No automatic restart rollback, character cleanup, or artifact deletion is attempted.

## Recorded attempts

The parent stopped retries after three failed attempts. All failed fixtures and evidence remain intact.

1. The first preflight refused the still-running AP room server. The room was then stopped gracefully with SIGINT after saving and backing up its real progress. The strict process census was retained; a proposed room exception was removed rather than weakening ownership checks.
2. `.local/crash-runtime-plan/run-20261019T193331Z-77b00289/` created owned fixture 26 and binding 16, then failed before any kill because PyMySQL returns an empty tuple for empty results. The snapshot now canonicalizes row sequences as lists and uses `sorted`. An executable empty-tuple regression and a SELECT-only check against actual fixture 26 verify that harness fix. Its rewards were not cleared or reset.
3. `.local/crash-runtime-plan/run-20261019T193803Z-c76606ac/` created owned fixture 27 and binding 17. One actual SIGKILL exited 137, the same pinned container restarted, and `queued-after-restart.json` exactly matched the durable unapplied bag/voucher queue. The subsequent client login failed with `Server closed connection`. The world stayed running, protected snapshots matched, and no recovery PASS was claimed.

A subsequent challenge-ready run, `.local/crash-runtime-plan/run-20261019T194751Z-ae22a830/`, created fixture 28. One actual kill/restart and the queued-to-applied transition succeeded, but the harness incorrectly expected item flags 9. Actual delivery correctly saved flag 1, soulbound. Flag 8 means wrapped and must not be required. The corrected assertion, negative wrapped-item test, and complete first-batch verifier now pass against that captured real MySQL evidence. The fixture and its applied history remain intact.

The original doubtful assumption was that a listening world port is sufficient readiness for the next authenticated client session. Do not create another fixture or repeat process kills until the connection stage and cause are established. Do not log in earlier failed fixtures or apply their queues merely to make preflight pass.

## Recorded execution: GUID 29 continuation

The parent explicitly authorized only the known-created GUID 29, `Apsgkxtddgmv`, on marked SEC_PLAYER APV2B/account 3 and binding 19. Original evidence is `.local/crash-runtime-plan/run-20261019T195228Z-7c423b5d/`. That run completed both actual world SIGKILL barriers with exit 137, preserved the queued first batch across restart, applied and relogged the first batch, then proved the second applied online snapshot exactly equal to the second post-restart snapshot. It failed only when the final relog saw AUTH's cached offline realm. Its FAIL summary and world log are not overwritten.

A valid native world challenge can precede AUTH's realm-cache refresh, configured privately with `RealmsStateUpdateDelay=20`. The shared `authenticate(..., ready_timeout=0)` keeps the default single-list behavior. `Runner.login()` requests 45 seconds and polls REALM_LIST on the same verified SRP socket, once per second, until a realm is unlocked with `flags & 3 == 0`. No new SRP exchange occurs while polling. Invalid bounds fail before networking; malformed lists and bad server proofs fail closed. Fragmented realm responses share a bounded deadline. World authentication, session-key endianness, loopback connection, and profile guards before CMSG_PLAYER_LOGIN remain unchanged.

Private `.local/finish_crash29.py` has no target/resume options. It pins all 20 original artifact hashes with aggregate SHA-256 `d4a955c246259e266f5454174b0528619f109242f206590219b80c13d67ea67b`, validates creation/name/account/profile/seed/manifest and receipt history, and checks both original exit-137 records against their same-container restart evidence. Before refreshing only a private copy of the parent timestamp, it observes all accounts/characters offline, verifies the running binary and original post-second-kill container/start identity, checks the complete 11-row frozen pending digest, and compares protected rows to the original before snapshot. Only then does it authorize the exact original known-created GUID. The released offline roster remains 1..28, excluding owned 29. Native character creation, foreign player-login packets, Store ingress, and new crashes/restarts are explicitly refused.

Live execution completed at `.local/crash-runtime-plan/continuation29/20261019T195911Z/summary.json` with `event=PASS`, explicitly labeled **composite WORLD PROCESS scenario proof**. Two fresh ordinary GUID 29 sessions stayed 7.000132 seconds each and completed native logout request/response/completion before account-and-character offline confirmation. Session totals were 28.604468 and 29.720432 seconds. Both AUTH lists were already ready, realm 1 at `127.0.0.1:8085`, unlocked, flags zero; the delayed-cache transition is exercised by literal protocol unit fixtures rather than claimed from this ready live realm.

`protocol-0.json` and `protocol-1.json` record timings, realm state, world challenge/auth response, enumeration, player login/world entry, time sync, and normal logout completion. `relog-0.json` and `relog-1.json` contain exact durable rows, each equal to original `second-applied-online-proof.json` and `second-after-restart.json`. `verify_effects(baseline, current, 2, 29, 19)` passes for both: bag GUIDs 351 and 352 each have entry 21841, count one, flags exactly 1, owned placement and authorization; vouchers remain 10; character level 1, XP zero, money zero. Item `playedTime` alone remains excluded by existing logic. The two protected snapshots equal the original protected-before snapshot. All 11 historical pending receipts, including GUID 27's two, retain their exact digest. Original hashes were rechecked after execution, including the untouched FAIL summary and log.

The continuation created zero characters, queued zero rewards, issued zero additional kills/restarts, used no Store or GM session, and performed only SELECT SQL observation plus normal AUTH session-key/native login/logout writes. World container/start identity remained unchanged. This does not turn the original one-shot FAIL into a one-shot PASS; a future canonical full run is separate and was not executed here.

Validation: 169 offline tests passed across realm client, shared runner, crash runtime, class matrix/systems, Artisan, travel/extension, merchant, trade, and transfer helpers. Literal fragmented-socket tests cover cached offline/locked/invalid realms becoming ready with the same key and exactly one SRP exchange, default single-list compatibility, timeout, malformed lists, bad server proof, bounded fragmented reads, and invalid timeout values. The private continuation's executable safety checks also rejected creation, foreign/protected GUID login, ingress, rerun, and crash calls before socket writes. Logs are `.local/crash-runtime-plan/continuation29/tests.log` and `execution.log`. No SQL effects suite, C++ build, GUI, real AP room/bridge, database crash, or controlled COMMIT/publication fault was run.

## Scope and a future controlled breakpoint

These are WORLD PROCESS crash/restart tests with synthetic Store ingress. Neither coarse kill claims deterministic COMMIT-before-publication coverage. They do not prove an AP bridge process crash, a legitimate AP playthrough, host/power-loss durability, or database crash recovery.

`tests/test_v2_effects_sql.py` already tests transactional rollback at insertion/update points and an actual SQL connection kill during a paused CALL followed by replay. `docs/CORE_PATCH.md` describes unknown COMMIT outcomes, no transaction replay, ordered durable verification, and fail-stop behavior. This verifier adds a native world-process boundary instead of repeating SQL-only tests. It does not inject lost COMMIT acknowledgements.

Historical `nm -C --defined-only` inspection of the former `6434b132...` binary found the symbols below. These addresses do not apply to the fixed candidate. Resolve its symbols and relocation afresh before any debugger experiment:

| Link-time address | Symbol |
| --- | --- |
| `0x6e9a61` | `WoWPilago::ApplyQueuedReward(Player*, unsigned int, unsigned int)` |
| `0x6e7c77` | `WoWPilago::(anonymous namespace)::VerifyCandidate(...)` |
| `0x6e5828` | `WoWPilago::(anonymous namespace)::Publish(...)` |

In the matched source, `ApplyQueuedReward` performs the whole CALL, ordered receipt read, saved-state comparison, and `VerifyCandidate`, rejects an uncommitted result, then calls `Publish`. A future separately approved debugger experiment could stop at the reward call's `Publish` entry, verify its caller/owned binding/receipt and runtime relocation, then kill before the first live mutation. The same helper also serves purchases, so a bare symbol breakpoint is insufficient. These are link-time symbol addresses, not assumed runtime addresses or proof a breakpoint was hit. Release uses `-g0`; source-line breakpoints are not established. No debugger was attached, no production fault hook was added, and no controlled publication fault was executed.
