# Talent switch runtime and funded continuation

## Native stock-client lifecycle PASS

Two completed stock-client phases on owned Rogue35 verified the lifecycle. An ordinary1000g dual purchase preserved primary three points and created secondary33 free; spending three secondary points gave30/30. One explicitly fabricated AP fixture unlock applied with secondary saved active, giving31/31. An ordinary1g primary respec gave34 primary free and31 secondary free, with Evasion known in both specs. Normal logout/re-entry with each spec active preserved those results.

Parent viewed the actual talent UI and independently checked saved money0, level50/XP0, two specs, primary active, reset fee10000, talent13792/specMask2, one unlock and six immutable receipts. Applied-index5 replay left receipt history and progress exact. Other41 characters and eleven frozen rewards remain unchanged. Public evidence is `docs/verification/native-talent-switches.json`; raw GUI and parent audits are in `gui-phase1-reviewed/` and `gui-phase2/`. All characters are offline and GUI96 is closed. Goal140/187 remains incomplete. This is fixture verification, not legitimate AP gameplay or a one-shot headless PASS.

## Preserved scripted failures

Parent **stopped scripted retries** after three failures. The later producer correction does not authorize reusing any consumed journal. All three attempts remain preserved.

Three scripted attempts failed and remain preserved. The first stopped before authentication on the single-template creature-schema comparison. The second completed the one-time1001g cash setup, then rejected the installed ASCII readback delimiter. The third confirmed the fresh trainer and balance, learned Improved Gouge rank3, then failed with `No unique source-confirmed wire option`. The matcher used fallback OptionText; the actual producer overrides it with broadcast text. The earlier saved checkpoint (one spec, primary spell13792/specMask1, money10010000, no talent unlock) is historical, not the current GUI state.

Do not rerun either consumed setup or continuation, repeat the cash command, or reset the fixture. Historical implementation and invocation details below describe code behavior only.

## Source-only gossip boundary correction

The shared pure `resolve_gossip(gossip, trainer, purpose)` accepts only a unique exact option in the current menu from the validated observed trainer GUID. It checks text, price, icon0 and box, then returns that packet's wire ID. It accepts no fallback aliases, case folding, substring matching or whitespace normalization.

| Purpose | Menu | Broadcast ID | Exact option | Copper | Box |
| --- | --- | --- | --- | --- | --- |
| Dual information | 4502 | 33762 | `How do I learn Dual Specialization?` | 0 | empty |
| Respec | 4502 | 62295 | `I wish to unlearn my Talents.` | 0 | empty |
| Purchase | 10371 | 33765 | `I wish to learn Dual Specialization.` | 10000000 | `Are you sure you wish to purchase a Dual Talent Specialization?` |

`execute_funded` opens a fresh root in the write session and resolves both dual and respec before its initial talent-state probe and first learn. The earlier read-only session's menu cannot satisfy this check. `choose` resolves again from each current menu; it caches no preflight wire across menus or logins. The existing allowed-send, one-use wire gate and pending wipe rules remain, and the menu is invalidated only after guarded send succeeds. Post-purchase roots need only respec: dual is correctly absent.

`source_evidence` pins ObjectMgr.cpp/.h, PlayerGossip.cpp, GossipDef.cpp, QueryHandler.cpp and locale/gender definitions, plus exact gossip/menu/broadcast and option/broadcast locale SQL hashes. It decodes selected actual SQL tuples and asserts the three nonempty, gender-equal enUS broadcast overrides, option types/flags/targets, price, icon, coded flag and literal box. The existing narrow dump decoder now selects the exact nine referenced broadcast IDs; a future trainer preflight compares those complete rows as well as the previous trainer tables. No SQL is executed by this source check.

ObjectMgr loads enUS at slot0 and skips enUS locale overrides. PlayerGossip uses **player gender** with `GetLocaleString`; both selected gender texts agree. Differing localized packets fail the exact enUS contract, including localized boxes. No locale normalization or fallback alias is accepted. QueryHandler's separate NPC body projection uses `BroadcastText::GetText`; this fix verifies option selection, not all NPC body text. Existing packet framing/header/menu handling remains; title is a TextID, not a body string. Type16 respec directly sends `MSG_TALENT_WIPE_CONFIRM`, retaining the exact trainer/10000-copper confirmation guard; menu4461 gains no selection authority.

The independent fixture is a hash-verified copy of the actual `funded-readonly-proof.json` root. Purchase tests use an explicitly synthetic source-derived label and exact box; they do not claim a captured purchase. Incoming fixtures never derive text or boxes from `GOSSIP`. Review artifacts, SQL copies, tests and preservation hashes are in `.local/talent-switch-plan/gossip-boundary-fix/`. The separate ASCII `|` money-prefix fix and all source IDs, funding/baseline, Date/schema/ambient, permissions and no-GO/no-MONEY funded guards remain unchanged.

