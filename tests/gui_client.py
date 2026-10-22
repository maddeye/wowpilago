"""Private, unpatched 3.3.5a login UI. No login automation or realm writes."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / ".local/v2-client"
SOURCE = Path(os.environ.get("WOWPILAGO_CLIENT", REPO / ".local/client-source")).resolve()
SHA256 = "bd87720d0fb7299f19b41c5e7f5bf65f3f628066b3765ce382e81c5871b0a2a3"
MARKER = "wowpilago private graphical client v1\n"
CONFIG = '''SET locale "enUS"
SET gxResolution "1024x768"
SET gxWindow "1"
SET gxMaximize "0"
SET gxApi "OpenGL"
SET Sound_EnableAllSound "0"
SET movie "0"
SET readTOS "1"
SET readEULA "1"
SET readTerminationWithoutNotice "1"
SET showToolsUI "1"
'''
REALMLIST = 'set realmlist 127.0.0.1\nset patchlist 127.0.0.1\n'


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def local_path(root, relative):
    path = root / relative
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise ValueError(f"Refusing symlink in private path: {part}")
        if part == root:
            break
    return path


def validate_private_root(root, source, expected):
    root, source = Path(root).absolute(), Path(source).resolve()
    if root.resolve() != root or root == source or source in root.parents or root in source.parents:
        raise ValueError("Private root must be separate and contain no symlink ancestors")
    if digest(source / "Wow.exe") != expected:
        raise ValueError("Source Wow.exe checksum mismatch")
    if root.exists():
        marker = local_path(root, ".owner")
        if not marker.is_file() or marker.read_text() != MARKER:
            raise ValueError(f"Refusing unowned directory: {root}")
    return root, source


@contextmanager
def private_layout(root=ROOT, source=SOURCE, expected=SHA256):
    root, source = validate_private_root(root, source, expected)
    if not root.exists():
        root.mkdir(parents=True)
        (root / ".owner").write_text(MARKER)

    with local_path(root, ".launch.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another parent already owns this private Wine prefix") from None
        yield root, source


def provision(root=ROOT, source=SOURCE, expected=SHA256, addon=None, stock_data=False):
    with private_layout(root, source, expected) as (root, source):
        return populate(root, source, addon, stock_data)


def populate(root, source, addon, stock_data):
    game = Path("game")
    copies = {game / "Wow.exe": source / "Wow.exe"}
    # Do not import dinput8, DXVK, skia, addons, settings, saves or caches.
    for name in ("Battle.net.dll", "DivxDecoder.dll", "ijl15.dll", "msvcr80.dll", "unicows.dll"):
        if (source / name).is_file():
            copies[game / name] = source / name
    links = {}
    moves = []
    for src in sorted((source / "Data").rglob("*")):
        rel = src.relative_to(source)
        if any(p.lower() in {"wtf", "cache", "interface"} for p in rel.parts):
            continue
        if src.is_symlink():
            raise ValueError(f"Unexpected source Data symlink: {src}")
        if not src.is_file() or src.name.lower() == "realmlist.wtf":
            continue
        if src.suffix.lower() != ".mpq":
            copies[game / rel] = src
            continue
        # Stock 12340 patches are unnumbered, -2 or -3, never lettered.
        custom = re.fullmatch(r"patch(?:-[a-z]{4})?-[a-z]\.mpq", src.name, re.IGNORECASE)
        active, parked = game / rel, Path("excluded-mpqs") / rel
        dst, other = (parked, active) if stock_data and custom else (active, parked)
        links[dst] = src
        if custom:
            old = local_path(root, other.parent) / other.name
            if os.path.lexists(old):
                if not old.is_symlink() or old.readlink() != src:
                    raise ValueError(f"Refusing different existing MPQ: {old}")
                if os.path.lexists(local_path(root, dst.parent) / dst.name):
                    raise ValueError(f"MPQ exists in both profile locations: {src.name}")
                moves.append((other, dst))
    defaults = {game / "WTF/Config.wtf": CONFIG, game / "Data/enUS/realmlist.wtf": REALMLIST}
    if addon:
        addon = Path(addon).resolve()
        if not addon.is_dir() or addon.name != "WoWPilago":
            raise ValueError("--addon must be the WoWPilago addon directory")
        for src in addon.rglob("*"):
            if src.is_symlink():
                raise ValueError(f"Unexpected addon symlink: {src}")
            if src.is_file():
                copies[game / "Interface/AddOns/WoWPilago" / src.relative_to(addon)] = src

    # Validate the entire plan before copying; never replace a private fixture.
    for rel, src in copies.items():
        dst = local_path(root, rel)
        if dst.exists() and (not dst.is_file() or digest(dst) != digest(src)):
            raise ValueError(f"Refusing different existing file: {dst}")
    for rel, src in links.items():
        dst = local_path(root, rel.parent) / rel.name
        if os.path.lexists(dst) and (not dst.is_symlink() or dst.readlink() != src):
            raise ValueError(f"Refusing different existing MPQ: {dst}")
    for rel in defaults:
        dst = local_path(root, rel)
        if dst.exists() and not dst.is_file():
            raise ValueError(f"Not a regular private fixture: {dst}")
    for name in ("prefix", "home", "evidence", "game/Interface/AddOns"):
        local_path(root, name).mkdir(parents=True, exist_ok=True)
    for old, new in moves:
        (root / new).parent.mkdir(parents=True, exist_ok=True)
        (root / old).rename(root / new)
    for rel, src in copies.items():
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            with dst.open("xb") as out, src.open("rb") as inp:
                shutil.copyfileobj(inp, out)
    for rel, src in links.items():
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not os.path.lexists(dst):
            dst.symlink_to(src)
    for rel, content in defaults.items():
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            with dst.open("x") as stream:
                stream.write(content)
    return root


def sandbox_command(root, display, software=False):
    env = {"HOME": str(root / "home"), "WINEPREFIX": str(root / "prefix"),
           "DISPLAY": f":{display}", "WINEDEBUG": "-all", "WINEDLLOVERRIDES": "mscoree,mshtml=",
           "XDG_CACHE_HOME": str(root / "home/.cache"), "WOWPILAGO_CLIENT": str(SOURCE)}
    if software:
        env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    command = ["bwrap", "--die-with-parent", "--unshare-pid", "--ro-bind", "/", "/",
               "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
               "--ro-bind", "/tmp/.X11-unix", "/tmp/.X11-unix",
               "--bind", str(root), str(root), "--chdir", str(root / "game"), "--clearenv"]
    for key, value in {"PATH": os.environ["PATH"], **env}.items():
        command += ["--setenv", key, value]
    return command + [sys.executable, str(Path(__file__).resolve()), "_wine", "--root", str(root)]


def wine_session(root=ROOT):
    root = Path(root).absolute()
    display = os.environ.get("DISPLAY", "")
    if (os.environ.get("WINEPREFIX") != str(root / "prefix")
            or os.environ.get("HOME") != str(root / "home")
            or not re.fullmatch(r":[1-9][0-9]*", display) or display == ":93"
            or not root.is_dir()
            or not os.statvfs(SOURCE).f_flag & os.ST_RDONLY):
        raise ValueError("Internal Wine entry requires the private read-only sandbox")
    root, _ = validate_private_root(root, SOURCE, SHA256)
    for name in ("home", "prefix"):
        if not local_path(root, name).is_dir():
            raise ValueError(f"Missing private directory: {name}")
    if digest(local_path(root, "game/Wow.exe")) != SHA256:
        raise ValueError("Private Wow.exe checksum mismatch")
    subprocess.run(["wineboot", "-u"], check=True)
    try:
        return subprocess.call(["wine", "Wow.exe", "-opengl", "-nosound"])
    finally:
        subprocess.run(["wineserver", "-k"], check=False)


def launch(display=94, software=False, stock_data=False, root=ROOT):
    if display < 1 or display == 93:
        raise ValueError("Display 0 and reserved display 93 are forbidden")
    if Path(f"/tmp/.X{display}-lock").exists() or Path(f"/tmp/.X11-unix/X{display}").exists():
        raise ValueError(f"Display :{display} is occupied; choose another")
    with private_layout(root) as (root, source):
        populate(root, source, None, stock_data)
        run_client(root, display, software)


def run_client(root, display, software):
    if (root / "game/Data/enUS/realmlist.wtf").read_text() != REALMLIST:
        raise ValueError("Preserved private realmlist differs; inspect it before launch")
    evidence = Path(tempfile.mkdtemp(prefix="run-", dir=local_path(root, "evidence")))
    children = []
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with (evidence / "xvfb.log").open("x") as xlog, (evidence / "wine.log").open("x") as wlog:
        try:
            x = subprocess.Popen(["Xvfb", f":{display}", "-screen", "0", "1280x960x24",
                                  "-nolisten", "tcp", "-ac", "-noreset"], stdout=xlog, stderr=xlog,
                                 start_new_session=True)
            children.append(x)
            for _ in range(100):
                if x.poll() is not None:
                    raise RuntimeError(f"Xvfb failed; see {evidence / 'xvfb.log'}")
                if Path(f"/tmp/.X11-unix/X{display}").exists():
                    break
                time.sleep(.1)
            else:
                raise RuntimeError("Xvfb socket timeout")
            child = subprocess.Popen(sandbox_command(root, display, software), stdout=wlog,
                                     stderr=wlog, start_new_session=True)
            children.append(child)
            (evidence / "session.json").write_text(json.dumps({
                "parent_pid": os.getpid(), "display": f":{display}", "software": software,
                "exe_sha256": digest(root / "game/Wow.exe"), "started": time.time(),
                "active_mpqs": sorted(str(p.relative_to(root / "game"))
                                      for p in (root / "game/Data").rglob("*")
                                      if p.suffix.lower() == ".mpq")}, indent=2) + "\n")
            print(f"Private client parent {os.getpid()}, DISPLAY=:{display}; logs: {evidence}", flush=True)
            code = child.wait()
            if code:
                raise RuntimeError(f"Wine/sandbox exited {code}; see {evidence / 'wine.log'}")
        except KeyboardInterrupt:
            pass
        finally:
            cleanup = dict(forced=False, complete=True, signals=[], errors=[])
            for child in reversed(children):
                try:
                    if child.poll() is None:
                        cleanup['signals'].append(dict(pid=child.pid, signal=int(signal.SIGTERM)))
                        os.killpg(child.pid, signal.SIGTERM)
                        try:
                            child.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            cleanup['forced'] = True
                            cleanup['signals'].append(dict(pid=child.pid, signal=int(signal.SIGKILL)))
                            os.killpg(child.pid, signal.SIGKILL)
                            child.wait()
                except Exception as error:
                    cleanup['complete'] = False
                    cleanup['errors'].append(dict(pid=child.pid, error=type(error).__name__))
            cleanup['finished'] = time.time()
            with (evidence / 'cleanup.json').open('x') as stream:
                json.dump(cleanup, stream, indent=2)
                stream.write('\n')
            if not cleanup['complete']:
                raise RuntimeError(f"Private client cleanup failed; see {evidence / 'cleanup.json'}")
            if cleanup['forced']:
                raise RuntimeError(f"Private client required forced termination; see {evidence / 'cleanup.json'}")
            print("Private client and Xvfb stopped", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["provision", "launch", "_wine"])
    parser.add_argument("--root", type=Path, default=ROOT, help="Owned private client directory")
    parser.add_argument("--display", type=int, default=94)
    parser.add_argument("--software", action="store_true", help="Mesa software OpenGL fallback")
    parser.add_argument("--stock-data", action="store_true",
                        help="Park lettered patch MPQ links outside private Data")
    parser.add_argument("--addon", type=Path, help="Copy optional addon/WoWPilago into private AddOns")
    args = parser.parse_args()
    if args.command == "_wine":
        return wine_session(args.root)
    if args.command == "provision":
        print(provision(root=args.root, addon=args.addon, stock_data=args.stock_data))
    else:
        if args.addon:
            parser.error("Use provision --addon before launch")
        launch(args.display, args.software, args.stock_data, root=args.root)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))
