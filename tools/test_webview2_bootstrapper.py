"""Synthetic WebView2 bootstrapper pin, staging, build and Setup-policy checks.

Nothing here downloads, executes or installs anything. Signatures come from a fake reader,
the compiler is replaced by a stub, and collector-setup.iss is checked as source text.
"""
import hashlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import build_installer
import webview2_bootstrapper as wb
from test_verify_package import build as build_zip, files as package_files

ROOT = Path(__file__).resolve().parents[1]
ISS = (ROOT / 'tools' / 'collector-setup.iss').read_text(encoding='utf-8')
DATA = b'MZ synthetic bootstrapper, never executed'


def synthetic_pin(data=DATA):
    pin = wb.load_pin()
    pin.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), fileVersion='1.2.3.4')
    return pin


def signature(pin, **changes):
    sig = {'status': 'Valid', 'signatureType': 'Authenticode', 'subject': pin['signerSubject'],
           'issuer': pin['issuerSubject'], 'thumbprint': pin['signerThumbprint'], 'chainBuilt': True,
           'chain': [pin['signerThumbprint'], '5039C8DC9ACE1CE039587E43486DE073FA459222', pin['allowedRootThumbprints'][0]],
           'ekus': ['1.3.6.1.4.1.311.10.3.21', wb.CODE_SIGNING_EKU], 'timeStamper': 'CN=Microsoft Time-Stamp Service',
           'fileVersion': pin['fileVersion']}
    sig.update(changes)
    return sig


class PinTests(unittest.TestCase):
    def test_committed_pin_is_valid_and_official(self):
        pin = wb.load_pin()
        self.assertEqual(pin['officialLink'], 'https://go.microsoft.com/fwlink/p/?LinkId=2124703')
        self.assertEqual(pin['signerSubject'], wb.MICROSOFT_SUBJECT)
        for source in pin['sources']:
            self.assertRegex(source, r'^https://(learn\.microsoft\.com|developer\.microsoft\.com|github\.com/MicrosoftEdge)/')

    def test_pin_tampering_rejected(self):
        bad = {
            'official Microsoft': {'officialLink': 'https://example.com/MicrosoftEdgeWebview2Setup.exe'},
            'Microsoft domains': {'allowedDownloadHosts': ['go.microsoft.com', 'microsoft.com.example.net']},
            'lowercase SHA-256': {'sha256': 'latest'},
            'size invalid': {'bytes': 0},
            'Microsoft Corporation signer': {'signerSubject': 'CN=Someone Else'},
            'thumbprints invalid': {'allowedRootThumbprints': []},
            'format mismatch': {'extra': True},
        }
        base = json.loads((ROOT / 'docs' / 'webview2-bootstrapper.json').read_text())
        for message, change in bad.items():
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'pin.json'
                path.write_text(json.dumps(base | change))
                with self.assertRaisesRegex(ValueError, message):
                    wb.load_pin(path)


class VerifyTests(unittest.TestCase):
    def check(self, data=DATA, pin=None, **sig_changes):
        pin = pin or synthetic_pin()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'b.exe'
            path.write_bytes(data)
            return wb.verify(path, pin, lambda _: signature(pin, **sig_changes))

    def test_valid_synthetic_file(self):
        result = self.check()
        self.assertFalse(result['executedDuringBuild'])
        self.assertEqual(result['sha256'], hashlib.sha256(DATA).hexdigest())

    def test_bytes_must_match_pin(self):
        with self.assertRaisesRegex(ValueError, 'differs from the reviewed pin'):
            self.check(data=DATA + b'x', pin=synthetic_pin())
        with self.assertRaisesRegex(ValueError, 'not a Windows executable'):
            self.check(data=b'ZZ', pin=synthetic_pin(b'ZZ'))

    def test_signature_failures(self):
        pin = synthetic_pin()
        cases = {
            'not valid': {'status': 'HashMismatch'},
            'not valid ': {'status': 'NotSigned'},
            'not valid  ': {'signatureType': 'Catalog'},
            'not Microsoft': {'subject': 'CN=Microsoft Corporation Fake'},
            'signer certificate differs': {'thumbprint': 'A' * 40},
            'issuing CA': {'issuer': 'CN=Other CA'},
            'allowed Microsoft root': {'chain': [pin['signerThumbprint'], 'B' * 40]},
            'allowed Microsoft root ': {'chainBuilt': False},
            'code-signing usage': {'ekus': ['1.3.6.1.5.5.7.3.1']},
            'file version': {'fileVersion': '9.9.9.9'},
        }
        for message, change in cases.items():
            with self.subTest(change=change):
                with self.assertRaisesRegex(ValueError, message.strip()):
                    self.check(pin=pin, **change)


