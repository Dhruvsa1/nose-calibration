"""Build an Inno Setup installer from a verified Collector ZIP and pinned WebView2 bootstrapper (build machine only)."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

from verify_package import verify
import webview2_bootstrapper


def build(archive, expected, compiler=None, check_only=False, bootstrapper=webview2_bootstrapper.DEFAULT_PATH,
          signature_reader=webview2_bootstrapper.read_authenticode, pin_path=webview2_bootstrapper.PIN_PATH):
    if not re.fullmatch(r'[0-9a-fA-F]{64}', expected):
        raise ValueError('An independently verified ZIP SHA-256 is required')
    root = Path(__file__).resolve().parents[1]
    staging = root / 'work' / 'installer-staging'
    staging.mkdir(parents=True, exist_ok=True)
    pin = webview2_bootstrapper.load_pin(pin_path)
    # Verify and compile a private snapshot, not a source ZIP that can change
    # between verification and extraction. Never extract into an existing tree.
    with tempfile.TemporaryDirectory(prefix='build-', dir=staging) as tmp:
        snapshot = Path(tmp) / 'payload.zip'
        total = 0
        with open(archive, 'rb') as src, snapshot.open('xb') as dst:
            while chunk := src.read(1024 * 1024):
                total += len(chunk)
                if total > 750 * 1024 * 1024:
                    raise ValueError('ZIP exceeds installer build limit')
                dst.write(chunk)
        result = verify(snapshot, expected)
        if not result['guideIncluded']:
            raise ValueError('The participant guide must be included')
        # Setup bundles Microsoft's WebView2 bootstrapper for machines without the runtime.
        # Verify a private copy (pinned bytes + Microsoft Authenticode); ISCC rechecks its hash.
        prerequisite = Path(tmp) / 'prerequisite'
        prerequisite.mkdir()
        staged_bootstrapper = webview2_bootstrapper.snapshot(bootstrapper, prerequisite, pin)
        result['webview2Bootstrapper'] = webview2_bootstrapper.verify(staged_bootstrapper, pin, signature_reader)
        with zipfile.ZipFile(snapshot) as z:
            metadata_names = [n for n in z.namelist() if n.endswith('/package-source.json')]
            if len(metadata_names) != 1:
                raise ValueError('Expected one package source manifest')
            metadata = json.loads(z.read(metadata_names[0]))
            version = metadata['version']
            if not re.fullmatch(r'\d+\.\d+\.\d+', version):
                raise ValueError('Invalid installer version')
            if result['channel'] == 'preview':
                version += '-preview'
            result['installerVersion'] = version
            if check_only:
                return result | {'installerBuilt': False}
            compiler_path = Path(compiler or '').resolve()
            if not compiler_path.is_file() or compiler_path.name.lower() != 'iscc.exe':
                raise ValueError('Provide the installed Inno Setup ISCC.exe path')
            extracted = Path(tmp) / 'extracted'
            z.extractall(extracted)  # verifier has checked all names/links/limits
        payload = extracted / Path(metadata_names[0]).parent
        output = Path(tempfile.mkdtemp(prefix='setup-', dir=root / 'work'))
        subprocess.run([str(compiler_path), '/Qp', f'/DPayloadDir={payload}',
                        f'/DOutputDir={output}', f'/DPackageVersion={version}',
                        f'/DPayloadId={result["sha256"][:24]}',
                        f'/DWebView2Bootstrapper={staged_bootstrapper}',
                        f'/DWebView2BootstrapperSha256={pin["sha256"]}',
                        str(root / 'tools' / 'collector-setup.iss')], check=True)
        installers = list(output.glob('*.exe'))
        if len(installers) != 1:
            raise ValueError('Expected exactly one installer')
        installer = installers[0]
        digest = hashlib.sha256(installer.read_bytes()).hexdigest()
        installer.with_suffix('.exe.sha256').write_text(f'{digest}  {installer.name}\n', encoding='ascii')
        result |= {'installerBuilt': True, 'installer': str(installer), 'installerSha256': digest,
                   'signed': False, 'installationTested': False,
                   'webview2RuntimeHandling': 'Setup detects the Evergreen Runtime; if missing, it runs the bundled '
                                              'pinned Microsoft bootstrapper unelevated and continues only once detected',
                   'missingRuntimeInstallTested': False}
        (output / 'build-provenance.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--compiler', help='Explicit path to trusted Inno Setup ISCC.exe')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--webview2-bootstrapper', default=str(webview2_bootstrapper.DEFAULT_PATH),
                        help='Pinned Microsoft bootstrapper prepared by tools/webview2_bootstrapper.py fetch')
    args = parser.parse_args()
    print(json.dumps(build(args.archive, args.expected_sha256, args.compiler, args.check_only,
                           args.webview2_bootstrapper), indent=2))
