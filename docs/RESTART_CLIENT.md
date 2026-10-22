# Restart client investigation

## Finding

The crash verifier declared the world healthy during startup because Docker's published TCP port accepted a connection. That does not establish that worldserver has opened its own listener or can send a world challenge.

The failed post-restart connection is consistent with EOF while waiting for the initial, unencrypted `SMSG_AUTH_CHALLENGE`, before `CMSG_AUTH_SESSION`, character enumeration, or `CMSG_PLAYER_LOGIN`. Native world initialization had not finished when the verifier exited. Docker proxy accepting a host connection while the container-side listener is unavailable explains the accepted-then-closed socket.

This stage is a strong inference, not a recovered traceback. The original wrapper saved only `str(exc)`. It did not save the failing socket endpoint, stack, packet header, or receive offset. An auth-server EOF after successful SRP cannot be excluded absolutely from that string alone. No original packet capture exists in the run artifacts.

Status: **half-pass only, not recovery PASS**. One intentional world SIGKILL completed. The durable offline queue survived exactly. Delivery, second crash window, and exactly-once recovery remain unverified.

## Scope and runtime

Investigation performed on 2026-10-19 UTC. Only new files under `.local/restart-client-investigation/` and this document were written. No shared runner, client, native source, configuration, fixture, or previous report was changed.

World container `4b7de1464f41e8106a954718adb09ca6753a10e409e9b905d488d429d4eb905c`, PID `926906`, remained running from `19:38:29.607939017Z`. Image is `sha256:55bfa1750408af5f5645166e47928aac6ecf0be92dd24005411cd96115f18ed9`. SHA256 of `/proc/926906/exe` matched the mounted candidate binary:

```text
3b9b2bf9f946a1eeef5908e440ed917132c0559c4bc483ba14be199060641809
.local/v2-build/20261019T191318.518327Z-mail-fixed/install/bin/worldserver
```

No crash retry, restart, kill, new player creation, account authentication, character login, gameplay packet, GM command, SQL write, queue application, GUI, bridge, or AP server was run. The saved AP room was not opened. Existing fixtures and history were preserved, including GUID 26/binding 16 and GUID 27/binding 17.

## Timeline

Original run `.local/crash-runtime-plan/run-20261019T193803Z-c76606ac`:

| UTC time | Evidence |
| --- | --- |
| 19:38:29.353787443 | Previous world process finished after intentional SIGKILL, from Docker state. |
| 19:38:29.607939017 | Same container started the new world process. |
| 19:38:29.894058 | `runtime-1.json` saved after `health()` accepted the host TCP connection and checked runtime identity/hash. |
| 19:38:29.926605 | `queued-after-restart.json` saved. Exact equality with `queued-offline.json`. |
| 19:38:29 | APV2B auth `last_login`, from SELECT. Native `LOGIN_UPD_LOGONPROOF` updates this after successful SRP proof. Previous fixture creation was at 19:38:07. |
| 19:38:30.096631 | `summary.json` saved with `Server closed connection`, `world_kills=1`, `protected_unchanged=true`. Only 0.489 seconds after process start. |
| 19:38:30.2719 | Docker logs still reporting database startup. |
| 19:38:48.263 | Docker logs still reporting late world initialization. |
| 19:38:48.340109 | Native `Server.log` last-write time. Its tail contains `WORLD: World Initialized In 0 Minutes 18 Seconds` and `worldserver-daemon ready...`. This is a file timestamp, not a per-message timestamp. |
| 19:41:13.793943 | Later passive world challenge probe succeeded. No bytes sent. |

Artifact timestamps are filesystem mtimes, not packet timestamps. Host local displays use UTC+02; stored timeline and database clock observations use UTC. Native console output is buffered: the Docker log stops near the playerbots banner while the native file contains the subsequent ready message. Absence of that message from Docker output alone is not evidence of a stuck world.

## Connection stage

`tests/verify_crash_runtime.py:235` accepts `socket.create_connection(('127.0.0.1', 8085))` as readiness. It reads no server packet. PID `926976` was Docker's proxy for host `127.0.0.1:8085` to container `172.19.0.4:8085`.

`CrashRunner.crash()` then calls `health()`, checks offline/exclusive state, and `execute()` records the unchanged queue before entering `login(guid=27)`.

The next client path is:

