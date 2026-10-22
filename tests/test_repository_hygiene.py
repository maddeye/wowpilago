"""Publication boundaries must keep local secrets out without hiding setup examples."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RepositoryHygieneTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('git'), 'Git is required to check ignore rules')
    def test_private_files_are_ignored_but_example_config_is_publishable(self):
        private = ['bridge.toml', 'bridge.local.toml', '.env', '.env.local',
                   '.local/realm/credentials.json', 'NEW.local/snapshot.json',
                   '.venv/token', 'dist/WoWPilago.zip', 'room.apsave', 'private.key',
                   'client/Wow.exe', 'client/engine.DLL', 'client/Data/patch.MPQ',
                   'data/AreaTable.dbc', 'data/000.mmap', 'backup.sql.gz',
                   'CMakeFiles/output', 'CMakeCache.txt', 'compile_commands.json']
        public = ['examples/bridge.toml', 'examples/player.yaml', '.env.example',
                  'src/APProgression.cpp', 'docs/SECURITY.md']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', '-c', 'init.defaultBranch=main', 'init', '-q', directory], check=True)
            shutil.copyfile(ROOT / '.gitignore', root / '.gitignore')
            for name in private + public:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture\n')
            result = subprocess.run(['git', 'check-ignore', '--no-index', '--stdin'],
                                    cwd=root, input='\n'.join(private + public) + '\n',
                                    text=True, capture_output=True, check=True)
            self.assertEqual(set(result.stdout.splitlines()), set(private))


if __name__ == '__main__':
    unittest.main()
