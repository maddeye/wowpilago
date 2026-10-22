# Private graphical client

## Restart at the login screen

Run from the repository root with your matching client installation:

```sh
export WOWPILAGO_CLIENT=/path/to/wow-3.3.5a
python tests/gui_client.py provision --stock-data
# Optional, copied only into the private Interface/AddOns directory:
python tests/gui_client.py provision --stock-data --addon addon/WoWPilago
python tests/gui_client.py launch --display 94 --software --stock-data
```

The last command is a foreground parent. A runtime controller can spawn it with
stdin set to DEVNULL and retain its PID. It does not need an interactive terminal.
The parent owns Xvfb and a Bubblewrap PID namespace containing Wine. SIGTERM or
Ctrl-C stops both; the game's Quit button also exits the parent normally. Do not
use a global `wineserver -k`, which could stop somebody else's client.

Each session writes an exclusive `cleanup.json` in its evidence directory. It records attempted signals, forced termination, cleanup errors and completion time. A SIGKILL fallback now makes the launcher exit with an error after it attempts cleanup of every owned child. A cleanup error also fails the launcher. Successful cleanup does not erase an earlier Wine error. `complete=true` describes cleanup only, not native verification success. Native acceptance must also require `forced=false`, a successful launcher exit and its separate character-save and account-offline audits. Historical sessions without this record do not acquire stronger cleanup proof from this change.

Session-scoped background terminals do not survive the agent session. Restart the
parent when needed rather than assuming this verification left a live client.

Display 0 and reserved display 93 are refused. Occupied display sockets/locks are
refused, not removed. A lock prevents two parents using this private Wine prefix.
All runtime logs go into a new `.local/v2-client/evidence/run-*` directory, printed
by the parent. Parent startup is not proof of a working client. Check its window
and screenshot; failures exit nonzero and retain the Wine/Xvfb logs.

Requirements: Python 3.11+, Wine, wineboot, wineserver, Bubblewrap, Xvfb. The input
and capture commands below also require xdotool and ImageMagick `import`.
Bubblewrap user namespaces must work. There is deliberately no unsafe fallback
that launches Wine against writable original files.

## Isolation and file policy

The source is selected by `WOWPILAGO_CLIENT`, defaulting to `.local/client-source`
inside the repository. Keep the same value for provision and launch. The launcher
forwards the resolved source path into the cleared Bubblewrap environment so the
Wine child validates the same read-only installation. Source and private EXE hashes
must both be:

```text
bd87720d0fb7299f19b41c5e7f5bf65f3f628066b3765ce382e81c5871b0a2a3
```

The CLI only provisions `.local/v2-client`. It refuses an existing directory
without its ownership marker, symlinked private destinations, overlapping source
and destination, different existing copied files, or redirected MPQ links. It
never replaces a different fixture to make a test pass. Existing regular private
WTF/configuration and saves survive reprovisioning; identical copied content and
MPQ symlinks are reused. A changed addon copy is likewise refused, not updated in
place. Inspect conflicts manually; do not point the helper at another client.

The private layout is:

```text
.local/v2-client/
  game/Wow.exe                 # regular, byte-identical copy
  game/Data/**/*.MPQ           # symlinks to original archives
  game/Data/enUS/realmlist.wtf  # private realmlist and patchlist, 127.0.0.1
  game/WTF/Config.wtf          # initially 1024x768, windowed, OpenGL, audio off
  game/Interface/AddOns/       # initially empty, optional WoWPilago copy only
  prefix/                     # new Wine prefix, retained across restarts
  home/                       # private HOME/cache
  evidence/                   # logs, captures, checks
```

Data files other than MPQs are content-copied. Original WTF, Cache, Interface,
realmlists, addons and saves are not imported. Only the game's Battle.net,
DivxDecoder, ijl15, msvcr80 and unicows DLLs are copied when present. The source's
`dinput8.dll`, `skia.dll` and DXVK DLL are not copied. No executable patches,
process-memory writes, injected addon loaders or code patches are used.

MPQ symlinks alone do not prevent writes. Bubblewrap makes the entire host tree
read-only and only rebinds this private root writable. Wine gets private `/tmp`,
HOME and WINEPREFIX. Its registry and processes are separate from the user's
Wine prefix. A runtime write-open check returned `EROFS` for both the original
WTF config and a linked MPQ. Networking remains shared for a later localhost
realm test. Xvfb uses `-nolisten tcp`; no X TCP listener was observed. Its local
UNIX display uses `-ac`, so this is display/process isolation, not protection
against other local users. Do not enter real credentials.

## Post-authentication crash and working data profile

