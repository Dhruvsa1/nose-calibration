"""Synthetic package fixtures for verify_package; nothing here is executed or extracted."""
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from verify_package import verify

ROOT = Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT/'docs/security-pins.json').read_text())
REV = 'c3b62f6d0422a9e13a2094121b4c8a4155ee8d94'
SYNTHETIC_TOKEN = 'ghp_' + 'A1b2C3d4E5'*4

def source(**changes):
    s = {'schema': 1, 'product': 'NoseCalibration', 'channel': 'preview', 'version': '0.1.0',
         'informationalVersion': f'0.1.0-preview+{REV}', 'sourceRevision': REV, 'sourceTreeClean': True,
         'uncommittedPathCount': 0, 'uncommittedPaths': [], 'uncommittedPathsTruncated': False,
         'runtimeIdentifier': 'win-x64', 'selfContained': True, 'targetFramework': 'net8.0-windows',
         'bundledRuntimeVersion': '8.0.31', 'sdkVersion': '8.0.425', 'builtAtUtc': '2026-10-02T00:00:00Z'}
    s.update(changes)
    return s

def files(overrides=None, version=f'0.1.0-preview+{REV}'):
    info = version
    f = {
        'NoseCalibration.exe': b'MZ synthetic host',
        'NoseCalibration.dll': b'MZ synthetic ' + info.encode() + b'\0' + info.encode('utf-16-le'),
        'NoseCalibration.runtimeconfig.json': json.dumps({'runtimeOptions': {'includedFrameworks': [
            {'name': 'Microsoft.NETCore.App', 'version': '8.0.31'},
            {'name': 'Microsoft.WindowsDesktop.App', 'version': '8.0.31'}]}}).encode(),
        'System.Security.Cryptography.dll': 'PRIVATE KEY\0-----BEGIN \0'.encode('utf-16-le'),
        'public-key.pem': (ROOT/'public-key.pem').read_bytes(),
        'oauth-client.json': json.dumps({'clientId': PIN['githubAppClientId'], 'appId': PIN['githubAppId'], 'slug': PIN['githubAppSlug']}).encode(),
        'START-HERE.txt': b'Compare the published SHA-256.',
        'Install.ps1': b'# synthetic',
        'package-source.json': json.dumps(source()).encode(),
    }
    for name in ('index.html', 'style.css', 'app.js', 'questions.js', 'grader.js', 'ui.js'):
        f['web/'+name] = b'synthetic'
    for name in ('icon-light', 'icon-dark', 'wordmark-light', 'wordmark-dark'):
        f[f'web/branding/{name}.png'] = b'\x89PNG'
    for name, data in (overrides or {}).items():
        if data is None: f.pop(name, None)
        else: f[name] = data
    return f

def build(f, manifest=None):
    if manifest is None:
        manifest = [{'path': p, 'sha256': hashlib.sha256(d).hexdigest(), 'bytes': len(d)} for p, d in f.items()]
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        for p, d in f.items(): z.writestr('NoseCalibration/'+p, d)
        z.writestr('NoseCalibration/package-files.json', json.dumps(manifest))
    return out.getvalue()

