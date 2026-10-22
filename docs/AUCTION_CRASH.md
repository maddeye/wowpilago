# Worldserver crash during the auction test

## Finding

The actual core proves a null `Player*` in the asynchronous **login server-mail reward callback**, after fixture 22 logged out. The crashing stack is not an auction packet parser or an NPC event. Auction hello was the last non-logout client operation, but timing does not establish auction causation.

No world restart, source edit, rebuild, SQL operation, GUI action, or gameplay-history change was performed during this investigation. All investigation writes are under `.local/auction-crash/` and this new document. Fixture 22's stale SQL online flag remains untouched. The existing build and other services were not controlled.

## Artifact identity and times

The stopped container is `wow-test-worldserver-1`, container ID `5cac61f7765884f75aad9c7c8d35beecfb1fdcb1f807aff54c9ff06c1fa32a3b`.

- Image SHA-256 is `d29bbb51fbad4cff828b9ede4333d5ef31b2573d5d3e5c3457897ad7dd34ab48`.
- Both the binary copied from that stopped container and `.local/v2-build/20261019T150600.624050Z/install/bin/worldserver` hash to `6434b132b68a581a2046319c25795f9f5c1211ab2096b56898702a12542d83e8`. ELF build ID is `cbfe638760abc2284858b5bbb9374a5686590d9d`.
- Host PID is `147397`, container crashing LWP is `1`, UID is `1000`. Signal is `SIGSEGV`, `SEGV_MAPERR`. Docker exit is `139`, `OOMKilled=false`.
- Journal `COREDUMP_TIMESTAMP=1792435084000000` means `2026-10-19T18:38:04Z`. The journal entry timestamp is `2026-10-19T18:38:20.897163Z`, matching the list's displayed `20:38:20 CEST`. Docker `FinishedAt` is `2026-10-19T18:38:21.199054702Z`. These are separate recorded timestamps, not interchangeable crash instants.
- Extracted core size is `2712895488` bytes. SHA-256 is `daa5cfdd2615e9382783086530b6b47cb27811360f5d3b1747df96908d727455`. The original systemd compressed core remains in place.

The executable command is `/work/install/bin/worldserver -c /work/install/etc/worldserver.conf`. The archived CMake cache records `Release` with `-O1 -DNDEBUG -g0`. The binary is not stripped, so function names survive but C++ local types and exact source line mappings do not. Source references below are matched archived source, not DWARF line-number claims.

Configuration records `MaxCoreStuckTime = 0`. The coredump journal records an unlimited core limit and dumpable state `1`. Full container configuration, runtime flags, process status, process limits, and world configuration are retained privately with the evidence.

## Actual stack

`gdb-initial.txt` contains all ten thread backtraces, registers, signal information, and loaded libraries. The crashing main-world thread has this stack, shown from caller to fault:

```text
main
WorldUpdateLoop
World::Update
WorldSessionMgr::UpdateSessions
WorldSession::Update
WorldSession::ProcessQueryCallbacks
AsyncCallbackProcessor<QueryCallback>::ProcessReadyCallbacks
QueryCallback::InvokeIfReady
QueryCallback::WithPreparedCallback callback
ServerMailReward::OnPlayerLogin callback                 0x562b0684057e
ServerMailMgr::SendServerMail                            0x562b06d351e7
ServerMailCondition::CheckCondition                      0x562b06d35050
Object::GetByteValue                                     0x562b06a47140
```

The fault is at binary-relative offset `0x1c9f140`:

```text
Object::GetByteValue +42: cmp 0x68(%rdi),%si
rdi = 0
rsi = 0x17
rdx = 1
siginfo.si_addr = 0x68
```

This is the null object's member access, not a corrupt auction payload read. `ServerMailCondition::CheckCondition +239` calls `GetByteValue` with field `0x17`, byte offset `1`, for the class condition. Its continuation computes the class mask.

## Recovered callback state

`gdb-detail.txt` records the disassembly and frame registers used to recover the captures. `gdb-state-verified.txt` checks these values directly in core memory:

