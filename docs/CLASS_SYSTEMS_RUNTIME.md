# Bounded native class-system verification

`tests/verify_class_systems.py` uses fabricated AP ingress through `bridge.v2.Store`.
It does not connect to an AP room. GM quest completion and level setup are not a
legitimate playthrough, quest-check validation, or release proof.

## Run safely

1. Print the offline plan. This does not connect to SQL or either server.

   ```sh
   .venv/bin/python tests/verify_class_systems.py
   ```

2. Run the behavior tests.

   ```sh
   .venv/bin/python -m unittest discover -s tests -p test_class_systems.py -v
   ```

3. Check `.local/class-systems/run.jsonl` before considering another run. Each
   invocation creates one fresh GM0 player and one fresh TEST setup character.
   There is no resume, deletion, repair, or cleanup mode. Do not rerun to erase a
   failure. TEST had 7/10 characters before the first invocation.

4. Only on the existing private test realm, with the native smoke finished and
   TEST offline, run an independent fixture account.

   ```sh
   WOWPILAGO_DB_PASSWORD=test-only WOWPILAGO_TEST_ACCOUNT_PASSWORD=test-only \
     .venv/bin/python tests/verify_class_systems.py --run --account APV2D
   ```

APV2A and APV2B cannot be selected. APV2C..F require the existing exact fixture
email marker, security 0, no online session, and a free character slot. TEST must
be security 3 and offline before authentication. No existing TEST character is
logged in. The imported Runner requires successful creation and ownership/profile
checks before logging any character. Relogins accept only this invocation's new
GUIDs, with an additional rejection of GUIDs 1..4. The account creation budget
is one player plus one GM per invocation, regardless of remaining free slots.

SQL observation uses the imported SELECT-only connection. The only direct SQL
writes are Store binding, manifest, queue, and disconnected fixture status.
Character level, XP, money, inventory, spells, and talents are never updated by
runner SQL. Native authenticated commands and normal talent packets establish
state. Neither the legitimate AP room nor its character receives fixture items.
All characters, bindings, receipts, and history remain after success or failure.

## Source and packet contract

The clean core is
`.local/v2-build/20261019T150600.624050Z/source`.
The runner compares its pinned `APProgression.h`, `APProgression.cpp`, and
`APCatalog.h` byte-for-byte with this repository. The current catalog is
`4611c269173e443bff425e85a255fa086315ffdec0657c9098982d8e6fe9e1b0`.
It reuses the complete current Catalog-validated manifest, not an abbreviated
allowlist. NetworkItems use location -1, player 0, flags 0 and a random
`fabricated-class-systems-*` seed, clearly separate from real ingress.

The existing `tests/verify_runtime.py` and `tests/realm_client.py` are imported
without modification. Their persistent 30-second ping scheduler and
`character_spell(spell,specMask)` observation are preserved. Each command,
checkpoint, talent action, and durable state goes to JSONL evidence.

Pinned source bodies inspected for this run:

| Source body | Contract |
| --- | --- |
| `Player.cpp`, `GiveXP` and `GiveLevel` | Before-apply XP hook, cap-crossing remainder, native level veto |
| `Player.cpp`, `InitTalentForLevel`, `CalculateTalentsPoints`, `LearnTalent` | Native points minus spent, class/rank/prerequisite and five-points-per-row requirements |
| `SkillHandler.cpp`, `HandleLearnTalentOpcode` | `CMSG_LEARN_TALENT` 0x251, two little-endian uint32 fields, then native talent-state reply |
| `Player.cpp`, `resetTalents`; `SkillHandler.cpp`, `HandleTalentWipeConfirmOpcode` | Native respec recalculates points; normal request requires a real interactable trainer GUID and money |
| `PlayerGossip.cpp`, dual-spec option; `PlayerUpdates.cpp`, `UpdateSpecCount` | Native dual-spec teaching spells 63680 and 63624 must be self-cast; configured minimum level is 40 |

Talent.dbc identifies warrior talent 130 as row 0, ranks
16462/16463/16464/16465/16466, and talent 126 as row 1 with no prerequisite talent.
The runner sends ordinary talent actions, never `.learn all talents` or bonus
point modifications. Unknown talent 0 only requests a native state reply and
is not counted as coverage. Actual spending and tier checks use 130 and 126.
Saved `character_talent` rows supplement the free-point packet evidence.

Spell.dbc identifies riding spells 33388/33391/34090/34091/54197. Native module
eligibility requires levels 20/40/60/70/77. Journeyman needs Apprentice;
Artisan/Cold Weather need Expert. Expert can supply the ground prerequisites.
Mount 458 has mounted aura 78 and speed aura 32 with base value 59, meaning 60%;
23227 has the same aura types and base value 99, meaning 100%. These actual DBC
rows, plus dual-spec and Charge rows, are preserved in source evidence. Reading
a DBC row does not prove a mount cast or travel worked.

Charge 100 requires Battle Stance 2457 and level 4; its selected rank chain is
6178 at 26 and 11578 at 46. `.learn <spell>` acts on the GM's selected player,
not a trailing player argument. `.levelup <fresh-name> <positive-delta>` is used
only forward. Quest 13108 is fabricated setup through `.quest add`, `complete`,
and `reward`; QuestXP.dbc specifies 44100 XP at level 80/difficulty 8. No SQL XP
or bank injection is available as a fallback.

## Coverage boundaries

