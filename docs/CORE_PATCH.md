# Audited core patch

`patches/azerothcore-v2.patch` targets AzerothCore commit
`9fb906bb7296212ff42fc95ff73a92aaf8554f0d`, matching project-root `support.json`.
It was generated from `git archive` of that commit in `/tmp`, not from the host
working tree. Existing host modifications were excluded. No host core tracked
files, client files, TODO entries or commits were changed.

## Apply to an isolated core

```bash
CORE=../wow-test/azerothcore
SCRATCH=$(mktemp -d /tmp/wowpilago-core-XXXXXX)
git -C "$CORE" archive 9fb906bb7296212ff42fc95ff73a92aaf8554f0d | tar -x -C "$SCRATCH"
python tools/apply_core_patch.py --core "$SCRATCH"
python tools/apply_core_patch.py --core "$SCRATCH"  # already applied
```

`--core` is mandatory. The tool checks project-root `support.json`, the checkout's
HEAD when `.git` exists, and SHA-256 of all thirteen selected files before writing.
An archive needs no `.git` or extra support file. Its selected-file hashes attest
the supported sources, not the entire archive. Unrelated files are not attested.
A different checkout HEAD fails even if these thirteen files match.

Already-applied detection requires both `git apply --reverse --check` and the
complete patched fingerprints. Partial patches and local edits to selected files
fail without application. The tool deliberately refuses the existing modified
host `ScriptMgr.h`; do not reset user changes to make it pass. Port those changes
separately in an isolated integration checkout.

## Hook contract

All hook additions are generic `PlayerScript` hooks with matching `ScriptMgr` dispatch.
Flags are appended before `PLAYERHOOK_END`, preserving existing numeric flags.
The existing constructor enables all hooks by default; explicit subscriptions
must include the corresponding new flags. Boolean dispatch is deny-if-any.
Void hooks default to no action, and permission hooks default to true.

```cpp
void OnPlayerBeforeApplyXP(Player*, uint64& finalXP, uint32& maxLevel);
bool OnPlayerCanAddSpell(Player*, uint32 spellId, uint8 specMask, bool temporary, bool learnFromSkill);
bool OnPlayerCanTrainSpell(Player const*, uint32 trainerSpellId);
bool OnPlayerCanAccessMap(Player const*, uint32 mapId, WorldLocation const* destination, bool loginCheck);
void OnPlayerCheckItemLevel(Player const*, Item const*, bool& ignoreRequiredLevel);
void OnPlayerSaveToDB(Player*, CharacterDatabaseTransaction, bool create, bool logout);
```

The flags are `PLAYERHOOK_BEFORE_APPLY_XP`, `PLAYERHOOK_CAN_ADD_SPELL`,
`PLAYERHOOK_CAN_TRAIN_SPELL`, `PLAYERHOOK_CAN_ACCESS_MAP`,
`PLAYERHOOK_CHECK_ITEM_LEVEL`, and `PLAYERHOOK_SAVE_TO_DB`.

### XP

The final-award hook runs after favored-zone, partial-play-time, RaF and rested
calculation. Award, bonus, sum and loop remainder use wide arithmetic. The rested
API still takes uint32, so its input is saturated at that API boundary. Existing
XP-source hooks remain at their callers and are never invoked again here.
World/trial hard-cap returns and no-XP/death eligibility checks remain intact.
Scripts can lower, but cannot raise, the world/trial maximum.

The module should calculate room to its cap in uint64, bank overflow once, and
reduce `finalXP` to the accepted amount. Already-custom-capped players still
reach the hook. Reaching the effective cap writes `PLAYER_XP=0`. If a script only
lowers the cap without normalizing the award, the core passes the remaining XP
through this same hook once more, at the actual capped level, before discarding
it. That second call contains remainder only, with no multipliers or source
hooks repeated. Normalizing the initial award avoids this second call.
Do not bank the same normalized overflow twice. At the true level-80 maximum,
the module must discard excess rather than bank it.

The loop subtracts a threshold only after actual level advancement, stops on a
level veto or zero threshold, and respects the effective maximum. XP logs exclude
cap-discarded XP and saturate packet fields. The stored XP field is also uint32;
a level veto with more than UINT32_MAX unconsumed XP saturates that field rather
than wrapping. Durable banking and receipt/release transactions belong to the
module, not this patch.

### Learning and trainers

`_addSpell` checks permission after spell validation and before packets, spell-map
mutation, skill changes or passive casts. `Trainer::GetSpellState` checks
permission before returning Available. `TeachSpell` already calls CanTeachSpell
before charging money, so list and purchase permission agree. Normal class,
race, skill, level, rank, prerequisite and profession checks remain.
The module must inspect learn-effect trigger IDs as well as the trainer spell ID.