## Historical source-only continuation implementation

`--continue-funded` is implemented for parent review and a later fresh grant. This change is **source-only readiness**, not native PASS. Goal remains **138/187**, not complete. No live auth, SQL, Docker inspection, GUI, grant, release, setup, or attempt was performed during this implementation.

The parent resolved the old missing-`StartedAt` blocker by approving the scope of a **future fresh read-only GM13 trainer lookup**. No old-process-continuity requirement remains. The new executor never uses the historical trainer GUID as current authority. It records fresh container ID, `StartedAt`, and world process identity (PID1 `worldserver`, Linux start ticks and boot ID), with matching observations at both ends of runtime inspection, for future audit.

The original `execution/` and `schema-reviewed-execution/` journals are consumed and immutable. **Never rerun money or setup, delete markers, recreate actors, clear fixtures, or repair state.** The second attempt applied 10010000 copper exactly once, then failed because its connected `.pinfo` parser expected a different leading field separator. Its failure remains a failure. `money_readback` accepts only leading `| ` → `¦ ` canonicalization; hyperlink pipes, exact GUID35/name/balance and online marker remain mandatory.

The default CLI prints a constant plan without observations. `--source-evidence` reads local files only, including preserved artifacts and complete source/build/install/config/DBC/helper evidence. Neither mode authenticates, queries a database, or inspects Docker:

```sh
PYTHONPATH=.:tests .venv/bin/python tests/verify_talent_switch_runtime.py
PYTHONPATH=.:tests .venv/bin/python tests/verify_talent_switch_runtime.py --source-evidence
PYTHONPATH=.:tests .venv/bin/python -m unittest tests/test_talent_switch_runtime.py
```

Implementation review and preservation hashes are in `.local/talent-switch-plan/funded-fresh-trainer-review/`. The previous source review remains untouched at `NEW.local/talent-switch-plan/funded-continuation-review/REPORT.md`.

## Historical invocation contract (no retry authorized)

The parent independently reviews source, performs the then-current census, and supplies the external grant and owner inventory. No grant is generated here. The only continuation command is:

```sh
PYTHONPATH=.:tests .venv/bin/python tests/verify_talent_switch_runtime.py --continue-funded --grant /parent/supplied/grant.json --owners /parent/supplied/owners.json
```

There are no output, resume, phase, arbitrary actor, trainer GUID, or retry options. The fixed journal `.local/talent-switch-plan/funded-continuation/` is now consumed and preserved. Exclusive, fsynced `attempt.json` consumed its one opportunity before runtime inspection, SQL, Store acquisition or auth; ambiguity cannot authorize another attempt. Its `money_reserved` is zero, and the funded journal refuses a `money-burned` record.

Grant requirements:

- `parent_authorized: true`, `purpose: "talent-switch-funded"`, exact `guids: [13,35]`, integer `creation_limit: 0`, integer `money_setup_copper: 0`.
- Exact `readonly_commands: [".npc info 79788", ".pinfo Apsckmrzjjql"]`.
- `prior_funding_attested: true` and `prior_funding_sha256` equal to the complete fixed `PRIOR_FUNDING_HASHES` mapping, also exposed in source evidence. This pins 23 preserved funding/review artifacts, including money-burned, successful target confirmation, original failure, connected readback, trainer observation, both raw snapshots, packet logs, old runtime and parent audit. No new money authorization is accepted.
- `hashes` equal to the **complete current JSON** from `--source-evidence`, not selected fields. It includes this runner, owned tests/documentation, shared helpers, original birth/manifest/receipt evidence, trusted GM13 creation evidence, core/module sources, actual local config, DBCs, build/image/install and prior funding hashes. Source changes invalidate old grants.
- Nonempty `release_id`; integer `issued_at` and `expires_at` with `issued_at <= now < expires_at <= issued_at + 1800`; all then-current `released_owners`.
- `owners_sha256` matches the supplied owner file. That file requires `purpose: "current-native-owners"`, a nonempty `owners` list, `all_released: true`, `no_other_runners: true`, and integer `observed_at` within the grant window.

Only the two supplied authorization files may be read until scope, TTL, funding attestation and owner inventory pass. Missing paths or invalid authorization fail before source/runtime/process/SQL/auth observations. The full current evidence is then computed and matched before process inspection and attempt reservation. Local process inspection refuses another potential native runner. Authorization is rechecked throughout login, command pumping, incoming packet handling, sensitive transport and ingress.

