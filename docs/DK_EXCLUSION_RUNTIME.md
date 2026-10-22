# Unbound DK start and AP exclusion

## Native start and exclusion PASS

The parent-authorized `native-reviewed` run exited 0 after six seconds. Fresh GUID42 on marked account APV2F completed two ordinary logins at level55, map609/zone4298. Both raw INITIAL_SPELLS sets preserve Attack6603, Blood Presence48266 and Death Coil47541. Both native talent packets report zero free points. There is no AP binding or Store ingress. No selfcast was requested.

Parent independently parsed both raw spell/talent packet sets, checked both saved profiles, compared the complete protected tables exactly, and verified only the expected realm-count increment for account7. All characters/accounts were offline afterward. See `docs/verification/native-dk-exclusion.json` and `.local/dk-runtime-plan/native-reviewed/`. The first process-census refusal and its original reservation remain preserved separately.

This proves an unbound ordinary DK start and AP-v1 exclusion, not DK AP support, stock GUI behavior, combat or completion of the DK introduction. No config, Core, original character or client changes were made. The preparation history below remains source-only where stated.

AP v1 supports nine classes and excludes DK class 6. `Catalog.parse` rejects a DK manifest before any Store call. The new probe never constructs Store, binds a character, sends rewards or fabricates ingress. Constructing a local manifest solely to test Catalog rejection is not AP ingress.

## Corrected source contract, native proof pending

The earlier blocker was a mistaken test premise. The parent retracted the literal `SkipDKintro=0` requirement. This pinned Core has no such option. The objective is DK exclusion from AP v1 and an ordinary unbound level55 introduction start, not a fictional config boolean. No ignored key was added and no Core/config change was made.

The actual config `.local/v2-realm/config/worldserver.conf:2064` sets `StartHeroicPlayerLevel = 55`; line1685 sets `PlayerStart.CustomSpells = 0`. `WorldConfig.cpp:245` defaults heroic level to55. `source_evidence()` now validates those real settings, pinned source hashes, the normal create entrypoint/dataflow, Human DK default SQL start609/4298, the direct Ebon Hold quest-talent calculation and all three starting-spell DBC providers. It returns expected start facts and file hashes, not a `SkipDKintro` field.

The read-only source check passes against the real candidate. That resolves only the false source blocker. It does not prove live module behavior. Create/talent script hooks exist; a plugin that changes the start must fail the existing exact native level/map/zone/spell/talent checks. Both native logins must still report talent0, and all release, identity, eligibility, private credentials, protected-history and runtime-pin guards remain mandatory. No native run or release is authorized by this correction.

## Offline commands

```sh
PYTHONPATH=tests:. .venv/bin/python tests/verify_dk_runtime.py
PYTHONPATH=tests:. .venv/bin/python -m unittest test_dk_runtime test_runtime_runner test_realm_client
```

Default CLI only prints the constant plan. It does not read config, DBC, release files, authenticate, query SQL or create attempt files. Unit tests mock sockets and login boundaries, but also run `source_evidence()` against the real pinned files and DBC. A temporary file fixture with no invented setting passes; wrong heroic level, custom-spell setting, map/zone, talent calculation, create hook or source hash fails. Tests assert the returned facts, so a missing return cannot pass. They are not a native PASS. The implementation exceeds the approximate 200-line target to keep the packet, cleanup, provenance and protected-history guards local.

## Source findings

Paths below are relative to `.local/v2-build/20261019T191318.518327Z-mail-fixed/source` unless stated otherwise.

1. `CharacterHandler.cpp:561` calls `Player::Create`. `Player.cpp:496-517` obtains race/class `PlayerInfo`, relocates to its coordinates and creates its map. Lines572-584 select `CONFIG_START_HEROIC_PLAYER_LEVEL` for DK and assign the level. `ObjectMgr.cpp:4360-4432` loads those fields from `playercreateinfo`. `data/sql/base/db_world/playercreateinfo.sql:47` defines Human DK `(race=1,class=6,map=609,zone=4298)` at `2355.84,-5664.77,426.028`. This is the Ebon Hold introduction start, not a guessed Human Warrior start. Future preflight SELECTs the actual world row, and both saved phases require map609/zone4298/level55.
2. `src/server/game/Entities/Player/Player.cpp:13961-13983`, `CalculateTalentsPoints`, uses zero below56 for DK on `MAP_EBON_HOLD`, then adds quest/extra bonuses and applies the talent rate. Fresh unbound55 with no intro rewards should therefore expose zero. Both logins require the actual `SMSG_TALENTS_INFO` 0x4c0 player packet and `SmokeClient.talent_points == 0`. Zero is not treated as missing.
3. `playercreateinfo_skills.sql` supplies generic skill183 and DK skills770/772. Actual local client `SkillLineAbility.dbc` rows3999/17016/16433 give Attack6603/Blood Presence48266/Death Coil47541 respectively, with acquire method2 and minimum skill1. Class masks are 0/32/32. SkillRaceClassInfo rows5/896/895 admit Human DK. Death Coil's successor49892 has acquire method0, so the automatic-successor suppression does not replace starting47541. `Player.cpp:12130` loads default skills; `12264-12330` applies mask/rank/acquire checks and temporarily adds default spells outside the world. Custom spells are disabled by actual config. Action-bar rows alone are not evidence that spells are known.
4. `PlayerStorage.cpp:5591-5594` loads default skills/custom spells before additional saved spells. `Player.cpp:3322-3326` and `_SaveSpells` at `PlayerStorage.cpp:7928-7969` explain why temporary defaults need not have SQL rows. The raw native INITIAL_SPELLS set is the baseline. Saved `character_spell` rows are separately recorded and compared across relog, not required to contain every default.

