"""Filesystem safety checks, not evidence that Wine or graphics work."""

from contextlib import contextmanager, nullcontext
import fcntl
import importlib.util
import json
import signal
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, call, patch

import gui_client as gc


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        self.root = self.base / "private"
        self.source.mkdir()
        for name, data in {
            "Wow.exe": b"fixture exe", "Data/common.MPQ": b"archive",
            "Data/enUS/locale-enUS.MPQ": b"locale", "Data/enUS/realmlist.wtf": b"original realm",
            "WTF/Config.wtf": b"original config", "Cache/save": b"cache",
            "Interface/AddOns/Other/a.lua": b"other addon", "dinput8.dll": b"injection",
            "Data/enUS/Interface/custom.lua": b"custom locale interface",
        }.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.expected = gc.digest(self.source / "Wow.exe")

    def provision(self, **kwargs):
        return gc.provision(self.root, self.source, self.expected, **kwargs)

    def snapshot(self):
        return {str(p.relative_to(self.source)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.source.rglob("*") if p.is_file()}

    def test_isolation_and_idempotence(self):
        before = self.snapshot()
        self.provision()
        game = self.root / "game"
        self.assertFalse((game / "Wow.exe").is_symlink())
        self.assertEqual(gc.digest(game / "Wow.exe"), self.expected)
        self.assertEqual((game / "Data/common.MPQ").readlink(), self.source / "Data/common.MPQ")
        self.assertEqual((game / "Data/enUS/realmlist.wtf").read_text(), gc.REALMLIST)
        self.assertEqual((game / "WTF/Config.wtf").read_text(), gc.CONFIG)
        self.assertFalse((game / "dinput8.dll").exists())
        self.assertFalse((game / "Cache").exists())
        self.assertFalse((game / "Data/enUS/Interface").exists())
        config = game / "WTF/Config.wtf"
        config.write_text("private settings\n")
        save = game / "WTF/save"
        save.write_text("private save")
        self.provision()
        self.assertEqual(config.read_text(), "private settings\n")
        self.assertEqual(save.read_text(), "private save")
        self.assertEqual(self.snapshot(), before)

    def test_stock_data_moves_only_lettered_patches_and_is_reversible(self):
        names = ["patch.MPQ", "patch-2.MPQ", "patch-3.MPQ", "patch-A.mpq",
                 "patch-P.MPQ", "enUS/patch-enUS-M.MPQ", "enUS/patch-enUS-3.MPQ",
                 "enUS/backup-enUS.MPQ", "unknown.MPQ"]
        custom = {"patch-A.mpq", "patch-P.MPQ", "enUS/patch-enUS-M.MPQ"}
        for name in names:
            path = self.source / "Data" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
        before = self.snapshot()
        self.provision()
        links = {name: (self.root / "game/Data" / name).lstat().st_ino for name in custom}
        for _ in range(2):
            self.provision(stock_data=True)
            for name in names:
                active = self.root / "game/Data" / name
                parked = self.root / "excluded-mpqs/Data" / name
                self.assertEqual(active.exists(), name not in custom)
                if name in custom:
                    self.assertEqual(parked.readlink(), self.source / "Data" / name)
                    self.assertEqual(parked.lstat().st_ino, links[name])
        self.provision()
        self.assertTrue(all((self.root / "game/Data" / name).exists() for name in names))
        self.assertEqual(self.snapshot(), before)

    def test_stock_data_refuses_conflicts_before_moving_links(self):
        for name in ("patch-A.mpq", "patch-B.mpq"):
            (self.source / "Data" / name).write_bytes(b"custom")
        self.provision()
        conflict = self.root / "excluded-mpqs/Data/patch-B.mpq"
        conflict.parent.mkdir(parents=True)
        conflict.write_bytes(b"preserve")
        with self.assertRaisesRegex(ValueError, "both profile locations"):
            self.provision(stock_data=True)
        self.assertTrue((self.root / "game/Data/patch-A.mpq").is_symlink())
        self.assertEqual(conflict.read_bytes(), b"preserve")
        conflict.unlink()
        conflict.parent.rmdir()
        (self.root / "excluded-mpqs").rmdir()
        (self.root / "excluded-mpqs").symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.provision(stock_data=True)

    def test_refuses_unowned_root_and_bad_checksum(self):
        self.root.mkdir()
        with self.assertRaisesRegex(ValueError, "unowned"):
            self.provision()
        with self.assertRaisesRegex(ValueError, "checksum"):
            gc.provision(self.base / "new", self.source, "wrong")
        self.assertFalse((self.base / "new").exists())

    def test_refuses_overlap_and_symlink_root(self):
        for root in (self.source, self.source / "child", self.base):
            with self.subTest(root=root), self.assertRaises(ValueError):
                gc.provision(root, self.source, self.expected)
        self.root.symlink_to(self.source, target_is_directory=True)
        for root in (self.root, self.root / "child"):
            with self.subTest(root=root), self.assertRaises(ValueError):
                gc.provision(root, self.source, self.expected)
        self.assertFalse((self.source / "child").exists())

    def test_refuses_private_symlink_and_different_exe(self):
        self.provision()
        exe = self.root / "game/Wow.exe"
        exe.write_bytes(b"changed private fixture")
        with self.assertRaisesRegex(ValueError, "different existing"):
            self.provision()
        self.assertEqual(exe.read_bytes(), b"changed private fixture")
        exe.unlink()
        exe.symlink_to(self.source / "Wow.exe")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.provision()

    def test_refuses_redirected_config_and_mpq(self):
        self.provision()
        config = self.root / "game/WTF/Config.wtf"
        config.unlink()
        config.symlink_to(self.source / "WTF/Config.wtf")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.provision()
        config.unlink()
        mpq = self.root / "game/Data/common.MPQ"
        mpq.unlink()
        mpq.symlink_to(self.source / "Wow.exe")
        with self.assertRaisesRegex(ValueError, "MPQ"):
            self.provision()

    def test_optional_addon_is_private_copy(self):
        addon = self.base / "WoWPilago"
        addon.mkdir()
        (addon / "WoWPilago.toc").write_text("## Interface: 30300\n")
        self.provision(addon=addon)
        dst = self.root / "game/Interface/AddOns/WoWPilago/WoWPilago.toc"
        self.assertFalse(dst.is_symlink())
        self.assertEqual(dst.read_text(), (addon / dst.name).read_text())
        self.assertFalse((self.root / "game/Interface/AddOns/Other").exists())

    def test_custom_source_survives_launch_and_cleared_child_environment(self):
        spec = importlib.util.spec_from_file_location("custom_gui_client", gc.__file__)
        parent = importlib.util.module_from_spec(spec)
        with patch.dict(gc.os.environ, {"WOWPILAGO_CLIENT": str(self.source / ".." / "source")}):
            spec.loader.exec_module(parent)
        self.assertEqual(parent.SOURCE, self.source)
        before = self.snapshot()
        parent.provision(root=self.root, expected=self.expected)
        with patch.object(parent.Path, "exists", return_value=False), patch.object(
                parent, "private_layout", return_value=nullcontext((self.root, parent.SOURCE))), patch.object(
                parent, "populate") as populate, patch.object(
                parent, "run_client", side_effect=parent.sandbox_command) as run:
            parent.launch(195, root=self.root)
            populate.assert_called_once_with(self.root, self.source, None, False)
            run.assert_called_once_with(self.root, 195, False)
        command = parent.sandbox_command(self.root, 195)
        self.assertIn("--clearenv", command)
        env = {command[i + 1]: command[i + 2]
               for i, arg in enumerate(command) if arg == "--setenv"}
        self.assertEqual(env["WOWPILAGO_CLIENT"], str(self.source))
        child = importlib.util.module_from_spec(spec)
        with patch.dict(gc.os.environ, env, clear=True):
            spec.loader.exec_module(child)
            self.assertEqual(child.SOURCE, parent.SOURCE)
            with patch.object(child, "SHA256", self.expected), patch.object(
                    child.os, "statvfs", return_value=Mock(f_flag=gc.os.ST_RDONLY)) as statvfs, patch.object(
                    child.subprocess, "run"), patch.object(child.subprocess, "call", return_value=0) as wine:
                self.assertEqual(child.wine_session(self.root), 0)
                statvfs.assert_called_once_with(self.source)
                wine.assert_called_once_with(["wine", "Wow.exe", "-opengl", "-nosound"])
                statvfs.return_value.f_flag = 0
                wine.reset_mock()
                with self.assertRaisesRegex(ValueError, "private read-only sandbox"):
                    child.wine_session(self.root)
                wine.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_source_default_is_repository_local(self):
        spec = importlib.util.spec_from_file_location("default_gui_client", gc.__file__)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(gc.os.environ, {}, clear=True):
            spec.loader.exec_module(module)
        self.assertEqual(module.SOURCE, module.REPO / ".local/client-source")

    def test_internal_wine_entry_refuses_host_environment(self):
        with patch.dict(gc.os.environ, {}, clear=True), patch.object(gc.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "private read-only sandbox"):
                gc.wine_session()
            run.assert_not_called()

    def test_one_parent_per_prefix(self):
        self.provision()
        with (self.root / ".launch.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, "already owns"):
                self.provision(stock_data=True)
            layout = gc.private_layout
            with patch.object(gc, "private_layout", side_effect=lambda root: layout(
                    root, self.source, self.expected)):
                with self.assertRaisesRegex(ValueError, "already owns"):
                    gc.launch(195, root=self.root)

    def test_separate_roots_have_independent_parent_locks(self):
        self.provision()
        second = self.base / "second"
        gc.provision(second, self.source, self.expected)
        with gc.private_layout(self.root, self.source, self.expected):
            with gc.private_layout(second, self.source, self.expected) as (root, _):
                self.assertEqual(root, second)

    def test_root_cli_forwarding(self):
        for root_args, root in (([], gc.ROOT), (["--root", str(self.root)], self.root)):
            for command in ("provision", "launch", "_wine"):
                with self.subTest(command=command, root=root), patch.object(
                        gc.sys, "argv", ["gui_client.py", command, *root_args]), patch.object(
                        gc, "provision") as provision, patch.object(gc, "launch") as launch, patch.object(
                        gc, "wine_session", return_value=7) as wine, patch("builtins.print"):
                    result = gc.main()
                    if command == "provision":
                        provision.assert_called_once_with(root=root, addon=None, stock_data=False)
                    elif command == "launch":
                        launch.assert_called_once_with(94, False, False, root=root)
                    else:
                        wine.assert_called_once_with(root)
                        self.assertEqual(result, 7)

    def test_launch_root_forwarding(self):
        for kwargs, root in (({}, gc.ROOT), ({"root": self.root}, self.root)):
            with self.subTest(root=root), patch.object(gc.Path, "exists", return_value=False), patch.object(
                    gc, "private_layout", return_value=nullcontext((root, self.source))) as layout, patch.object(
                    gc, "populate") as populate, patch.object(gc, "run_client") as run:
                gc.launch(195, True, True, **kwargs)
                layout.assert_called_once_with(root)
                populate.assert_called_once_with(root, self.source, None, True)
                run.assert_called_once_with(root, 195, True)

    def test_sandbox_roots_have_isolated_environments(self):
        for root in (gc.ROOT, self.root, self.base / "second"):
            with self.subTest(root=root):
                command = gc.sandbox_command(root, 195)
                self.assertEqual(command[-3:], ["_wine", "--root", str(root)])
                env = {command[i + 1]: command[i + 2]
                       for i, arg in enumerate(command) if arg == "--setenv"}
                self.assertEqual(env["WOWPILAGO_CLIENT"], str(gc.SOURCE))
                self.assertEqual(env["HOME"], str(root / "home"))
                self.assertEqual(env["WINEPREFIX"], str(root / "prefix"))
                self.assertEqual(env["XDG_CACHE_HOME"], str(root / "home/.cache"))
                bind = command.index("--bind")
                self.assertEqual(command[bind + 1:bind + 3], [str(root), str(root)])
                self.assertEqual(command[command.index("--ro-bind") + 1:][:2], ["/", "/"])

    def run_cleanup_case(self, wine_wait, wine_poll=None, x_poll=None, kill=None):
        self.provision()
        xvfb = Mock(pid=101)
        wine = Mock(pid=102)
        xvfb.poll.side_effect = [None, x_poll]
        xvfb.wait.return_value = 0
        wine.poll.return_value = wine_poll
        wine.wait.side_effect = wine_wait
        exists = Path.exists
        with patch.object(gc.subprocess, 'Popen', side_effect=[xvfb, wine]), \
                patch.object(gc.signal, 'signal'), patch.object(gc.os, 'killpg', side_effect=kill) as signals, \
                patch.object(gc.time, 'sleep'), patch.object(gc.Path, 'exists', autospec=True,
                    side_effect=lambda p: str(p) == '/tmp/.X11-unix/X195' or exists(p)), \
                patch('builtins.print'):
            try:
                gc.run_client(self.root, 195, False)
            finally:
                self.cleanup_signals = signals.call_args_list
                self.cleanup_children = (xvfb, wine)

    def cleanup_record(self):
        records = list((self.root / 'evidence').glob('run-*/cleanup.json'))
        self.assertEqual(len(records), 1)
        return json.loads(records[0].read_text())

    def test_cleanup_natural_exit_is_not_forced(self):
        self.run_cleanup_case([0], wine_poll=0, x_poll=0)
        record = self.cleanup_record()
        self.assertTrue(record['complete'])
        self.assertFalse(record['forced'])
        self.assertEqual(record['signals'], [])
        self.assertEqual(self.cleanup_signals, [])

    def test_cleanup_success_does_not_erase_session_failure(self):
        with self.assertRaisesRegex(RuntimeError, 'exited 7'):
            self.run_cleanup_case([7], wine_poll=7, x_poll=0)
        self.assertTrue(self.cleanup_record()['complete'])
        self.assertFalse(self.cleanup_record()['forced'])
        self.assertEqual(self.cleanup_signals, [])

    def test_cleanup_normal_sigterm_is_not_forced(self):
        self.run_cleanup_case([KeyboardInterrupt(), 0])
        record = self.cleanup_record()
        self.assertTrue(record['complete'])
        self.assertFalse(record['forced'])
        self.assertEqual(self.cleanup_signals, [call(102, signal.SIGTERM), call(101, signal.SIGTERM)])

    def test_cleanup_force_kill_fails_after_other_child_cleanup(self):
        with self.assertRaisesRegex(RuntimeError, 'forced'):
            self.run_cleanup_case([KeyboardInterrupt(), subprocess.TimeoutExpired('wine', 10), 0])
        record = self.cleanup_record()
        self.assertTrue(record['complete'])
        self.assertTrue(record['forced'])
        self.assertEqual(self.cleanup_signals, [call(102, signal.SIGTERM), call(102, signal.SIGKILL),
                                                 call(101, signal.SIGTERM)])
        self.assertEqual(record['signals'], [dict(pid=102, signal=int(signal.SIGTERM)),
            dict(pid=102, signal=int(signal.SIGKILL)), dict(pid=101, signal=int(signal.SIGTERM))])
        self.cleanup_children[0].wait.assert_called_once_with(timeout=10)

    def test_cleanup_error_does_not_skip_other_child_or_erase_session_error(self):
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed') as caught:
            self.run_cleanup_case([7], kill=[PermissionError(), None])
        self.assertIsInstance(caught.exception.__context__, RuntimeError)
        self.assertIn('exited 7', str(caught.exception.__context__))
        record = self.cleanup_record()
        self.assertFalse(record['complete'])
        self.assertEqual(record['errors'], [dict(pid=102, error='PermissionError')])
        self.assertEqual(self.cleanup_signals, [call(102, signal.SIGTERM), call(101, signal.SIGTERM)])
        self.cleanup_children[0].wait.assert_called_once_with(timeout=10)

    @contextmanager
    def child_sandbox(self, root=None):
        root = self.root if root is None else root
        env = {"HOME": str(root / "home"), "WINEPREFIX": str(root / "prefix"), "DISPLAY": ":195"}
        with patch.object(gc, "SOURCE", self.source), patch.object(gc, "SHA256", self.expected), patch.dict(
                gc.os.environ, env, clear=True), patch.object(
                gc.os, "statvfs", return_value=Mock(f_flag=gc.os.ST_RDONLY)) as statvfs, patch.object(
                gc.subprocess, "run") as run, patch.object(gc.subprocess, "call", return_value=0) as wine:
            yield statvfs, run, wine

    def test_child_owned_root_and_prefix_scoped_cleanup(self):
        before = self.snapshot()
        for root in (self.root, self.base / "second"):
            gc.provision(root, self.source, self.expected)
            with self.child_sandbox(root) as (statvfs, run, wine):
                self.assertEqual(gc.wine_session(root), 0)
                statvfs.assert_called_once_with(self.source)
                wine.assert_called_once_with(["wine", "Wow.exe", "-opengl", "-nosound"])
                self.assertEqual(run.call_args_list, [call(["wineboot", "-u"], check=True),
                                                     call(["wineserver", "-k"], check=False)])
                wine.side_effect = RuntimeError("fixture failure")
                with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                    gc.wine_session(root)
                self.assertEqual(run.call_args_list[-1], call(["wineserver", "-k"], check=False))
        self.assertEqual(self.snapshot(), before)

    def test_child_refuses_wrong_environment_and_writable_source(self):
        self.provision()
        cases = [{"HOME": str(self.source)}, {"WINEPREFIX": str(self.base / "other")},
                 *({"DISPLAY": display} for display in ("", ":0", ":93", ":0.0", ":93.0", ":00", "host:0"))]
        for env in cases:
            with self.subTest(env=env), self.child_sandbox() as (_, run, wine), patch.dict(gc.os.environ, env):
                with self.assertRaisesRegex(ValueError, "private read-only sandbox"):
                    gc.wine_session(self.root)
                run.assert_not_called()
                wine.assert_not_called()
        with self.child_sandbox() as (statvfs, run, wine):
            statvfs.return_value.f_flag = 0
            with self.assertRaisesRegex(ValueError, "private read-only sandbox"):
                gc.wine_session(self.root)
            run.assert_not_called()
            wine.assert_not_called()

    def test_child_refuses_unsafe_roots_without_creating_them(self):
        self.provision()
        unowned = self.base / "unowned"
        unowned.mkdir()
        alias = self.base / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        roots = (self.base / "missing", unowned, alias, alias / "home", self.source,
                 self.source / "child", self.base, self.root / ".." / self.root.name)
        for root in roots:
            with self.subTest(root=root), self.child_sandbox(root) as (_, run, wine):
                with self.assertRaises(ValueError):
                    gc.wine_session(root)
                run.assert_not_called()
                wine.assert_not_called()
        self.assertFalse((self.base / "missing").exists())
        self.assertFalse((self.source / "child").exists())

    def test_child_rechecks_marker_paths_and_hashes(self):
        self.provision()
        for relative in (".owner", "home", "prefix", "game/Wow.exe"):
            path = self.root / relative
            saved = path.with_name(path.name + ".saved")
            path.rename(saved)
            path.symlink_to(saved, target_is_directory=saved.is_dir())
            with self.subTest(path=relative), self.child_sandbox() as (_, run, wine):
                with self.assertRaisesRegex(ValueError, "symlink"):
                    gc.wine_session(self.root)
                run.assert_not_called()
                wine.assert_not_called()
            path.unlink()
            saved.rename(path)
        for path, data in ((self.root / ".owner", b"wrong owner"),
                           (self.root / "game/Wow.exe", b"wrong exe"),
                           (self.source / "Wow.exe", b"wrong source exe")):
            original = path.read_bytes()
            path.write_bytes(data)
            with self.subTest(path=path), self.child_sandbox() as (_, run, wine):
                with self.assertRaises(ValueError):
                    gc.wine_session(self.root)
                run.assert_not_called()
                wine.assert_not_called()
            path.write_bytes(original)

    def test_sandbox_and_display_guards(self):
        command = gc.sandbox_command(self.root, 94, software=True)
        self.assertIn("--ro-bind", command)
        self.assertIn("--clearenv", command)
        self.assertIn("--unshare-pid", command)
        self.assertIn("LIBGL_ALWAYS_SOFTWARE", command)
        self.assertIn(":94", command)
        for display in (0, 93, -1):
            with self.assertRaises(ValueError):
                gc.launch(display)


if __name__ == "__main__":
    unittest.main()
