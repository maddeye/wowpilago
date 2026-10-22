# Native safety review

Rechecked the on-disk progression source and header against the two prior findings. This pass changes only `tests/test_native_progression.py`, `docs/PROGRESSION_RUNTIME.md`, and this review. It performs no realm operations, database connections, production-source edits, or host-core modifications.

## Findings fixed in source and bounded behavior tests

### 1. Failed deferred full saves now stop before confirmation

`APProgression.cpp::Commit` reads the boolean from `completion.m_future.get()` and calls `Stop` on false. This shared helper covers deferred full saves, check inserts, and boss-credit inserts.

The original hazard remains relevant to the failure policy. Core save construction can clear item dirty states before the transaction finishes. Matching persisted level and bank cannot prove that changed inventory committed. The fix stops rather than continuing with cleaned but unsaved inventory.

Executed evidence: `test_commit_false_stops_before_confirmation_even_when_progress_matches` runs the production `Commit`, save hook, and world-flush bodies. The fixture starts with matching persisted/live level and bank but changed inventory, and models dirty-state clearing during full-save construction. False commit raises fail-stop before the confirmation query and leaves pending set. True commit persists the modeled inventory, performs confirmation, and clears pending. Removing the result check would let the false case continue, which the test rejects.

Status: the reported unchecked-result defect is fixed. Actual core inventory behavior and database failure/reconnect handling still require integration evidence; the fixture does not prove those boundaries.

### 2. Victory now joins the character full-save transaction

`Reconcile` only sets cached victory and `savePending` on first observing actual level 80. It no longer commits a standalone victory update. `OnPlayerSaveToDB` appends bank, actual level, and victory derived from actual level to the transaction supplied by the character save. Cached victory is not the save hook's authority.

Executed evidence: `test_victory_reconcile_and_atomic_full_save_coordination` runs production reconciliation, save-hook, commit, and world-flush bodies. At level 79, reconciliation sets neither victory nor pending. At 80, it sets both without beginning or committing a transaction. No deferred save occurs at 4,999 ms; the next 1 ms triggers the full save. Modeled failure retains durable level 79 and victory false; success persists level 80 and victory true together. Direct full saves also use actual level when cached victory disagrees. Missing or contradictory level, last_level, bank, or XP confirmation stops without clearing pending.

Status: the separate-victory-transaction defect is fixed. Atomic rollback is exercised in the transaction fixture, not against MySQL. The production post-commit query confirms character level, progress last_level, bank, and character XP, but does not separately read victory. Its persistence relies on the successful full transaction containing the progress update. Do not describe that query as a victory readback.

## Current ownership and persistence contract

- Progression state lives in each Player's `CustomData` cache. Gameplay hooks use the owning map worker; effect application and deferred saves use the joined world phase. The earlier core inspection found `MapMgr::Update` joins map workers before the world-script update. There is no shared mutable progression-state map and no general cross-thread locking API. This pass did not rerun a scheduler or race test.
- The world flush scans online bindings every 5,000 ms of update diffs. Pending bank/level/victory work causes a full character save, a checked single-worker commit, and level/bank/XP confirmation before clearing pending. Autosave and delivery saves append progress too, but do not clear pending. Database waits block the caller; this is not an asynchronous durability promise with a five-second upper bound.
- Binding loads compare the manifest's parsed `catalog_version` string with compiled `CatalogVersion`. Startup validates bindings without populating a global state cache. Player-owned caches load on demand. SQL lookup failures, catalog mismatch, and invalid bound profiles use fail-stop rather than vanilla fallback.
- `Human` checks the session bot flag and, under `MOD_PLAYERBOTS`, includes `PlayerbotMgr.h` and checks `sPlayerbotsMgr.GetPlayerbotAI`. Bound-profile validation rejects detected bots. Ordinary-session selfbot detection depends on that build path; this pass does not establish playerbots build/runtime compatibility.

## Earlier paths inspected without another confirmed defect

These are retained source-review observations, not new executed integration evidence. The prior review traced delivery's pre-receipt full-save verification, atomic reward/purchase procedures, idempotent receipt replay, instance-specific equipment authorization, and delegation to core equip/use operations. It also inspected add-spell/trainer/cast gates, travel roots, and world-thread delivery callers. This pass does not revalidate those subsystems or expand their release claims.

## Verification and open gates

Executed sequentially with temporary-file C++ fixtures and no SQL connections:

```
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_native_progression.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_native_*.py' -v
```

The progression suite passes three tests, including the unchanged production-header policy test and the two extracted production-method regressions. The full native suite passes seven tests. The new fixtures stub core/framework boundaries, unrelated reconciliation callbacks, and atomic database outcomes. Production method bodies are extracted at test time, not reimplemented. SQL text checks supplement executed behavior; they are not its replacement. Temporary-copy mutation checks also rejected all three regressions: ignoring the commit boolean, deriving saved victory from stale cache, and reintroducing an independent victory commit. No production file was mutated.

Open release gates:

1. Real SQL rollback/fault/reconnect probes must prove character level/XP, bank, victory, inventory, and receipts remain consistent. No shared-schema SQL tests were run.
2. Compile and link the current module against the pinned patched core, including `MOD_PLAYERBOTS`; exercise startup, hook timing, map-worker/world-phase ownership, and ordinary-session selfbots on a realm.
3. Run client equipment/use, travel and transport recovery, riding/forms/quest mounts/vehicles, party credit, and instance reset/restart cases across supported profiles.
4. Complete a playthrough/multiworld and bridge acknowledgement/reconnect checks before calling the subsystem release-ready.

Verdict: both reported progression defects are fixed in the inspected source and covered by executed bounded production-method regressions. Live release gates remain open.