The source guard checks pinned helper and default SQL inventories plus DBC providers using files only. Future live preflight separately checks actual world start/default skill rows before creation. The direct talent formula is not a skip-intro config check. Read-only review evidence is under `.local/dk-runtime-plan/source-contract-review/review.json`, with the 57-test log in `offline-tests.txt`. All 11,706 entries in the candidate's `source-files.sha256.json` match their pinned hashes; installed build hashes also match. These results supersede the old unresolved-setting notes in earlier preparation artifacts, not the pending native checks. See `CLASS_MATRIX.md` for the baseline failure history and `CLASS_SYSTEMS_RUNTIME.md` for the limits of earlier class/talent proof. Neither document nor any Matrix-owned file was changed.

## Future authorization boundary

The parent alone may supply `.local/dk-runtime-plan/native-reviewed/parent-release.json` after **all** Matrix work is released, including SA61's two new class9/11 cases and cleanup. No release template or usable grant is shipped. Required fields are `owned_release: true`, `native_matrix_released: true`, `account: APV2F`, `creation_limit: 1`, exact world/manifest hashes and numeric Unix `issued_at`/`expires_at`. Validity must be at most1800 seconds and current at each authentication. Expiry stops scheduling, not bounded offline cleanup.

Pinned candidate is `20261019T191318.518327Z-mail-fixed`:

- World `3b9b2bf9f946a1eeef5908e440ed917132c0559c4bc483ba14be199060641809`; manifest `6ac13239c2b11940904ece49ea6064c72980e433d6ef06aff587f36babc51553`.
- Image `sha256:55bfa1750408af5f5645166e47928aac6ecf0be92dd24005411cd96115f18ed9`; APProgression.cpp `85e1a31476fe3d918dd61bfba685401c520707d72dcc3d4579788c3b4baa83c7`.
- Combined patch `76342b88b9864f85525771ba51de7c2b78467343027075b83184bc76356aca6c`. Strict Artisan `build_evidence` and `runtime_evidence` are reused, not weakened. Runtime config must be the read-only actual config mount with matching hash and command.

A future explicit `--run` reserves exclusive `attempt.json`, never removes it and never retries. It checks competing runners without stopping them. Before first authentication it verifies private UUID, single private realm1, all characters/accounts offline, account7 APV2F's exact email/reg_mail markers, role0, online0 and private verifier. Fresh SELECTs must show fewer than10 characters, a same-account level>=55 and no existing DK. Historical Travel GUID24 level77 is not current eligibility proof and is never logged in or modified. Eligibility failure has no GM, `.levelup`, SQL-write or deletion fallback.

An exclusive `creation-intent.json` is written before authentication. Exactly one normal Human DK create packet is allowed. The first CMSG_PLAYER_LOGIN callback requires the original `CREATED <name>` event, a GUID absent from the preexisting population and >4, actual account7/name/race1/class6, offline55 and no binding before invoking shared authorization. There is no unconditional GUID enrollment. Relog uses only this proved owned GUID. TEST, GM13, APV2A and originals1..4 have no login path; shared Human Warrior/TEST defaults remain untouched.

The first root reservation stopped at `no_other_runners()` before authentication, SQL or creation because another verification process was present. Its `attempt.json` and `live-run.log` remain at `.local/dk-runtime-plan/`. Parent selected the separate `native-reviewed` namespace for a later exclusive attempt. Its marker must not be deleted or reused, and offline preparation processes must finish before release.

## Bounded native sequence

Two normal headless build12340 logins observe starting spells and talent0. Between them, normal logout saves actual start/profile/spell rows. Optional `--selfcast` permits exactly one explicit SELF Blood Presence48266 cast, only when source providers and the fresh native packet both confirm it. The shared travel SPELL_GO and Matrix aura parsers must observe actual caster/unit GUID and matching aura. No combat, movement, talent spending, equipment, chat, GM selection, teleport or progression packets are allowed.

Runner-local cleanup waits for owned characters/account to become offline even if connect, packet validation or the yielded body raises. Partial markers and new characters remain; no flags are cleared. Final checks require all actors/accounts offline. Dynamic protected snapshots cover all preexisting characters and available character child tables/stats, owned items, all AP bindings/child tables/queues and account access. Only the genuinely new DK is excluded from the protected population. Realm account counts may increase by exactly the number of new DKs, not arbitrarily. No scalar itemString query or gameplay SQL write exists. The normal DictCursor and shared list-normalized SELECT boundary are used.

Seven earlier Matrix PASS GUIDs32..38 and partial Warlock39 remain history, not DK evidence. This case would establish only an unbound start/exclusion exception using two protocol logins. It would not prove stock GUI behavior, complete DK introduction, DK AP support, a real AP room, or a full playthrough. Original client/private UI, production code/data/hashes, server state and Matrix sources remain untouched.