### Travel and saved login

Teleport permission receives a concrete destination before teleport cleanup or
other effects. The old late teleport hook is unchanged. Map admission calls the
new hook with `destination=nullptr` before continent and GM success returns;
the old dungeon-specific hook stays in its original position.

Saved login checks the final resolved location after transport/taxi/instance
recovery and before normal map creation. A second check covers the actual map
selected by map-creation fallback, including a preselected transport map. Denial
removes transport passenger membership, clears movement transport state, saved
taxi destinations and entry-point taxi path, discards map/instance selection,
and relocates to the race/class start. The fallback must have valid coordinates
and pass the permission hook too; otherwise login fails. A locked homebind is
not used as the permission fallback. Core admission checks are not replaced.

Map 530's Outland versus Blood Elf/Draenei starter-area policy belongs to the
module. Map-only admission cannot resolve that distinction. The module must use
the teleport/login destination and fail closed on unknown areas for a binding.
Travel denial returns false without teleport side effects. Live boat departure
handling and every-route behavior still need realm testing; this patch does not
add a transport-specific departure relocation policy.

### Equipment and saves

Both public CanUseItem signatures remain. A private common validator receives
instance context only from the owned-item path. The new hook is called only for
an instance failing RequiredLevel, with `ignoreRequiredLevel=false`. It can waive
that comparison alone. Template-only callers never receive an exemption.
Ownership, faction/class/race, skill/spell, holiday, proficiency, reputation and
existing script validation remain in place.

The save hook receives the existing transaction immediately after
`_SaveCharacter(create, trans)` in the transactional SaveToDB overload. Append
module state to it; never commit it from the hook. Existing callers retain commit
ownership. Hook invocation is not proof that a transaction committed.

No ItemScript trade hook was added. Binding without a BOP-trade window, existing
mail/trade/sale vetoes, and normal CanBeTraded checks are sufficient for the
researched issuance policy. Authorization must remain per GUID. No item-template
or global client-query level changes are included. Stock-client equip/use command
fallbacks belong to the later module work.

## SQL transaction contract

The patch also fixes the database engine needed by the transaction-aware save
hook. A private per-connection `m_inTransaction` starts false. Both raw Execute
and prepared Execute, including parameter-binding failure, suppress statement
reconnect/replay while it is true. ExecuteTransaction checks START TRANSACTION
before running any payload, then keeps the guard through COMMIT and rollback.
It reports success only after an acknowledged COMMIT.

| Outcome | Engine action | Result-task future |
| --- | --- | --- |
| START fails | No payload or COMMIT. A connection loss may reconnect/retry START before any payload. | false if START still fails |
| Raw/prepared statement fails | Stop before the tail; attempt rollback on the original connection only. | false |
| COMMIT acknowledgement is lost | Never replay COMMIT or payload; attempt same-connection rollback. The database may already have committed. | false, outcome unknown |
| Rollback fails | Preserve the original statement/COMMIT error; close the uncertain connection without reconnecting. | false |
| A later Execute begins | May reconnect before START or an independent autocommit statement. Never resume the failed transaction tail. | Depends on that new operation |

Outside transactions, existing raw/prepared reconnect-and-replay behavior remains.
An absent handle after failed rollback can reconnect on the next Execute. Public
void Begin/Commit/Rollback methods remain available and maintain the guard, but
ExecuteTransaction uses checked Execute calls for START and COMMIT. Rollback
always disables reconnect/replay, including when called directly. Keepalive skips
a discarded handle; SQL escaping reconnects before using its character set rather
than passing a null handle to the C API.

The pinned caller audit found ExecuteTransaction only in TransactionTask's shared
TryExecute and DatabaseWorkerPool::DirectCommitTransaction. Async commits use
TransactionTask or TransactionWithResultTask. The latter sets its future false
on nonzero errors. DirectCommitTransaction still has its public void return, so
it cannot report success to a caller. Ordinary connection Execute callers are
AdhocStatement, PreparedStatementTask, the worker pool's two DirectExecute
paths, and ExecuteTransaction itself. Pool BeginTransaction only constructs a
query list; it does not open a SQL transaction. No external direct callers of
the connection's void transaction methods were found in the pinned src tree.

All three deadlock retry loops retain their existing bounds: one minute for async
tasks and five retries for direct commits. They now stop if a retry returns a
non-deadlock error. Without this caller fix, a COMMIT acknowledgement lost during
a deadlock retry would trigger another whole transaction. No connection-loss
retry is added at this layer.