```text
callback capture                  0x7f85353cf5e0
captured WorldSession             0x7f850e23cb00
captured ServerMail               0x7f8555fe76d0
session cached character GUID     22
session account ID                5
session player pointer            0
session recently-logged-out flag  1
mail template ID                  39713
mail sender                       19506
mail money Alliance / Horde       0 / 0
mail subject                      A Very Special Delivery
current condition type            8, Class
current condition value           32, Death Knight class mask
current condition state           0
```

The session pointer recovered from the callback equals the session in `ProcessQueryCallbacks` and `WorldSession::Update`. This is not an assumed dangling session pointer. Its current player is null and its recent-logout flag is set.

`WorldSession::SetPlayer` disassembly establishes the player-pointer offset `0xd0` and cached GUID offset `0xc8`. `WorldSession::LogoutPlayer` disassembly establishes recent-logout offset `0x17b`. The archived member layout identifies account ID offset `0x110`. These offsets apply only to this pinned binary.

The empty prepared result entered the callback's `if (!result)` branch. The callback loads the captured session's player at offset `0xd0` and passes it directly to `SendServerMail`. The mail's class condition then dereferences that null player. The condition fails before any mail transaction in this invocation. This does not make a claim about every other earlier callback.

## Causal source path

All paths in this section are relative to `.local/v2-build/20261019T150600.624050Z/source/`. Copies and hashes are in `source-evidence/` and `source-evidence.sha256.json`.

`src/server/scripts/World/server_mail.cpp`, lines 29 through 73, schedules one asynchronous character-database query per server-mail template on login. It captures the session and a reference to the template. The initial session check happens before scheduling. Inside the later callback there is no current-player or original-character identity check before `session->GetPlayer()` is passed onward.

`src/server/game/Mails/ServerMailMgr.cpp`, lines 292 onward, checks the template conditions before beginning the mail transaction. Lines 346 onward implement the condition switch. The `Class` branch calls `player->getClassMask()` without a valid player.

`src/server/game/Server/WorldSession.cpp`, line 610, processes query callbacks. Logout removes the player and calls `SetPlayer(nullptr)` at line 880. Lines 896 through 898 finish logout and set `m_playerRecentlyLogout=true`. The session can still process a delayed login callback after that transition. The core contains exactly that state.

The root error is an asynchronous operation outliving the character-login state it assumes. Adding a null check inside the generic byte getter or making all mail conditions silently accept missing players would hide the wrong boundary.

## Auction and log boundaries

The copied interrupted transcript has SHA-256 `d6a937f904932066a7ec8289cdeb9fc3a0d2acf7ff17666de533a81fdc0a7534`. Its final player sends are hello `0x255`, payload `d201000f220030f1`, and logout request `0x4b`, empty payload. It contains no auction-sell packet `0x256`. The preceding run received the enabled auction hello before stopping on the incorrect house expectation, as documented in [TRANSFER_LIVE.md](TRANSFER_LIVE.md).

The core identifies the logged-out fixture's login-reward callback. It does not prove the exact ordering of hello handling versus logout or why this particular database result became ready then. Packet records lack per-packet timestamps. No malformed-auction-input cause is supported by the crashing stack.

The last complete Docker messages include the MoveSpline velocity warning for creature entry 32572 and the guild-cache reset. Neither appears in the causal stack. They are not root-cause evidence. `docker-world.private.log` preserves the full timestamped log, including its incomplete final output.

## Bounded fix proposal, not applied

Fix `ServerMailReward::OnPlayerLogin`'s asynchronous callback boundary. Capture the original character GUID. At callback execution, obtain the session's current player and return without delivery unless that player exists and has the captured GUID. Pass that validated player to `SendServerMail`.

A null check there prevents this exact crash. The GUID check also prevents a delayed callback from delivering the old character's login reward to a different character on the same session. Do not solve this by changing auction parsing, skipping all server mail, clearing the fixture flag in SQL, or guarding `Object::GetByteValue`.