```text
Runner.login                         tests/verify_runtime.py:227
  authenticate(APV2B)                tests/realm_client.py:202
  choose unlocked realm
  create_connection(127.0.0.1:8085)
  RealmClient.connect                tests/realm_client.py:353
    wait_for(SMSG_AUTH_CHALLENGE)     tests/realm_client.py:342
      receive                        tests/realm_client.py:309
        recv_exact                   tests/realm_client.py:150
          ProtocolError("Server closed connection") on recv returning b''
    send CMSG_AUTH_SESSION           only after complete 40-byte challenge
    wait_for SMSG_AUTH_RESPONSE
    CMSG_CHAR_ENUM
    CMSG_PLAYER_LOGIN                much later
```

Native source under `.local/v2-build/20261019T191318.518327Z-mail-fixed/source/` explains the startup gap. `src/server/apps/worldserver/Main.cpp` calls `SetInitialWorldSettings()` before `StartWorldNetwork()`, then enables the realm and logs ready. Therefore a sub-second host TCP connection cannot establish world readiness when initialization takes 18 seconds.

In `src/server/game/Server/WorldSocket.cpp`, `Start()` schedules the IP check. An allowed IP proceeds through `CheckIpCallback()` to `HandleSendAuthSession()`, which sends opcode `0x01ec` with a 40-byte payload. An IP ban instead sends `SMSG_AUTH_RESPONSE` with `AUTH_REJECT` and logs `WorldSocket::CheckIpCallback: Sent Auth Response (IP ... banned)`. Later world-auth denials also log explicit reasons. No such error appears in the preserved native logs. At the failed run's timestamp the native world listener had not yet been started, so those world-auth callbacks do not explain the immediate failure.

The later passive probe received these complete 44 bytes in 3.636 ms, including TCP connect in 0.890 ms:

```text
002aec01010000002d725a06cc0722ced8a4cf41628b955965efcc6e85c329b18666d46cd7a8438e4e3b8f98
```

Header `00 2a ec 01` decodes as big-endian size 42, little-endian opcode `0x01ec`, and 40 payload bytes. Payload starts with uint32 1. This establishes later challenge readiness only. It does not prove world authentication, character login, reward delivery, or gameplay.

## Authentication and preserved state

SELECT-only observations found APV2B still marked `wowpilago-fixture@invalid`, GM0, offline, `failed_logins=0`, no IP lock, country lock `00`, OS `Win`, and `last_login=2026-10-19 19:38:29` UTC. No active IP or APV2B account ban was present. Realm 1 currently has flag 0, build 12340, and security 0. Warden is disabled.

The auth server never restarted. Its `RealmsStateUpdateDelay=20` permits a cached online realm listing during the first fraction of world startup. `RealmList.cpp` refreshes this cache periodically, not for every client realm-list request. A selectable realm therefore does not replace a world challenge readiness check. The exact historical realm-list response was not captured.

GUIDs 26 and 27 remain offline level-1 fixtures with XP 0. Both bindings remain disconnected. Binding 17 still has only indexes 0/1, bag 21841 and five vouchers, both `applied=0`, `applied_value=0`, and null item GUID/application timestamp. No account or character was online at observation. The named verifier/GUI/bridge/AP-server process scan found none running.

Both original snapshot comparisons were independently rechecked: queued-before versus queued-after are equal; protected-before versus protected-after are equal. Previous run files were not rewritten. This does not promote the failed recovery test to PASS.

## Proposed fix, not implemented

1. In the crash verifier's existing bounded health loop, require a complete valid unencrypted `SMSG_AUTH_CHALLENGE` on a disposable socket before declaring readiness. Host TCP accept alone is insufficient. Retain identity/hash checks and the existing deadline. EOF during this readiness probe means still not ready, not permission to retry a fixture login or repeat a crash.
2. Preserve a traceback or explicit socket endpoint/stage/expected opcode when login fails. Record header length and elapsed time without logging passwords, SRP proofs, or session keys. Do not wrap shared `Runner` changes into this investigation while class matrix 53 owns it.
3. Later add a small offline socket test for accepted TCP followed by EOF versus a complete challenge. No new framework, fixed sleep, gameplay readiness claim, login retry loop, or crash retry is needed.

No patch or recovery rerun was performed. Parent review of this proposal is the next action; failed fixtures must remain untouched until a separately authorized maintenance plan exists.

## Evidence directory

`.local/restart-client-investigation/` contains the original artifact timeline with hashes, native log copies, timestamped Docker logs, container state snapshots, SELECT text/results, exact snapshot comparisons, stopped-process observation, and the passive challenge result. No credential or session-key columns were selected. The original run retains its failed summary and every earlier fixture/history artifact.