This restores the engine's transaction boundary, not application recovery.
AP must use idempotent whole CALL plus durable verification to resolve unknown
COMMIT outcomes before publishing or granting again. Never nest a self-committing
CALL in a purported enclosing transaction. General inventory dirty-state reset
behavior is not changed here. External SQL disconnect tests against the native
engine belong to the parent runtime work and are not claimed by these checks.

## Login server-mail callback lifetime

The matching coredump in [AUCTION_CRASH.md](AUCTION_CRASH.md) identifies a delayed
`ServerMailReward::OnPlayerLogin` callback after logout, not an auction parser.
The appended `src/server/scripts/World/server_mail.cpp` hunk captures the original
full `ObjectGuid` by value when scheduling the query. On completion it fetches
the session's current player and requires a non-null player with that same GUID
before reading the template or delivering mail. Delivery uses that validated
player. The query still binds the GUID counter expected by the database.
A nonempty already-rewarded result still delivers nothing. Eligible current
characters retain the existing faction-specific money, items and conditions.
No generic object getter, mail condition, auction handling or AP catalog changed.
Template-reference lifetime during a mail-store reload remains outside this fix.

Current `patches/azerothcore-v2.patch` SHA-256:
`76342b88b9864f85525771ba51de7c2b78467343027075b83184bc76356aca6c`.
The patcher now requires and fingerprints `server_mail.cpp` too. `build_realm.py`
already snapshots this patch and patcher, records the patch digest and hashes
the patched source, so no build-tool change is needed. `support.json` keeps the
same supported core pin; `verify_support.py` records a separate host-tree/DB
audit, not the current patch digest. Historical manifests and proof hashes were
not rewritten. In particular, the parent's already-running build does not
include this fix and was not changed or interrupted.

Executed verification, with the local source path shown repository-relative:

```bash
CORE_PATCH_SOURCE=../wow-test/azerothcore PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_server_mail_lifetime.py -v
```

All five tests pass. They archive the exact pin into `/tmp`, apply and reapply
the complete patch, extract the actual patched `OnPlayerLogin` method including
its callback, compile it with C++20 and lightweight session/query/mail doubles,
and execute delayed completion after scheduling. Logout and a different full
GUID on the same session deliver nothing; the same current character receives
ordinary mail; a nonempty query result prevents duplicates. Both factions run
through each case, checking recipient and delivery arguments. A fifth test
rejects missing, modified and escaping-symlink mail sources without writes.
The existing nine `test_core_patch.py` tests also pass, including full fresh-pin
archive application, idempotency, reverse application and source fingerprints.
These are native extracted-method tests, not a linked or live realm test.
Parent must coordinate an isolated rebuild/link and runtime retest before
restoring worldserver. No old source/install or private evidence was changed.

## Source fingerprints

SHA-256 before application, reproducible with
`git -C "$CORE" show <commit>:<path> | sha256sum`. Full original and patched maps
are in `tools/apply_core_patch.py:FINGERPRINTS`.

| Path under `src/server/game/` | Original SHA-256 |
| --- | --- |
| `Entities/Creature/Trainer.cpp` | `d4278f255b334f2298a33b2af93f60542f26b608afb968fd9d1638fa04123619` |
| `Entities/Player/Player.cpp` | `45cba4ed7c92debf42c974984fe727e35e21779a21b7bbfa7bb045ad8a1bf509` |
| `Entities/Player/Player.h` | `74bbdb808f307ca346bde6933519364b6e198015e84e730ebc03db7e043266dd` |
| `Entities/Player/PlayerStorage.cpp` | `bcd368071217a82e7a6af8ac001337fac0092beff22f6e143d3ece40ad379606` |
| `Maps/MapMgr.cpp` | `2497304d1b5b1b28f2f96cf43f935e45a1aa5fc9fe1a46760a998044b99dbbdd` |
| `Scripting/ScriptDefines/PlayerScript.cpp` | `a36602c5ff6bd69d6af194ec8a0b6710bfb8669318ef315502b930bb3d2592e6` |
| `Scripting/ScriptDefines/PlayerScript.h` | `026e272425ebc234fc74c9ecd4d1ca4982ddd8183f8e11c3ad9181225f5c88f5` |
| `Scripting/ScriptMgr.h` | `da94439b0d98c6198dcab26f48680b67be5fbb7ddd02c51052c1e65c8d7a42cd` |

Additional originals under `src/server/database/Database/`:

| File | Original SHA-256 |
| --- | --- |
| `MySQLConnection.cpp` | `02f083daa76d1901030d775497981391e49af9d852333b67d50803d4422c0aa5` |
| `MySQLConnection.h` | `3c7de6ab1114301d63655212e84dc5b49d5302294a5617a59f990c8721e19870` |
| `Transaction.cpp` | `cbd8582eb53b230b54c8c8fc5f6dd7dd19124208f2de5e291874e8a81ec25896` |
| `DatabaseWorkerPool.cpp` | `f31ac093e94ff8813689f79212a67f3d3a5570ec7c30833b8406690e54d5cdc1` |

Additional original under `src/server/scripts/World/`:

| File | Original SHA-256 |
| --- | --- |
| `server_mail.cpp` | `6c1e4f4c3a31af713383124944d9a8259094cc9b65bf37152e08b7564fd02810` |

Its patched SHA-256 is
`508dbbdb9b6421805e6f34cda06e7981cfec8c7ab4bd8af9d0a3458e59d9952d`.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_core_patch.py -v
```

Nine tests pass, including the original eight. They create a fresh local git archive in a temporary directory,
apply/reapply/reverse the actual patch, and reject modified original/patched
sources and wrong checkout HEAD without changing sources. Set `CORE_PATCH_SOURCE`
to use another local clone containing the commit.

Executable C++ checks extract actual patched functions, rather than asserting
patch text. Small test doubles exercise XP cap crossing, huge/RaF/rested/favored
awards, no-progress veto, trial maximum, cap remainder, item-only exemption,
ordinary template rejection, other item requirements, trainer veto/prerequisites,
resolved login fallback/cleanup, hook defaults, boolean dispatch and explicit
hook registration. These are isolated function tests, not a linked game server.

The transaction test also executes the patched production raw/prepared Execute,
ExecuteTransaction, void transaction methods, GetLastError, reconnect handler,
keepalive, SQL escaping, both async task Execute methods and the direct-commit
method. Fake C API/database
state injects START failure, raw failure after one successful write, prepared bind
and execution failure, lost COMMIT acknowledgement both before and after commit,
and rollback failure with a distinct error. It checks exact SQL call order,
no committed tail, original-error preservation, future false, next-operation
reconnection, outside-transaction raw/prepared retries, and deadlock recovery.
Each retry caller also receives deadlock followed by lost COMMIT acknowledgement;
none retries that unknown outcome. No patch-string assertions are used.

Before the server-mail extension, the eight affected translation units were MySQLConnection.cpp, Transaction.cpp,
DatabaseWorkerPool.cpp, PlayerScript.cpp, Player.cpp, PlayerStorage.cpp, Trainer.cpp
and MapMgr.cpp. All passed actual object compilation with `-O0 -g0 -Werror` using
`wowpilago-module-check:latest`, with the patched archive mounted read-only
at `/core` and the image's existing `/build/compile_commands.json`. The image's
preexisting source revision is not substituted for the pinned mounted sources.
No full configure, link, server startup or client test was performed.

To reproduce object compilation with that image after applying to `$SCRATCH`:

```bash
docker run --rm -i -v "$SCRATCH:/core:ro" wowpilago-module-check:latest python3 - <<'PY'
import json, shlex, subprocess
entries = json.load(open('/build/compile_commands.json'))
for name in ['MySQLConnection.cpp', 'Transaction.cpp', 'DatabaseWorkerPool.cpp',
             'PlayerScript.cpp', 'Player.cpp', 'PlayerStorage.cpp', 'Trainer.cpp', 'MapMgr.cpp']:
    entry = next(e for e in entries if e['file'].endswith('/' + name))
    args = shlex.split(entry['command'])
    index = args.index('-o')
    del args[index:index + 2]
    args.remove('-c')
    args += ['-O0', '-g0', '-Werror', '-c', '-o', '/tmp/' + name + '.o']
    subprocess.run(args, cwd=entry['directory'], check=True)
    print('PASS', name, flush=True)
PY
```

`git diff --check` passes for the complete generated patch. The earlier hook-only
patch's core C++ linter comparison found no new findings against the pinned
baseline, which already has tabs in DBCStructure.h and old qualifier/whitespace
issues. That linter comparison was not repeated for the transaction extension.
The SQL linter cannot run in the archive because it requires fetching
origin/master; no SQL changed. No unrelated sources were edited to hide findings.

Native-engine SQL disconnect/rollback/replay, trainer charging, boat/taxi travel,
client equipment behavior and the complete TODO release gates remain unverified.
The transaction checks above use fake C API/database state, not a running MySQL
server or linked worldserver. Host tracked-core diff was compared before/after
this extension and remained byte-identical; no host core or module file was edited.
