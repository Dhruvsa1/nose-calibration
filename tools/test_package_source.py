"""package.ps1 -CheckSourceOnly in a throwaway Git repository; nothing is built or published."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SHELL = shutil.which('pwsh') or shutil.which('powershell')

class PackageSourceTests(unittest.TestCase):
    def setUp(self):
        if not SHELL or not shutil.which('git'):
            self.skipTest('PowerShell and Git required')
        self.repo = Path(tempfile.mkdtemp(prefix='nose-package-test-'))
        (self.repo/'tools').mkdir()
        (self.repo/'docs').mkdir()
        (self.repo/'collector').mkdir()
        shutil.copy(TOOLS/'package.ps1', self.repo/'tools'/'package.ps1')
        (self.repo/'collector'/'NoseCalibration.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net8.0-windows</TargetFramework>'
            '<VersionPrefix>0.1.0</VersionPrefix></PropertyGroup></Project>')
        (self.repo/'docs'/'PACKAGE-README.txt').write_text('Approved study release text.\n')
        self.git('init', '-q')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'synthetic')
        self.revision = self.git('rev-parse', 'HEAD').strip()

    def tearDown(self):
        if hasattr(self, 'repo'):
            target=self.repo.resolve()
            if target.parent != Path(tempfile.gettempdir()).resolve() or not target.name.startswith('nose-package-test-'):
                raise RuntimeError('Refusing cleanup outside the test temporary directory')
            def writable(function, path, error):
                import stat
                os.chmod(path, stat.S_IWRITE)
                function(path)
            shutil.rmtree(target, onerror=writable)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid',
                               '-c', 'commit.gpgsign=false', *args], capture_output=True, text=True, check=True).stdout

    def check(self, *args):
        env = {k: v for k, v in os.environ.items() if k.upper() != 'PSMODULEPATH'}
        r = subprocess.run([SHELL, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
                            str(self.repo/'tools'/'package.ps1'), '-CheckSourceOnly', *args], capture_output=True, text=True, env=env, timeout=120)
        return r.returncode, r.stdout, r.stderr

    def test_clean_release_identity(self):
        code, out, err = self.check()
        self.assertEqual(code, 0, err)
        s = json.loads(out)
        self.assertEqual((s['channel'], s['sourceRevision'], s['sourceTreeClean'], s['informationalVersion']),
                         ('release', self.revision, True, f'0.1.0+{self.revision}'))

    def test_release_refuses_modified_and_untracked(self):
        for change in ('modify', 'untracked'):
            with self.subTest(change=change):
                if change == 'modify':
                    (self.repo/'tools'/'package.ps1').write_text((self.repo/'tools'/'package.ps1').read_text() + '\n# local edit\n')
                else:
                    self.git('checkout', '--', '.')
                    (self.repo/'docs'/'new.txt').write_text('x')
                code, _, err = self.check()
                self.assertNotEqual(code, 0)
                self.assertIn('clean committed tree', err)

    def test_preview_records_dirty_paths_bounded(self):
        for i in range(60):
            (self.repo/'docs'/f'extra{i:02}.txt').write_text('x')
        code, out, err = self.check('-Preview')
        self.assertEqual(code, 0, err)
        s = json.loads(out)
        self.assertFalse(s['sourceTreeClean'])
        self.assertEqual((s['uncommittedPathCount'], len(s['uncommittedPaths']), s['uncommittedPathsTruncated']), (60, 50, True))
        self.assertEqual(s['informationalVersion'], f'0.1.0-preview+{self.revision}.dirty')

    def test_release_refuses_preview_wording(self):
        (self.repo/'docs'/'PACKAGE-README.txt').write_text('Development preview packages are not approved.\n')
        self.git('commit', '-qam', 'preview wording')
        code, _, err = self.check()
        self.assertNotEqual(code, 0)
        self.assertIn('development preview', err)
        self.assertEqual(self.check('-Preview')[0], 0)

    def test_requires_version_prefix(self):
        (self.repo/'collector'/'NoseCalibration.csproj').write_text('<Project><PropertyGroup></PropertyGroup></Project>')
        code, _, err = self.check('-Preview')
        self.assertNotEqual(code, 0)
        self.assertIn('VersionPrefix', err)

if __name__ == '__main__':
    unittest.main()