@unittest.skipUnless(wb.DEFAULT_PATH.is_file(), 'Pinned bootstrapper not prepared (tools/webview2_bootstrapper.py fetch)')
class PreparedBootstrapperTest(unittest.TestCase):
    def test_prepared_file_matches_pin_and_microsoft_signature(self):
        # Static only: hashes the file and reads its embedded signature; never runs it.
        pin = wb.load_pin()
        with tempfile.TemporaryDirectory() as tmp:
            result = wb.verify(wb.snapshot(wb.DEFAULT_PATH, tmp, pin), pin)
        self.assertEqual((result['signatureStatus'], result['rootThumbprint']), ('Valid', pin['allowedRootThumbprints'][0]))


class SnapshotTests(unittest.TestCase):
    def test_copy_is_independent_of_later_source_changes(self):
        pin = synthetic_pin()
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'src.exe'
            src.write_bytes(DATA)
            (Path(tmp) / 'out').mkdir()
            staged = wb.snapshot(src, Path(tmp) / 'out', pin)
            src.write_bytes(b'MZ replaced after staging')
            self.assertEqual(staged.read_bytes(), DATA)
            self.assertEqual(staged.name, 'MicrosoftEdgeWebview2Setup.exe')

    def test_rejects_missing_directory_and_link(self):
        pin = synthetic_pin()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out'
            out.mkdir()
            with self.assertRaisesRegex(ValueError, 'not found'):
                wb.snapshot(Path(tmp) / 'missing.exe', out, pin)
            with self.assertRaisesRegex(ValueError, 'regular file'):
                wb.snapshot(out, out, pin)
            target = Path(tmp) / 'real.exe'
            target.write_bytes(DATA)
            link = Path(tmp) / 'link.exe'
            try:
                os.symlink(target, link)
            except OSError:
                self.skipTest('Symbolic links need Developer Mode or privilege on this Windows account')
            with self.assertRaisesRegex(ValueError, 'regular file'):
                wb.snapshot(link, out, pin)


class FetchTests(unittest.TestCase):
    def test_redirects_limited_to_microsoft_https(self):
        handler = wb._AllowlistedRedirects(['go.microsoft.com', 'msedge.sf.dl.delivery.mp.microsoft.com'])
        for url in ('http://msedge.sf.dl.delivery.mp.microsoft.com/x.exe', 'https://evil.example/x.exe',
                    'https://go.microsoft.com.evil.example/x.exe'):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, 'Refusing'):
                handler.redirect_request(mock.Mock(), None, 301, 'Moved', {}, url)

    def test_changed_upstream_file_is_not_accepted(self):
        pin = synthetic_pin()

        class Response:
            def __init__(self, data): self.data = data
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def geturl(self): return 'https://msedge.sf.dl.delivery.mp.microsoft.com/files/x/MicrosoftEdgeWebview2Setup.exe'
            def read(self, n): return self.data[:n]

        opener = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'vendor' / 'MicrosoftEdgeWebview2Setup.exe'
            opener.open.return_value = Response(b'MZ a newer Microsoft build')
            with self.assertRaisesRegex(ValueError, 'Nothing was accepted'):
                wb.fetch(pin, dest, lambda _: signature(pin), opener)
            self.assertFalse(dest.exists())
            opener.open.return_value = Response(DATA)
            result = wb.fetch(pin, dest, lambda _: signature(pin), opener)
            self.assertEqual(dest.read_bytes(), DATA)
            self.assertEqual(result['destination'], str(dest))
            opener.open.assert_called_with('https://go.microsoft.com/fwlink/p/?LinkId=2124703', timeout=60)


class BuildInstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        f = package_files({'Nose-Calibration-Setup.pdf': b'%PDF synthetic'})
        self.zip = base / 'package.zip'
        self.zip.write_bytes(build_zip(f))
        self.sha = hashlib.sha256(self.zip.read_bytes()).hexdigest()
        self.bootstrapper = base / 'MicrosoftEdgeWebview2Setup.exe'
        self.bootstrapper.write_bytes(DATA)
        self.pin_path = base / 'pin.json'
        self.pin = synthetic_pin()
        self.pin_path.write_text(json.dumps(self.pin))
        self.compiler = base / 'ISCC.exe'
        self.compiler.write_bytes(b'stub, never executed')

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, reader=None, check_only=True, bootstrapper=None):
        reader = reader or (lambda _: signature(self.pin))
        return build_installer.build(self.zip, self.sha, self.compiler, check_only,
                                     bootstrapper or self.bootstrapper, reader, self.pin_path)

    def test_check_only_records_bootstrapper_provenance(self):
        result = self.build()
        self.assertFalse(result['installerBuilt'])
        self.assertEqual(result['webview2Bootstrapper']['sha256'], self.pin['sha256'])

    def test_missing_or_unsigned_bootstrapper_stops_build(self):
        with self.assertRaisesRegex(ValueError, 'not found'):
            self.build(bootstrapper=Path(self.tmp.name) / 'absent.exe')
        with self.assertRaisesRegex(ValueError, 'not valid'):
            self.build(reader=lambda _: signature(self.pin, status='NotSigned'))

    def test_compiler_receives_verified_snapshot_and_pinned_hash(self):
        calls = []

        def fake_run(args, check):
            calls.append(args)
            defines = dict(a[2:].split('=', 1) for a in args if a.startswith('/D'))
            staged = Path(defines['WebView2Bootstrapper'])
            self.assertEqual(staged.read_bytes(), DATA)
            self.assertNotEqual(staged.resolve(), self.bootstrapper.resolve())
            self.assertEqual(defines['WebView2BootstrapperSha256'], self.pin['sha256'])
            (Path(defines['OutputDir']) / 'NoseCalibration-Setup-0.1.0-preview-win-x64.exe').write_bytes(b'stub')

        with mock.patch.object(build_installer.subprocess, 'run', fake_run):
            result = self.build(check_only=False)
        self.assertEqual(len(calls), 1)
        provenance = json.loads((Path(result['installer']).parent / 'build-provenance.json').read_text())
        self.assertEqual(provenance['webview2Bootstrapper']['sha256'], self.pin['sha256'])
        self.assertFalse(provenance['missingRuntimeInstallTested'])
        self.assertFalse(provenance['signed'])
        output = Path(result['installer']).parent
        self.assertTrue(output.parent == ROOT / 'work' and output.name.startswith('setup-'))
        for item in output.iterdir():
            item.unlink()
        output.rmdir()


def section(name):
    match = re.search(r'^\[' + name + r'\]\n(.*?)(?=^\[|\Z)', ISS, re.M | re.S)
    return match.group(1) if match else None