The original `--run` remains tied to its already-consumed fixed journal and its original grant purpose. It cannot serve as a funded fallback. `execute()` also refuses a funded context.

## Fixture and preflight

Only GUID35 Apsckmrzjjql on normal-security APV2C/account4 and control GUID13 Apsjxsocfsik on TEST/account1 may log in. Zero character creation. The original typed Human Rogue birth/profile and first-login evidence come from `.local/class-matrix-plan/third-reviewed-run/attempt-ec4bda0bfebd4870253b7396/class-4/`. `Runner.login(..., expected_profile=profile)` retains the normal role0 path. GM13 retains `MerchantRunner.reuse_control` and its trusted Human Warrior creation proof. No shared Runner/RealmClient or core/config/AP implementation is changed.

Binding25 must retain its full original manifest, seed `fabricated-class-matrix-dc792199e5793d75b748ebb7e20be853`, team0/slot1, original receipt prefix and checksum. Do not substitute a reduced catalog or another character. APV2C must still have ten characters. All42 characters and all accounts must be offline before the first login; eleven pending rewards remain frozen.

The complete normal preflight still verifies private database UUID, normal account identity/credentials/security, birth/profile, original binding/manifest/prefix, cap_items4, talent_unlocks0, ability5277 and saved5277/26669 specMask255, and the exact current trainer/menu/condition rows against pinned SQL dumps. The creature schema projection is only `id1` → `id` when both source alternate IDs are zero.

Funded preflight additionally requires exactly122 raw tables, exact saved actor35 level50/XP0/money10010000 and GM13 level1/XP55/money0, one spec/active0/reset0, no talents, instance0, and both positions already within five yards of the source trainer. The full saved funding snapshot is compared to the fresh offline baseline: every non-ambient row and column must match exactly. Wrong money, staged talents/specs/unlocks, changed receipts, another actor's state or an altered inventory fails before login. There is no top-up, movement, repair, or alternate authentication fallback.

## Historical funding validation

`prior_funding()` verifies the hardcoded hashes before interpreting any prior artifact. It validates the exact selected-player money confirmation, literal connected pinfo result, preserved timeout, and historical loaded-NPC observation without treating that observation as current authority. Raw packets reconstruct actual zero-XP exploration events; `source_tp` verifies level/XP, exact explored bits against AreaTable.dbc and unchanged taxi unlocks.

The pre-money → funded-saved comparison permits only documented source-backed TP/cash/save/ambient changes. Two additional **historical-only** deltas are checked exactly on comparison copies; raw files remain unchanged:

- GUID35 `restState`2 →1 while rest_bonus rises from0.13048 to281.167. Pinned `Player::SetRestBonus` sets REST_STATE_RESTED above10; `PlayerStorage.cpp` adds offline rested bonus during login. Player.cpp/Player.h/PlayerStorage.cpp are in current evidence.
- Exactly one unacknowledged binding25 Stormwind exploration check919701519 at `2026-10-19 23:53:55`. Pinned APCatalog.h maps it to zone1519/map0. `OnPlayerUpdateZone` → `ZoneChecks` → `RecordCheck` inserts the already-enabled check. Both module source files are pinned. No other AP change is allowed.

Historical achievement counters1149 (exploration) and4224 (highest money) are validated with their original bounded timestamp, not the date of the new run. All other character/AP state is exact under the existing narrow bookkeeping rules.

The separately pinned parent historical audit explains the earlier WG transition: worldstate3801 changed1→0,4024 changed4→5, and3781 reset as a battle ended. This precedes the second attempt's pre-money baseline. It is **not** an allowance for the new attempt. The new run starts with a fresh full runtime baseline and does not require historical process continuity.

## Fresh read-only proof and packet policy

The funded per-client transport mode permits GM13 exactly one `.npc info 79788`, followed by exactly one `.pinfo Apsckmrzjjql`. It rejects all write GM commands, including the original GO, SUMMON and MONEY commands even if old setup flags are fabricated. It also rejects SET_SELECTION, teleport/worldport acknowledgements, creation, arbitrary spells/commands and unrelated opcodes. Incoming teleports fail instead of prompting movement or repair. GM13 can open only one control session; subsequent GM logins are denied.

Both normal sessions remain open while the existing bounded paired pump services them and checks grants before incoming packets. The trainer response must reach its source-defined terminal `SpellSchoolImmuneMask` field. Validation requires a unique loaded Creature GUID with entry918, DB spawn79788, matching low counter, Current Entry918, phase1, instance0, source position and both actors within five yards of the **actual observed NPC**. `Not in world`, guessed DB-derived GUIDs, duplicate replies or a wrong position/entry/phase fail. A new runtime counter is valid when freshly proved; it need not match the old665 counter.