The unchanged EXE with all supplied MPQs reproduced Error 132, access violation
at `0040CC50`, immediately after APV2A authenticated. The source installation is
not a stock data set, despite its stock build-12340 executable. The private
client now supports `--stock-data` on both provision and launch. Use it on every
invocation. Omitting it restores the supplied lettered patches and can restore
the crash.

This option excludes only these nine nonstock lettered patch archives:

```text
Data/patch-A.mpq
Data/patch-B.mpq
Data/patch-C.mpq
Data/patch-D.mpq
Data/patch-E.mpq
Data/patch-G.mpq
Data/patch-I.mpq
Data/patch-P.mpq
Data/enUS/patch-enUS-M.MPQ
```

Stock 12340 patch names are unnumbered, `-2`, or `-3`, including their locale
variants. The option recognizes case-insensitive single-letter patch suffixes,
with an optional four-letter locale. It retains numbered patches, base archives,
`backup-enUS.MPQ`, and unknown archive names. This is a stock-data *layout*, not
a hash certification of every remaining archive.

Existing owned links move from `game/Data/...` to `excluded-mpqs/Data/...`, outside
the game's archive search path. Nothing is deleted or overwritten. Provisioning
without the option moves them back. Both directions reject conflicting files,
redirected links, and duplicate active/parked paths before moving anything.
Provisioning and launch share the prefix lock, so a live client's data profile
cannot change. Settings, caches, saves, DLLs, EXE, and original archives are not
replaced by the option. Session JSON records the active MPQ list.

The failure stack goes from `0040CC50`, a memory-copy instruction, through
`0069DD34`, `0069E078`, and `0069E132`. Offline `objdump` inspection places the
caller in the OpenGL texture path, with 4-by-4 block calculations and
`glPixelStorei`, `glTexImage2D`, and `glTexSubImage2D` imports. The recorded stack
also contains `interface/glues/models/ui_orc/ogrimmarbanners01.blp`,
`DBG:CharacterSelect`, and a BLP2 header. These are texture-loading evidence,
not proof that this particular BLP or one specific MPQ is defective.

The current server's `ServerPktHeader.h`, `AuthHandler.cpp`, and
`CharacterHandler.cpp` were inspected. The header writes big-endian payload
length plus two opcode bytes, little-endian opcode, and the normal large-packet
extension. Empty character enumeration sends a single zero count byte. No
protocol fault was identified. The same running auth/world binaries on
3724/8085 accepted the working profile without a restart or server change.
No decrypted packet capture was collected.

With only the nine lettered archives excluded, actual GUI login reached empty
character selection, a rendered Human Warrior creation preview, and selection
of newly created `Apjourney`. Read-only DB queries confirmed account 2, APV2A,
character GUID 4, race/class 1/1, level 1, online 0, total playtime 0, kills 0.
The client never entered the world. TEST and its Test/Apbags/Approbe characters
were not used or altered. No bridge binding, game checks, or GM gameplay ran.

Evidence under `.local/v2-client/evidence/` includes `baseline-after-auth.png`,
`minidump-texture.json`, `crash-*-disassembly.txt`, `crash-instruction.txt`,
`exe-pe-headers.txt`, `stock-after-auth.png`, `stock-human-warrior-preview.png`,
`stock-apjourney-selection.png`, and `apjourney-created.txt`. Crashes and dumps
remain under `game/Errors/`, including the baseline reproduction at
`2026-10-19 18.33.04`. REA native engines were unavailable, recorded in
`rea-doctor.json`; the disassembly and dump inspection used ordinary local
tools, not REA decompilation. No analysis engines or MCP configuration were
installed or changed.

The failed premises were that a matching stock EXE and working login UI certify
the supplied Data set, and that successful SRP proves graphical login works.
The demonstrated fix removes the custom patch set rather than introducing DLL
injection or executable patches. Which single archive or asset triggers the
fault, and whether a custom DLL would repair it, remain untested.

A reversal control restored all nine links and reproduced `0040CC50` at
`2026-10-19 18.37.55`, even with Apjourney now present. Restoring `--stock-data`
then reached Apjourney selection again. Runs `run-98uxldd4` and `run-xvkw5n90`
record 27 versus 18 active MPQs. The successful runs `run-__o05576` and
`run-xvkw5n90` both exited 0 using Back and Quit. No private client, controller,
Xvfb, display-94 socket, or display-94 lock remains. Auth/world servers were
neither stopped nor restarted. See `final-apjourney-selection.png`,
`final-layout.json`, `characters-after.txt`, and `live-provision-refusal.txt`.

## Initial login-UI verification

The preparation reached the graphical login UI with Wine 11.17. The UI itself
shows `Version 3.3.5 (12340) (Release)` and `Jun 24 2010`. Both EXEs retain the
requested SHA-256. The supplied directory has extra lettered patch MPQs; this
verification establishes the exact EXE and observed UI build, not that every
archive is a stock Blizzard archive.