Before deployment, test a delayed login-mail result after logout, after a different-character login on the same session, and during a normal eligible login. The first two must not deliver a reward. The last must retain ordinary delivery behavior. Coordinate the source change with the parent and its fresh build. This investigation neither changed that build nor tested a fix.

The captured template is also a reference into the manager's store. Reload lifetime is a separate review concern, not a demonstrated cause here. The template and class condition are readable and consistent in this core.

## Offline verification and evidence

From the repository root, this command rechecks the observed failure state without starting a worldserver:

```sh
gdb -nx -nh -batch -x .local/auction-crash/state.gdb
```

The final output is:

```text
CORE ASSERT PASS: fixture 22 account 5 recently logged out; captured session has null player; mail template 39713; Class mask 32
Cached character GUID low: 22
```

This is a repeatable core-state check, not an execution replay or a verified fix. No code was injected into the core, and no inferior was resumed. Full execution reproduction requires a separate authorized runtime or future test fixture.

The evidence directory is private. Core memory, configuration, logs, journal data, and Docker environment may contain credentials or player data. Do not publish them. The principal retained artifacts are:

- `worldserver.147397.core`, `core.sha256`, `coredump-info.txt`, and `coredump-journal.private.jsonl` preserve the core and original timestamps.
- `sysroot/`, `binary.sha256`, `binary-metadata.txt`, and `library.sha256` preserve the matching stopped-container executable and libraries. No debug rebuild was needed.
- `initial.gdb`, `detail.gdb`, `state.gdb`, `lifecycle.gdb`, and their output files preserve the inspection commands and results. The first state inspection's incorrect template-ID assertion is retained as `gdb-state-first-inspection.txt`; the memory dump exposed template 39713, and the corrected check passes.
- `container-inspect.private.json`, `image-inspect.private.json`, `worldserver.conf.private`, `CMakeCache.old.txt`, and `docker-world.private.log` retain runtime and build context.
- `transfer-evidence/`, `evidence-manifest.json`, `source-evidence/`, and `source-evidence.sha256.json` preserve copied transcripts, snapshots, and relevant old source without changing originals.

GDB warns that host `libthread_db` does not match the inferior. All ten core LWPs and their ordinary unwind backtraces are present. That warning does not affect the direct register, instruction, and memory evidence above. No typed local-variable recovery is claimed from this `-g0` build.

## Fix status: patched and tested offline, deployment pending

`patches/azerothcore-v2.patch` now appends the callback-boundary fix for the exact
core pin `9fb906bb7296212ff42fc95ff73a92aaf8554f0d`. It captures the original full
character `ObjectGuid`, then fetches the current player at callback execution
and requires that player to exist and match before calling `SendServerMail`.
Normal eligible delivery and the already-rewarded query check remain intact.
There are no generic null guards or mail disablement.

Current patch SHA-256 is
`76342b88b9864f85525771ba51de7c2b78467343027075b83184bc76356aca6c`.
The patcher also checks the original/patched mail-source fingerprints. See
[CORE_PATCH.md](CORE_PATCH.md#login-server-mail-callback-lifetime) for details.

Executed `test_server_mail_lifetime.py`: five tests pass. Actual patched
`OnPlayerLogin` code and its callback compile and run with lightweight native
stubs. Delayed completion after logout delivers nothing; a different character
on the same session receives nothing; the same current character receives
normal faction-specific mail; a nonempty reward query delivers no duplicate.
Missing, modified and unsafe mail sources are rejected. The nine existing core
patch tests also pass, including clean application, reapplication and reversal
in throwaway fresh-pin archives. No host checkout was patched.

This is not a deployed fix. The parent's full build already in progress lacks
this callback fix and was not interrupted or modified. Parent must arrange an
isolated rebuild/link and runtime retest before restoring the stopped world.
No service restart, authentication, SQL write, character/history change, AP
version/catalog change, or private coredump modification was performed for this
fix. Old linked source and installed binaries remain untouched. The separate
mail-template reload lifetime concern remains untested.