The fresh pinfo must report the connected exact player hyperlink/name/GUID35,1001g0s0c and online marker. Its leading ASCII prefix is canonicalized by the existing parser. Missing/wrong money or stale/offline output fails within the finite deadline; commands are never repeated.

GUID35 then sends a fresh native gossip hello to that exact observed GUID and receives the root4502 menu before any talent spending. Both sessions log out normally, saved pristine state is checked again with only ordinary login bookkeeping allowed (including source `SetRestBonus` state2→1 only when rest_bonus exceeds10), and GM13 performs no further operations. The shared sequence also completes a fresh exact-GUID gossip hello after the player's next login. In funded clients, a completed hello/response is a transport prerequisite for the first talent-spend packet; merely receiving an unsolicited menu or sending a hello is insufficient.

## Shared normal-protocol sequence

Original setup mode and funded continuation both call `execute_funded(setup)`. There is one sequence implementation:

| Checkpoint | Active spec | Earned | Spent active | Free |
| --- | --- | --- | --- | --- |
| Pristine | 0 | 33 | 0 | 33 |
| Learn203 ranks0,1,2 | 0 | 33 | 3 | 30 |
| Ordinary NPC1000g purchase; secondary | 1 | 33 | 0 | 33 |
| Learn203 ranks0,1,2 | 1 | 33 | 3 | 30 |
| One original-manifest919100020 ingress | 1 | 34 | 3 | 31 |
| Activate primary | 0 | 34 | 3 | 31 |
| Ordinary NPC1g primary reset | 0 | 34 | 0 | 34 |
| Relogs/switches/replays | 0/1 | 34 | 0/3 | 34/31 |

Pinned `APProgression::TalentPoints` returns33 from normal41 less eight reservations, then34 after one unlock. `Player::ActivateSpec` counts only active-mask spent ranks; never sum both specs. Talent.dbc203 is Rogue tab181 row0, three ranks13741/13793/13792. Row1 talent1827 rank0 is rejected before spending, after three points in each spec and after respec. Full talent/glyph responses and saved spec masks are checked, including Evasion in both native spellbooks and saved5277/26669 masks255.

Dual spec is bought through normal source-defined trainer gossip,4502 →10371 → purchase for10000000 copper, not direct teaching casts. First respec uses the actual source-confirmed wipe response for the observed NPC and10000 copper; the confirmation is consumed before transport. Gossip selections use the freshly received wire list ID, not guessed database option IDs. Only primary/secondary activation spells63645/63644 are allowed; switch completion waits for native SPELL_GO and talent state.

The locked Store attaches only binding25 and the parsed original full Catalog manifest. It never calls `bind` or `status`. Its only mutation API is `receive(len(original_prefix), items([919100020]))`. An exclusive durable ingress intent precedes the first receive. Replays use the identical index and item and must leave exactly one new applied receipt. This is FABRICATED fixture ingress, not real AP gameplay. No cap, ability, voucher, stock, purchase, item or unrelated AP mutation is permitted.

Final state requires earned34, primary34/secondary31, money0, reset cost10000 and only spec1's three spent talent points. Save comparisons retain ordinary source-pinned achievement bookkeeping for purchase/reset and dual-spec achievement2716, with exact bounded counter changes. Normal GUID4 and every other actor remain protected.

## Snapshot boundaries, cleanup and evidence

Every saved snapshot retains all122 base tables. Only source-known nonmerchant/nontrainer creature_respawn rows on noninstanced world maps may change, plus existing worldstate3781's uint32 WG countdown. AP merchant respawns, trainer79788, unknown/instance spawns, other worldstate values (including3801/4024), row inventories, comments and schema remain protected. Ambient audits contain full changed-row lists separately from the protected-state result. No whole-table or general timestamp exclusions were added.

Native/login/transport failures retain intent, packet logs, partial receipts and saved state. Socket closure and bounded offline waits cover body/connect/logout failures. Store closure cannot skip the two outer offline waits. Runtime/connect/constructor failures also receive durable failure evidence; cleanup failures cannot overwrite the original body failure. There are no SQL cleanup writes. A native PASS is written only after the complete sequence, final offline snapshot comparison and final saved-state assertions.

Offline checks exercise both full sequence models through real client send guards, deterministic in-memory framing/pumping, funding/grant/baseline refusal, exact next-index ingress/replay, immutable history, strict ambient boundaries, no-money/no-TP transport, runtime identity and cleanup. These prove source behavior under models; actual native timing and current runtime state remain for the parent's later authorized run.