Evidence under `.local/v2-client/evidence/`:

| File | Observation |
| --- | --- |
| `run-li21loof/login-12340.png` | Final launcher restart, visible build 12340, empty fields |
| `run-___2ifwm/input-check.png` | Dummy account text accepted through X input |
| `run-___2ifwm/password-check.png` | Tab focus and masked dummy password input |
| `run-___2ifwm/geometry.txt` | Window 6291459, x=128, y=109, 1024x768 |
| `readonly-check.txt` | Write-open of source config and linked MPQ refused with EROFS |
| `source-before.json`, `source-after.json` | Source non-MPQ hashes and all file size/mode/mtime snapshots |
| `helper-tests.txt` | Offline filesystem/helper test results, not graphics certification |

All 9 initial helper tests passed. The initial parent exited 0 after the UI Quit button.
No private Wine/client/Xvfb processes, display-94 socket or X lock remained.
The source snapshot matched across all 6,470 files. Non-MPQ file content hashes
and all file sizes/modes/mtimes were unchanged; the 33 GB of MPQs were not
content-hashed. The source was mounted read-only during all Wine execution.

The first attempt used a 1024x768 Xvfb screen. Wine shrank the game to 976x732
at x=24, y=31 to fit its window margins. Changing the launcher to a 1280x960
Xvfb screen fixed the actual game window at 1024x768 without resizing tricks.

The default graphics attempt reached the login UI despite these actual messages:

```text
MESA-EGL: warning: DRI3 error: Could not get DRI3 device
MESA-EGL: warning: Ensure your X server supports DRI3 to get accelerated rendering
```

`glxinfo -B` reported Mesa llvmpipe, LLVM 22.1.8, Mesa 26.2.2, accelerated `no`.
The tested alternative `--software` sets `LIBGL_ALWAYS_SOFTWARE=1`. It also
reached the same login UI, and its Wine log was empty. Hardware-accelerated
rendering was not established. Do not treat an unsupported graphics path as a
passed runtime test; inspect logs and the actual screenshot.

## Input and capture

Use per-command DISPLAY assignments, never change the desktop's DISPLAY or run
these commands without an explicit private display. Window IDs change on restart.
There is no window manager, so `windowactivate` is not dependable. Direct
`windowfocus`, XTEST mouse clicks, typing, Ctrl+A/BackSpace and Tab were verified.
Do not rely on direct `key --window` synthetic events.

```sh
wid=$(DISPLAY=:94 xdotool search --onlyvisible --name '^World of Warcraft$' | head -n 1)
DISPLAY=:94 xdotool getwindowgeometry --shell "$wid"
DISPLAY=:94 xdotool windowfocus --sync "$wid"
# Window-relative coordinates for the verified 1024x768 client:
DISPLAY=:94 xdotool mousemove --window "$wid" 512 402 click 1
DISPLAY=:94 xdotool type --clearmodifiers --delay 80 GUI_INPUT_CHECK
DISPLAY=:94 xdotool key --clearmodifiers ctrl+a BackSpace Tab
# Password field is at 512,472. Do not enter credentials or press Return.
DISPLAY=:94 import -window "$wid" /tmp/private-wow-login.png
# Quit only, NOT Login:
DISPLAY=:94 xdotool mousemove --window "$wid" 942 718 click 1
```

Observed root-relative account/password centers are 640,511 and 640,581.
Prefer window-relative coordinates and recheck geometry before sending input.
The Login button is around 512,574 window-relative. Do not click it during
preparation. Both dummy inputs were cleared before the evidence screenshot.

## Offline checks and boundary

```sh
python -m unittest discover -s tests -p test_gui_client.py -v
```

The 11 helper tests use temporary fake clients and check checksum rejection,
source preservation, idempotence, existing private settings/saves, unsafe paths,
conflicting files/MPQs, optional addon copying, the shared parent/provision lock,
and refusal of an unsandboxed internal Wine entry. Profile tests cover numbered
and locale patches, lettered patches, retained unknown archives, reversible
inode-preserving moves, duplicate conflicts, and symlink redirection. They do
not mock a graphics success.

The initial preparation did not submit a login. The later authorized crash
investigation did authenticate APV2A and create Apjourney through the GUI, but
never entered the world. Addon loading/gameplay remains unverified. The source
snapshot still matches across all 6,470 files, including non-MPQ content hashes
and every file's size/mode/mtime. See `source-login-fix-verification.json` and
`source-after-login-fix.json`. MPQ contents were not fully hashed. The original
installation, user Wine prefix, and desktop display were not write targets.