The bounded sequence tests an early unlock at level 1, native quest XP into the
initial cap and half-next-level full bank, exact release on Cap +10, native
above-cap refusal, talent spending and tier rejection, increasing caps through
80, early riding flags with delayed eligibility, Charge learning/ranks, later
release of eleven remaining talent reservations, and unchanged full relog/replay.
Every checkpoint logs out completely before querying saved character state.

The source includes spell-cast, trainer, flight-zone, access, item, and bot-related
hooks beyond these observations. Symbols and source bodies show compilation;
they are not runtime proof of every branch. Positive trainer respec, dual-spec
purchase/switching, mount casting, flight/travel, combat procs, expansion travel,
other classes including DK, and real UI behavior remain separate live gates.
Playerbots stays disabled. No claim is made about crash recovery or real AP
release readiness.

## Execution evidence

The invocation completed with exit 0 after 11 minutes 14 seconds. Evidence lives
under `.local/class-systems/`; `run.jsonl` contains the native observations and
`summary.json` the bounded result. `before.json` records actual account counts
and protected characters before fixture creation. `unchanged.sha256` records the
existing helpers and progression sources. `binary.sha256`, `live-process.txt`,
and `compiled-symbols.txt` connect the installed binary to the live process and
compiled class hooks. The observed world database reports ACDB 335.17-dev,
cache_id 17, with an archived build revision string of `unknown`; the binary
hash is used rather than pretending that string identifies a commit.

The live worldserver and installed executable both hash to
`6434b132b68a581a2046319c25795f9f5c1211ab2096b56898702a12542d83e8`.
No restart, configuration change, source edit, bot enablement, SQL character
repair, or history deletion occurred. The third native smoke had already
settled with PASS before TEST authentication.

The only fixtures created were APV2C `Apsofxvhhgsh`, GUID 12, binding 5, seed
`fabricated-class-systems-3b5e9c4ab4ad225209cd23f2`, and TEST setup GM
`Apsjxsocfsik`, GUID 13. Both are offline after completion. TEST now has 8/10
characters; APV2C has 1/10. `after.json` compares complete character rows for
GUIDs 1..4 with the pre-run snapshot and reports no differences. APV2A was never
authenticated or targeted; its account session ended independently during the
run. No runner command touched Apjourney or the existing original characters.

### Actual passed checks

| Gate | Native evidence |
| --- | --- |
| Cap/XP | Quest setup awarded native XP from level 1 to cap 10, XP 0 and bank 3800. Above-cap `.levelup` left level 10 unchanged. First cap receipt released exactly 3800 XP and cleared bank. Seven cap receipts allowed forward setup through 80. Higher levels used GM setup, not ordinary leveling gameplay. |
| Talents | Early unlock at level 1 left zero free points. At 10, row-1 talent 126 was refused despite one free point; row-0 talent 130 succeeded. Its five ranks were spent by 14; row 1 succeeded at 15 with five points already spent. Native entitlement at 80 was 60 with one unlock, then 71 after eleven later unlocks: 65 free plus six spent. This tests entitlement, not spending all 71 or rejecting a 72nd spend. |
| Riding | At 20, Journeyman-only flag 2 did not permit either ground spell, including explicit GM learn attempts. After the remaining flags arrived at 20, Apprentice alone was present. Journeyman was absent at 39/present at 40; Expert absent at 59/present at 60; Artisan absent at 69/present at 70; Cold Weather absent at 76/present at 77. Saved flags were 31. |
| Charge | Locked 100 and 6178 failed learning at 10 before permission. The ability receipt supplied base 100 at 10. Rank 6178 was refused at 25 and saved at 26; 11578 was refused at 45 and saved at 46. Rank spells and talent rows survived relogs. |
| Durability/safety | 26 full logout/save checkpoints, 25 exact applied receipt identities, identical ingress replay with unchanged final class state. Existing helper/source hashes still match. Six new behavior tests pass; full discovery ran 187 tests, 138 passed and 49 environment-dependent tests skipped. |

Final fixture progress reports cap_items 7, talent_unlocks 12, riding_flags 31,
banked_xp 0, level 80 and victory 1. That victory was reached through fabricated
setup and must never be presented as a legitimate AP victory or playthrough.

### Missing gates and needed extensions

1. Trainer respec and dual-spec purchase/switch/relog remain unexecuted. The
   source contracts were inspected, but a real trainer runtime GUID, interaction
   and native self-cast/switch evidence are still needed. No invented trainer GUID
   or command was sent.
2. Mount casts, ground speed, flight-zone/access checks, expansion travel, and
   real UI/travel/procs remain unexecuted. `OnPlayerCanTrainSpell`,
   `OnSpellCheckCast`, and flight/access branches have compiled/source evidence,
   not live branch coverage. Apprentice permission was first delivered at 20,
   so below-20 denial with its flag already present is not covered. Journeyman
   without Apprentice was tested at 20, not at its own eligible level 40.
3. Charge's previous-rank rejection at an otherwise eligible level, trainer
   purchase, casting in combat, and its level-4 boundary remain untested. The
   run proves the selected base and ranks' learning gates at the stated levels.
4. Other classes, DK behavior, positive Expert-only ground-prerequisite fallback,
   extra unlock/cap saturation receipts, crash recovery, and independent
   concurrent fixture runs remain untested. Do not mark those fullTODO gates
   complete from this run.
5. Real AP-room ingress and legitimate gameplay/release gates remain separate.
   Existing helpers need nearby-object discovery and narrow movement/teleport
   acknowledgement support before trainer/travel automation. No helper or
   production fix was required or made for the bounded gates above.
