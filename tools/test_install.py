"""Install.ps1 against synthetic packages in a temporary folder.

LOCALAPPDATA and the shortcut folder point into the temporary folder, so the real AppData,
Start menu and recordings are untouched. The synthetic NoseCalibration.exe is never run.
"""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

INSTALLER = Path(__file__).resolve().parent/'Install.ps1'
SHELLS = [s for s in (shutil.which('powershell'), shutil.which('pwsh')) if s]

def manifest_for(root):
    return [{'path': p.relative_to(root).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
            for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'package-files.json']

class InstallTests(unittest.TestCase):
    shell = SHELLS[0] if SHELLS else None

    def setUp(self):
        if not self.shell:
            self.skipTest('PowerShell not available')
        self.tmp = Path(tempfile.mkdtemp(prefix='nose-install-test-'))
        self.local = self.tmp/'LocalAppData'
        self.local.mkdir()
        self.start = self.tmp/'StartPrograms'
        self.start.mkdir()
        self.pkg = self.tmp/'extract'/'NoseCalibration'
        (self.pkg/'web').mkdir(parents=True)
        (self.pkg/'NoseCalibration.exe').write_bytes(b'MZ synthetic, never executed')
        (self.pkg/'web'/'app.js').write_text('// synthetic')
        (self.pkg/'START-HERE.txt').write_text('synthetic')
        (self.pkg/'package-source.json').write_text(json.dumps({'informationalVersion': '0.1.0-preview+test', 'channel': 'preview'}))
        shutil.copy(INSTALLER, self.pkg/'Install.ps1')
        self.write_manifest()

    def tearDown(self):
        if hasattr(self, 'tmp'):
            subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', str(self.tmp)], capture_output=True)

    def write_manifest(self, entries=None):
        (self.pkg/'package-files.json').write_text(json.dumps(manifest_for(self.pkg) if entries is None else entries))

    def run_installer(self, *extra):
        env = {k: v for k, v in os.environ.items() if k.upper() != 'PSMODULEPATH'}
        env['LOCALAPPDATA'] = str(self.local)
        result = subprocess.run([self.shell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
                                 str(self.pkg/'Install.ps1'), '-ShortcutFolder', str(self.start), '-NoPause', *extra],
                                capture_output=True, text=True, env=env, timeout=120)
        return result.returncode, result.stdout + result.stderr

    def installs(self):
        base = self.local/'Programs'/'NoseCalibration'
        return sorted(p.name for p in base.iterdir()) if base.exists() else []

    def assert_rejected(self, reason):
        before_shortcut = self.shortcut_bytes()
        before = self.installs()
        code, out = self.run_installer()
        self.assertEqual(code, 1, out)
        self.assertIn('was NOT installed', out)
        self.assertIn(reason, out)
        self.assertEqual(self.installs(), before)
        self.assertEqual(self.shortcut_bytes(), before_shortcut)
        self.assertFalse((self.local/'NoseCalibration').exists())

    def shortcut_bytes(self):
        lnk = self.start/'Nose Calibration.lnk'
        return lnk.read_bytes() if lnk.exists() else None

    def test_installs_verified_copy_and_shortcut(self):
        code, out = self.run_installer()
        self.assertEqual(code, 0, out)
        self.assertIn('Installed Nose Calibration 0.1.0-preview+test (preview)', out)
        self.assertIn('does not show who built it', out)
        [name] = self.installs()
        dest = self.local/'Programs'/'NoseCalibration'/name
        self.assertEqual(sorted(p.relative_to(dest).as_posix() for p in dest.rglob('*') if p.is_file()),
                         sorted(p.relative_to(self.pkg).as_posix() for p in self.pkg.rglob('*') if p.is_file()))
        self.assertEqual((dest/'NoseCalibration.exe').read_bytes(), (self.pkg/'NoseCalibration.exe').read_bytes())
        self.assertIsNotNone(self.shortcut_bytes())
        self.assertFalse((self.local/'NoseCalibration').exists(), 'installer must not create the recordings folder')

    def test_repeat_install_uses_new_folder_and_keeps_earlier(self):
        self.assertEqual(self.run_installer()[0], 0)
        first = self.installs()
        self.assertEqual(self.run_installer()[0], 0)
        self.assertEqual(len(self.installs()), 2)
        self.assertTrue(set(first) <= set(self.installs()))

    def test_tampered_content_same_size(self):
        (self.start/'Nose Calibration.lnk').write_bytes(b'existing shortcut')
        (self.pkg/'web'/'app.js').write_text('// SYNTHETIC')
        self.assert_rejected('content differs')

    def test_size_mismatch(self):
        (self.pkg/'web'/'app.js').write_text('// synthetic, longer')
        self.assert_rejected('size differs')

    def test_extra_file(self):
        (self.pkg/'helper.ps1').write_text('# not listed')
        self.assert_rejected('not listed in package-files.json')

    def test_missing_file(self):
        (self.pkg/'web'/'app.js').unlink()
        self.assert_rejected('Missing package file')

    def test_missing_manifest(self):
        (self.pkg/'package-files.json').unlink()
        self.assert_rejected('package-files.json is missing')

    def test_unsafe_manifest_paths(self):
        good = manifest_for(self.pkg)
        for path in ('../outside.txt', 'web/../../outside.txt', 'C:/Windows/x.dll', '/abs.txt', 'web\\app.js',
                     './web/app.js', 'web//app.js', '.hidden', 'web/app.js:stream'):
            with self.subTest(path=path):
                self.write_manifest(good + [{'path': path, 'sha256': '0'*64, 'bytes': 1}])
                self.assert_rejected('Unsafe path')

    def test_duplicate_and_malformed_entries(self):
        good = manifest_for(self.pkg)
        cases = {
            'Duplicate path': good + [dict(good[0], path=good[0]['path'].upper())],
            'Invalid digest': [dict(good[0], sha256='ZZ')] + good[1:],
            'Invalid size': [dict(good[0], bytes=-1)] + good[1:],
            'unexpected entry format': [dict(good[0], mode='755')] + good[1:],
        }
        for reason, entries in cases.items():
            with self.subTest(reason=reason):
                self.write_manifest(entries)
                self.assert_rejected(reason)

    def test_junction_inside_package(self):
        outside = self.tmp/'outside'
        outside.mkdir()
        (outside/'x.txt').write_text('x')
        made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(self.pkg/'linked'), str(outside)], capture_output=True)
        if made.returncode:
            self.skipTest('could not create a junction')
        self.assert_rejected('reparse point')
        self.assertTrue((outside/'x.txt').exists())

    def test_failure_after_copy_removes_partial_and_keeps_shortcut(self):
        self.assertEqual(self.run_installer()[0], 0)
        earlier = self.installs()
        original = self.shortcut_bytes()
        bad_start = self.tmp/'not-a-folder'
        bad_start.write_text('file, not folder')
        env_start, self.start = self.start, bad_start
        code, out = self.run_installer()
        self.start = env_start
        self.assertEqual(code, 1, out)
        self.assertIn('Start menu folder not found', out)
        self.assertEqual(self.installs(), earlier)
        self.assertEqual(self.shortcut_bytes(), original)

    def test_refuses_recordings_folder_and_package_folder(self):
        for target in (self.local/'NoseCalibration'/'x', self.local, self.pkg/'sub'):
            with self.subTest(target=target):
                code, out = self.run_installer('-InstallBase', str(target))
                self.assertEqual(code, 1, out)
                self.assertIn('Refusing', out)
                self.assertFalse((self.local/'NoseCalibration').exists())
                self.assertFalse((self.pkg/'sub').exists())

@unittest.skipUnless(len(SHELLS) == 2, 'needs both Windows PowerShell and PowerShell 7')
class InstallPwsh7Tests(InstallTests):
    shell = SHELLS[1] if len(SHELLS) == 2 else None

if __name__ == '__main__':
    unittest.main()