class SetupScriptPolicyTests(unittest.TestCase):
    def test_existing_installer_policy_is_unchanged(self):
        for line in ('PrivilegesRequired=lowest', 'AppMutex=Local\\NoseCalibration.Collector.Running',
                     'SetupMutex=Local\\NoseCalibration.Collector.Setup', 'CloseApplications=no',
                     'DefaultDirName={localappdata}\\Programs\\NoseCalibration\\releases\\{#PayloadId}'):
            self.assertIn('\n' + line + '\n', ISS)
        for name in ('Run', 'Registry', 'Tasks', 'InstallDelete', 'UninstallDelete', 'UninstallRun'):
            self.assertIsNone(section(name), name)
        self.assertNotRegex(ISS, r'(?im)^\s*(SetupArchitecture|PrivilegesRequiredOverridesAllowed)\s*=')

    def test_bootstrapper_is_bundled_hash_checked_and_never_installed(self):
        files = section('Files').strip().splitlines()
        entry = next(l for l in files if l.startswith('Source:'))
        self.assertIn('"{#WebView2Bootstrapper}"', entry)  # first entry: fast solid extraction
        self.assertIn('Flags: dontcopy noencryption', entry)
        self.assertIn('Hash: "{#WebView2BootstrapperSha256}"', entry)
        self.assertNotIn('DestDir', entry)

    def test_code_detects_both_documented_locations_and_fails_closed(self):
        code = section('Code')
        self.assertIn("'Software\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'", code)
        self.assertIn('UsableRuntimeVersion(HKLM32, Version)', code)
        self.assertIn('UsableRuntimeVersion(HKCU, Version)', code)
        self.assertIn("StrToVersion(Version, PackedVersion) and (PackedVersion > 0)", code)
        self.assertIn("WebView2SetupArgs = '/silent /install'", code)
        prepare = code[code.index('function PrepareToInstall'):]
        self.assertRegex(prepare, r'if WebView2RuntimeReady then\s+Result := \'\'\s+else\s+Result := InstallWebView2Runtime')
        install = code[code.index('function InstallWebView2Runtime'):code.index('function PrepareToInstall')]
        # Success only through a fresh detection after Microsoft's installer exits.
        self.assertRegex(install, r"if WebView2RuntimeReady then\s+Exit;")
        self.assertIn('GetSHA256OfStream(Locked), WebView2ExpectedSha256', install)
        self.assertIn('OpenReadDenyWrite', install)
        self.assertIn('IsCurrentProcess64Bit', install)

    def test_no_download_elevation_kill_or_persistence_in_setup(self):
        code = section('Code')
        for forbidden in ('http', 'DownloadTemporaryFile', 'CreateDownloadPage', 'ShellExec', 'runas', 'TerminateProcess',
                          'RegWrite', 'RunOnce', 'RestartReplace', 'DeleteFile', 'DelTree', 'ewNoWait', 'Exec('):
            self.assertNotIn(forbidden, code, forbidden)

    def test_timeout_offers_retry_and_defaults_to_cancel_when_suppressed(self):
        code = section('Code')
        self.assertIn('WaitRoundSlices = 2400', code)
        self.assertIn('MB_RETRYCANCEL, IDCANCEL) = IDRETRY', code)

    def test_silent_runs_never_request_an_automatic_restart(self):
        # Inno reboots a /VERYSILENT run without asking, and /SILENT /SUPPRESSMSGBOXES answers Yes,
        # unless the caller passes /NORESTART. Setup must not depend on the caller remembering it.
        code = section('Code')
        self.assertEqual(re.findall(r'NeedsRestart\s*:=\s*([^;]+);', code), ['not WizardSilent'])
        self.assertNotRegex(code, r'(?i)function\s+NeedRestart\b')
        install = code[code.index('function InstallWebView2Runtime'):code.index('function PrepareToInstall')]
        # Only reached when fresh detection failed; the actionable message still stops Setup
        # (exit 7 silent, 8 interactive) before any program file is copied.
        self.assertLess(install.index('if WebView2RuntimeReady then'), install.index('NeedsRestart :='))
        self.assertRegex(install, r"NeedsRestart := not WizardSilent;\s+Result := 'Microsoft''s WebView2 installer needs "
                                  r"Windows to restart\. Nose Calibration was not installed\.' \+\s+ParaBreak \+ "
                                  r"'Restart Windows, then run this setup again\.';")

    def test_wizard_cancel_is_ignored_only_while_microsofts_installer_runs(self):
        code = section('Code')
        handler = re.search(r'procedure CancelButtonClick\(CurPageID: Integer; var Cancel, Confirm: Boolean\);\n'
                            r'begin\n(.*?)\nend;', code, re.S)
        self.assertIsNotNone(handler)
        self.assertRegex(handler.group(1), r'^(\s*//.*\n)*\s*if BootstrapperRunning then\s+Cancel := False;$')
        run = code[code.index('function RunBootstrapper'):code.index('function InstallWebView2Runtime')]
        launched, show = run.index('CreateProcessW('), run.index('WebView2Page.Show;')
        for line in ('WizardForm.CancelButton.Enabled := False;', 'BootstrapperRunning := True;'):
            self.assertTrue(launched < run.index(line) < show, line)
        # Restored in the same finally that hides the page, so every exit path re-enables Cancel.
        self.assertRegex(run, r'finally\s+BootstrapperRunning := False;\s+WizardForm\.CancelButton\.Enabled := '
                              r'CancelWasEnabled;\s+WebView2Page\.Hide;')
        self.assertEqual(code.count('BootstrapperRunning := True'), 1)


if __name__ == '__main__':
    unittest.main()