class VerifyPackageTests(unittest.TestCase):
    def check(self, f, expected_sha256=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'package.zip'
            path.write_bytes(build(f))
            return verify(path, expected_sha256)

    def reject(self, f, message):
        with self.assertRaisesRegex(ValueError, message):
            self.check(f)

    def test_valid_package_with_public_key_certificate_and_runtime_strings(self):
        f = files()
        f['Microsoft.Web.WebView2.Core.xml'] = b'-----BEGIN CERTIFICATE-----\n-----BEGIN PUBLIC KEY-----'
        f['cs/Microsoft.VisualBasic.Forms.resources.dll'] = 'client_secret\0ghp_\0github_pat_'.encode('utf-16-le')
        result = self.check(f)
        self.assertEqual((result['channel'], result['sourceRevision'], result['sourceTreeClean']), ('preview', REV, True))
        self.assertFalse(result['expectedSha256Matched'])

    def test_private_key_markers_in_any_encoding(self):
        for marker in ('-----BEGIN EC PRIVATE KEY-----', '-----BEGIN ENCRYPTED PRIVATE KEY-----',
                       '-----BEGIN OPENSSH PRIVATE KEY-----', '-----BEGIN PRIVATE KEY-----', 'PuTTY-User-Key-File-3'):
            for data in (marker.encode(), b'\0' + marker.encode('utf-16-le'), marker.encode('utf-16-le')):
                with self.subTest(marker=marker, size=len(data)):
                    self.reject(files({'web/app.js': data}), 'Private key marker')

    def test_runtime_pin_covers_core_and_desktop(self):
        for name in ('Microsoft.NETCore.App', 'Microsoft.WindowsDesktop.App'):
            for version in ('8.0.22', '8.0.31-preview', '9.0.1', None):
                f=files();runtime=json.loads(f['NoseCalibration.runtimeconfig.json'])
                for entry in runtime['runtimeOptions']['includedFrameworks']:
                    if entry['name']==name:entry['version']=version
                if name=='Microsoft.NETCore.App':f['package-source.json']=json.dumps(source(bundledRuntimeVersion=version)).encode()
                f['NoseCalibration.runtimeconfig.json']=json.dumps(runtime).encode()
                with self.subTest(framework=name,version=version):
                    self.reject(f,'[Bb]undled runtime')

    def test_token_and_secret_literals(self):
        for data in (SYNTHETIC_TOKEN.encode(), SYNTHETIC_TOKEN.encode('utf-16-le'),
                     b'github_pat_' + b'A1_b2'*14, b'"client_secret": "abcdefghijklmnop1234"'):
            with self.subTest(data=data[:12]):
                self.assertRaisesRegex(ValueError, 'literal', self.check, files({'NoseCalibration.dll': files()['NoseCalibration.dll'] + b'\0\0' + data}))

    def test_private_admin_state_and_archives(self):
        for name in ('admin_ingest.py', 'intake_worker.py', 'web/numeric_review.js', 'enrollment.json', 'intake.v1.json',
                     'collect-cursor.json', 'worker.lock', 'a'*32 + '.zip', 'submission.nose', 'sessions/x/events.jsonl',
                     'submissions/x/submission.nose', 'recipient.private.pem', 'keys/key.dpapi', 'helper.cmd',
                     'NoseCalibration.Admin.dll', 'tools/UploadHarness.cs.txt', 'vendor/gh.exe', '.env.local', 'id_ed25519'):
            with self.subTest(name=name):
                self.reject(files({name: b'x'}), 'Private file')

    def test_unexpected_files_outside_allowlist(self):
        for name in ('extra.ps1', 'helper.exe', 'notes.txt', 'web/extra.svg', 'web/sub/app.js', 'other.json', 'cert.pem'):
            with self.subTest(name=name):
                self.reject(files({name: b'x'}), 'Unexpected file')

    def test_source_manifest_required_and_consistent(self):
        self.reject(files({'package-source.json': None}), 'Missing required')
        bad = {
            'Source revision missing': source(sourceRevision='unknown'),
            'Release package built from uncommitted': source(channel='release', sourceTreeClean=False, uncommittedPathCount=1,
                                                              uncommittedPaths=['x'], informationalVersion=f'0.1.0+{REV}.dirty'),
            'tree state invalid': source(sourceTreeClean=True, uncommittedPathCount=2),
            'Informational version': source(informationalVersion=f'0.1.0+{REV}'),
            'Bundled runtime': source(bundledRuntimeVersion='8.0.1'),
            'format mismatch': {**source(), 'extra': 1},
        }
        for message, s in bad.items():
            with self.subTest(message=message):
                self.reject(files({'package-source.json': json.dumps(s).encode()}), message)
        self.reject(files(version=f'0.1.0-preview+{"0"*40}'), 'Assembly version')

    def test_dirty_preview_is_accepted_and_reported(self):
        info = f'0.1.0-preview+{REV}.dirty'
        s = source(informationalVersion=info, sourceTreeClean=False, uncommittedPathCount=1, uncommittedPaths=['tools/package.ps1'])
        result = self.check(files({'package-source.json': json.dumps(s).encode()}, version=info))
        self.assertFalse(result['sourceTreeClean'])

    def test_expected_checksum(self):
        raw = build(files())
        digest = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'package.zip'
            path.write_bytes(raw)
            self.assertTrue(verify(path, digest.upper())['expectedSha256Matched'])
            with self.assertRaisesRegex(ValueError, 'differs from the expected'):
                verify(path, '0'*64)

    def test_manifest_listing_extra_tool_still_fails_allowlist(self):
        # Fable N1/P1 fixture: a self-consistent manifest must not make extra executables acceptable.
        self.reject(files({'extra.ps1': b'x', 'helper.exe': b'MZ'}), 'Unexpected file')

    def test_webview2_bootstrapper_never_ships_in_package(self):
        # Setup bundles it from the separately pinned build input; the ZIP payload must not carry it.
        for name in ('MicrosoftEdgeWebview2Setup.exe', 'prerequisites/MicrosoftEdgeWebview2Setup.exe'):
            with self.subTest(name=name):
                self.reject(files({name: b'MZ'}), 'Unexpected file')

if __name__ == '__main__':
    unittest.main()
