#!/usr/bin/env python3
"""Build the pinned protocol-2 realm without touching host core or runtime files."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
CORE_COMMIT = "9fb906bb7296212ff42fc95ff73a92aaf8554f0d"
BOTS_COMMIT = "2f7d9f774987d0157c6a0d0cc08c40bec3db3945"
IMAGE = "wowpilago-v2-toolchain-check:latest"
ROOT = PROJECT / ".local/v2-build"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprints(root):
    return {str(p.relative_to(root)): sha256(p)
            for p in sorted(root.rglob("*")) if p.is_file()}


def tree_digest(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def run(args, log):
    print("+ " + shlex.join(map(str, args)), flush=True)
    with log.open("w") as output:
        process = subprocess.Popen(list(map(str, args)), stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            output.write(line)
            output.flush()
            print(line, end="", flush=True)
        process.stdout.close()
        code = process.wait()
    if code:
        raise subprocess.CalledProcessError(code, args)


def archive(repo, commit, target, tar):
    target.mkdir(parents=True, exist_ok=True)
    with tar.open("wb") as output:
        subprocess.run(["git", "-C", str(repo), "archive", commit], stdout=output, check=True)
    subprocess.run(["tar", "-xf", str(tar), "-C", str(target)], check=True)
    return sha256(tar)


BOTS_FACTORY = "src/Bot/Factory/PlayerbotFactory.cpp"
BOTS_FACTORY_ORIGINAL = "d67e8e95c120cb8ea788d335fd64a4df03f36114cb14938bbbdecea34ad4bc87"
BOTS_FACTORY_PATCHED = "8457f86e0e5b7134000de8e703193956faff39c5295e73e2f6ca25bff6df9bf5"
BOTS_PATCH_SHA256 = "cc41814799c3aba0c994c66d9bcfa58fc9bcc86ba9144c3a9aa728bda796fd0a"


def apply_playerbots_patch(module, patch):
    """Only patch a Git-free pinned archive, never a host checkout."""
    module = Path(module).resolve(strict=True)
    if any(module.rglob(".git")):
        raise ValueError("playerbots patch requires a Git-free archive")
    factory = module / BOTS_FACTORY
    if not factory.resolve().is_relative_to(module):
        raise ValueError("unsafe playerbots source path")
    if sha256(patch) != BOTS_PATCH_SHA256:
        raise ValueError("unexpected playerbots safety patch digest")
    before = sha256(factory)
    if before not in (BOTS_FACTORY_ORIGINAL, BOTS_FACTORY_PATCHED):
        raise ValueError("wrong or modified pinned playerbots source")
    state = "already applied"
    if before == BOTS_FACTORY_ORIGINAL:
        env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(module.parent))
        command = ["git", "apply", str(patch.resolve())]
        subprocess.run(command[:2] + ["--check"] + command[2:], cwd=module, env=env, check=True)
        subprocess.run(command, cwd=module, env=env, check=True)
        state = "applied"
    if sha256(factory) != BOTS_FACTORY_PATCHED:
        raise ValueError("playerbots patched fingerprint mismatch")
    return {"commit": BOTS_COMMIT, "patch_sha256": sha256(patch), "state": state,
            "file": BOTS_FACTORY, "original_sha256": BOTS_FACTORY_ORIGINAL,
            "patched_sha256": BOTS_FACTORY_PATCHED}


def check_commands(build):
    commands = json.loads((build / "compile_commands.json").read_text())
    module = Path("/work/source/modules/mod-archipelago/src")
    expected = {str(p) for p in module.glob("*.cpp")}
    actual = {entry["file"] for entry in commands if entry["file"] in expected}
    assert expected and actual == expected, (expected, actual)
    entry = next(e for e in commands if e["file"].endswith("/APProgression.cpp"))
    args = shlex.split(entry["command"])
    assert "-DMOD_PLAYERBOTS" in args, "native playerbots macro missing"
    includes = [Path(a[2:]) for a in args if a.startswith("-I")]
    assert any((p / "PlayerbotMgr.h").is_file() for p in includes), "playerbots include missing"
    index = args.index("-o")
    del args[index:index + 2]
    args.remove("-c")
    result = subprocess.run(args + ["-E", "-dM"], cwd=entry["directory"],
                            check=True, text=True, stdout=subprocess.PIPE)
    (build.parent / "adapter.macros").write_text(result.stdout)
    assert "#define WOWPILAGO_PLAYERBOTS 1" in result.stdout, "native adapter disabled"
    print("PASS all WoWPilago translation units included; native playerbots adapter enabled")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--core", type=Path, default=PROJECT.parent / "wow-test/azerothcore")
    parser.add_argument("--check-commands", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.check_commands:
        check_commands(args.check_commands)
        return
    support = json.loads((PROJECT / "support.json").read_text())
    if support["core_commit"] != CORE_COMMIT or support["protocol_version"] != 2:
        parser.error("support.json does not match the pinned protocol-2 build")
    ROOT.mkdir(parents=True, exist_ok=True)
    work = ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    work.mkdir()
    manifest = {"status": "preparing", "core_commit": CORE_COMMIT,
                "playerbots_commit": BOTS_COMMIT, "protocol_version": 2,
                "jobs": args.jobs, "started_utc": datetime.now(timezone.utc).isoformat(),
                "run_directory": str(work)}

    def save():
        (work / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    save()
    print(f"Build artifacts: {work}", flush=True)
    try:
        manifest["image_id"] = subprocess.check_output(
            ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"], text=True).strip()
        run([PROJECT / ".venv/bin/python", PROJECT / "tools/build_catalog.py"], work / "catalog.log")
        module = work / "source/modules/mod-archipelago/src"
        module.mkdir(parents=True)
        shutil.copytree(PROJECT / "src", module, dirs_exist_ok=True)
        manifest["module_files_sha256"] = fingerprints(module)
        manifest["module_tree_sha256"] = tree_digest(manifest["module_files_sha256"])
        # Reject a concurrent source edit rather than silently building a mixed snapshot.
        if fingerprints(PROJECT / "src") != manifest["module_files_sha256"]:
            raise ValueError("src changed while copying; rerun after the source update finishes")
        shutil.copytree(PROJECT / "patches", work / "inputs/patches")
        (work / "inputs/tools").mkdir()
        for name in ("apply_core_patch.py", "build_realm.py"):
            shutil.copy2(PROJECT / "tools" / name, work / "inputs/tools" / name)
        shutil.copy2(PROJECT / "support.json", work / "inputs/support.json")
        manifest["patch_sha256"] = sha256(work / "inputs/patches/azerothcore-v2.patch")
        manifest["input_files_sha256"] = fingerprints(work / "inputs")
        manifest["core_archive_sha256"] = archive(args.core.resolve(), CORE_COMMIT,
                                                   work / "source", work / "core.tar")
        manifest["playerbots_archive_sha256"] = archive(
            args.core.resolve() / "modules/mod-playerbots", BOTS_COMMIT,
            work / "source/modules/mod-playerbots", work / "playerbots.tar")
        run([sys.executable, work / "inputs/tools/apply_core_patch.py", "--core", work / "source"],
            work / "patch.log")
        manifest["playerbots_safety_patch"] = apply_playerbots_patch(
            work / "source/modules/mod-playerbots", work / "inputs/patches/playerbots-safety.patch")
        source_files = fingerprints(work / "source")
        (work / "source-files.sha256.json").write_text(json.dumps(source_files, indent=2) + "\n")
        manifest["source_tree_sha256"] = tree_digest(source_files)
        manifest["status"] = "building"
        save()
        docker = ["docker", "run", "--rm", "--network=none", "--user", f"{os.getuid()}:{os.getgid()}",
                  "-e", "HOME=/tmp", "-v", f"{work}:/work",
                  "-v", f"{work / 'source'}:/work/source:ro", manifest["image_id"]]
        # ScriptPCH supplies template definitions missing from three pinned content scripts.
        configure = ["cmake", "-S", "/work/source", "-B", "/work/build",
                     "-DCMAKE_INSTALL_PREFIX=/work/install", "-DCMAKE_BUILD_TYPE=Release",
                     "-DCMAKE_CXX_FLAGS_RELEASE=-O1 -DNDEBUG -g0", "-DCMAKE_C_FLAGS_RELEASE=-O1 -DNDEBUG -g0",
                     "-DSCRIPTS=static", "-DMODULES=static", "-DAPPS_BUILD=all", "-DTOOLS_BUILD=none",
                     "-DBUILD_TESTING=OFF", "-DUSE_COREPCH=OFF", "-DUSE_SCRIPTPCH=ON",
                     "-DWITHOUT_GIT=ON", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"]
        manifest["configure_command"] = configure
        save()
        run(docker + configure, work / "configure.log")
        run(docker + ["python3", "/work/inputs/tools/build_realm.py", "--check-commands", "/work/build"],
            work / "adapter-check.log")
        run(docker + ["cmake", "--build", "/work/build", "--target", "worldserver", "authserver",
                      "--parallel", str(args.jobs), "--", "-k"], work / "build.log")
        run(docker + ["cmake", "--install", "/work/build"], work / "install.log")
        for name in ("worldserver", "authserver"):
            binary = work / "install/bin" / name
            with binary.open("rb") as stream:
                assert stream.read(4) == b"\x7fELF", f"not an ELF binary: {binary}"
            run(docker + ["ldd", f"/work/install/bin/{name}"], work / f"{name}-ldd.log")
            assert "not found" not in (work / f"{name}-ldd.log").read_text(), "unresolved shared library"
        manifest["installed_files_sha256"] = fingerprints(work / "install")
        manifest["libraries_sha256"] = {
            str(p.relative_to(work)): sha256(p) for p in sorted((work / "build").rglob("*"))
            if p.is_file() and (p.suffix == ".a" or ".so" in p.name)}
        manifest["status"] = "success"
    except (OSError, ValueError, AssertionError, subprocess.SubprocessError) as error:
        manifest["status"] = "failed"
        manifest["error"] = str(error)
        raise
    finally:
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save()
        print(f"{manifest['status']}: {work / 'manifest.json'}", flush=True)


if __name__ == "__main__":
    main()
