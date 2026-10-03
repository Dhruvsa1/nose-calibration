"""Pin and verify Microsoft's WebView2 Evergreen Bootstrapper as installer build input.

The bootstrapper is never executed on the build machine. This module hashes it and reads its
embedded Authenticode signature statically (Get-AuthenticodeSignature); Setup runs it only on
a participant machine that lacks the runtime. `fetch` downloads from the pinned official
Microsoft link and accepts only the exact pinned file: when Microsoft publishes a new
bootstrapper, `inspect` reports its facts and a reviewer must update the pin deliberately.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PIN_PATH = ROOT / 'docs' / 'webview2-bootstrapper.json'
DEFAULT_PATH = ROOT / 'vendor' / 'webview2' / 'MicrosoftEdgeWebview2Setup.exe'
FILE_NAME = 'MicrosoftEdgeWebview2Setup.exe'
OFFICIAL_LINK = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'
MICROSOFT_SUBJECT = 'CN=Microsoft Corporation, O=Microsoft Corporation, L=Redmond, S=Washington, C=US'
CODE_SIGNING_EKU = '1.3.6.1.5.5.7.3.3'
MAX_BYTES = 16 * 1024 * 1024
REPARSE_POINT = 0x400
THUMBPRINT = re.compile(r'[0-9A-F]{40}')
PIN_KEYS = {'schema', 'fileName', 'officialLink', 'allowedDownloadHosts', 'sha256', 'bytes', 'fileVersion',
            'signerSubject', 'signerThumbprint', 'issuerSubject', 'allowedRootThumbprints', 'retrievedUtc',
            'observedFinalUrl', 'observedLastModified', 'sources'}
SIGNATURE_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$path = $env:NOSE_WEBVIEW2_BOOTSTRAPPER
$s = Get-AuthenticodeSignature -LiteralPath $path
$c = $s.SignerCertificate
$chain = @(); $ekus = @(); $built = $false
if ($c) {
  $x = New-Object System.Security.Cryptography.X509Certificates.X509Chain
  $x.ChainPolicy.RevocationMode = 'NoCheck'
  $built = $x.Build($c)
  $chain = @($x.ChainElements | ForEach-Object { $_.Certificate.Thumbprint })
  $ekus = @($c.Extensions | Where-Object { $_.Oid.Value -eq '2.5.29.37' } | ForEach-Object { $_.EnhancedKeyUsages } | ForEach-Object { $_.Value })
}
[pscustomobject]@{
  status = [string]$s.Status; signatureType = [string]$s.SignatureType
  subject = $(if ($c) { $c.Subject } else { '' }); issuer = $(if ($c) { $c.Issuer } else { '' })
  thumbprint = $(if ($c) { $c.Thumbprint } else { '' }); chainBuilt = $built; chain = $chain; ekus = $ekus
  timeStamper = $(if ($s.TimeStamperCertificate) { $s.TimeStamperCertificate.Subject } else { '' })
  fileVersion = [string](Get-Item -LiteralPath $path).VersionInfo.FileVersion
} | ConvertTo-Json -Compress
'''


def load_pin(path=PIN_PATH):
    pin = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(pin, dict) or set(pin) != PIN_KEYS or pin['schema'] != 1:
        raise ValueError('WebView2 bootstrapper pin format mismatch')
    # The link and signer are fixed in reviewed code, not only data, so a pin edit alone
    # cannot redirect builds to another source or publisher.
    if pin['fileName'] != FILE_NAME or pin['officialLink'] != OFFICIAL_LINK:
        raise ValueError('WebView2 bootstrapper pin must name the official Microsoft bootstrapper link')
    hosts = pin['allowedDownloadHosts']
    if not isinstance(hosts, list) or 'go.microsoft.com' not in hosts or not all(
            isinstance(h, str) and re.fullmatch(r'([a-z0-9-]+\.)+microsoft\.com', h) for h in hosts):
        raise ValueError('WebView2 bootstrapper download hosts must be Microsoft domains')
    if not (isinstance(pin['sha256'], str) and re.fullmatch(r'[0-9a-f]{64}', pin['sha256'])):
        raise ValueError('WebView2 bootstrapper pin needs a lowercase SHA-256')
    if not (isinstance(pin['bytes'], int) and 0 < pin['bytes'] <= MAX_BYTES):
        raise ValueError('WebView2 bootstrapper pin size invalid')
    if pin['signerSubject'] != MICROSOFT_SUBJECT or not str(pin['issuerSubject']).endswith('O=Microsoft Corporation, C=US'):
        raise ValueError('WebView2 bootstrapper pin must name the Microsoft Corporation signer')
    roots = pin['allowedRootThumbprints']
    if not (isinstance(pin['signerThumbprint'], str) and THUMBPRINT.fullmatch(pin['signerThumbprint'])) or not (
            isinstance(roots, list) and roots and all(isinstance(r, str) and THUMBPRINT.fullmatch(r) for r in roots)):
        raise ValueError('WebView2 bootstrapper pin thumbprints invalid')
    return pin


def snapshot(source, directory, pin):
    """Copy a regular, non-link source file into a private build directory; return the copy."""
    source = Path(source)
    try:
        before = os.lstat(source)
    except FileNotFoundError:
        raise ValueError(f'WebView2 bootstrapper not found: {source}. Run tools/webview2_bootstrapper.py fetch') from None
    if stat.S_ISLNK(before.st_mode) or getattr(before, 'st_file_attributes', 0) & REPARSE_POINT \
            or not stat.S_ISREG(before.st_mode):
        raise ValueError('WebView2 bootstrapper must be a regular file, not a link or reparse point')
    if before.st_size > MAX_BYTES:
        raise ValueError('WebView2 bootstrapper exceeds size limit')
    target = Path(directory) / pin['fileName']
    with open(source, 'rb') as src:
        opened = os.fstat(src.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError('WebView2 bootstrapper changed while being opened')
        data = src.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('WebView2 bootstrapper exceeds size limit')
    with target.open('xb') as dst:
        dst.write(data)
    return target


def read_authenticode(path):
    """Read the embedded Authenticode signature without executing the file."""
    shell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    env = {k: v for k, v in os.environ.items() if k.upper() != 'PSMODULEPATH'}
    env['NOSE_WEBVIEW2_BOOTSTRAPPER'] = str(Path(path).resolve())
    result = subprocess.run([str(shell), '-NoProfile', '-NonInteractive', '-Command', SIGNATURE_SCRIPT],
                            capture_output=True, text=True, env=env, timeout=120)
    if result.returncode != 0:
        raise ValueError('Could not read WebView2 bootstrapper signature: ' + result.stderr.strip()[:300])
    return json.loads(result.stdout)


def verify(path, pin, reader=read_authenticode):
    """Require the exact pinned bytes and a valid Microsoft Authenticode signature."""
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('WebView2 bootstrapper exceeds size limit')
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != pin['bytes'] or digest != pin['sha256']:
        raise ValueError(f'WebView2 bootstrapper differs from the reviewed pin (sha256 {digest}, {len(data)} bytes)')
    if not data.startswith(b'MZ'):
        raise ValueError('WebView2 bootstrapper is not a Windows executable')
    sig = reader(path)
    chain = [str(t).upper() for t in sig.get('chain') or []]
    checks = [
        (sig.get('status') == 'Valid' and sig.get('signatureType') == 'Authenticode', 'Authenticode signature is not valid'),
        (sig.get('subject') == pin['signerSubject'] == MICROSOFT_SUBJECT, 'signer is not Microsoft Corporation'),
        (str(sig.get('thumbprint', '')).upper() == pin['signerThumbprint'], 'signer certificate differs from the pin'),
        (sig.get('issuer') == pin['issuerSubject'], 'issuing CA differs from the pin'),
        (sig.get('chainBuilt') is True and chain[:1] == [pin['signerThumbprint']]
         and chain[-1:] and chain[-1] in pin['allowedRootThumbprints'], 'certificate chain does not reach an allowed Microsoft root'),
        (CODE_SIGNING_EKU in (sig.get('ekus') or []), 'signer certificate lacks the code-signing usage'),
        (sig.get('fileVersion') == pin['fileVersion'], 'file version differs from the pin'),
    ]
    for ok, message in checks:
        if not ok:
            raise ValueError('WebView2 bootstrapper rejected: ' + message)
    return {'fileName': pin['fileName'], 'sha256': digest, 'bytes': len(data), 'fileVersion': sig['fileVersion'],
            'signatureStatus': sig['status'], 'signerSubject': sig['subject'], 'signerThumbprint': pin['signerThumbprint'],
            'issuerSubject': sig['issuer'], 'rootThumbprint': chain[-1], 'timeStamper': sig.get('timeStamper', ''),
            'officialLink': pin['officialLink'], 'pinRetrievedUtc': pin['retrievedUtc'], 'executedDuringBuild': False}


class _AllowlistedRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = set(hosts)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urllib.parse.urlsplit(newurl)
        if parts.scheme != 'https' or parts.hostname not in self.hosts:
            raise ValueError(f'Refusing WebView2 bootstrapper redirect to {parts.scheme}://{parts.hostname}')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(pin, directory, opener=None):
    """Download the official link into a new file in `directory`; only Microsoft HTTPS hops are followed."""
    opener = opener or urllib.request.build_opener(_AllowlistedRedirects(pin['allowedDownloadHosts']))
    target = Path(directory) / pin['fileName']
    with opener.open(pin['officialLink'], timeout=60) as response:
        final = urllib.parse.urlsplit(response.geturl())
        if final.scheme != 'https' or final.hostname not in pin['allowedDownloadHosts']:
            raise ValueError('WebView2 bootstrapper download ended outside the Microsoft allowlist')
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('WebView2 bootstrapper download exceeds size limit')
    with target.open('xb') as out:
        out.write(data)
    return target, response.geturl()


def fetch(pin, destination=DEFAULT_PATH, reader=read_authenticode, opener=None):
    """Download, accept only the pinned file, then place it at `destination` (ignored vendor/)."""
    scratch = ROOT / 'work' / 'dependencies'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='webview2-', dir=scratch) as tmp:
        downloaded, final_url = download(pin, tmp, opener)
        try:
            result = verify(downloaded, pin, reader)
        except ValueError as error:
            raise ValueError(f'{error}. Nothing was accepted. If Microsoft has published a new bootstrapper, '
                             'run inspect on it, review it, and update docs/webview2-bootstrapper.json deliberately.') from None
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise ValueError('Refusing to replace a link or non-file bootstrapper destination')
        staged = destination.with_name(destination.name + '.partial')
        staged.unlink(missing_ok=True)
        with staged.open('xb') as out:
            out.write(downloaded.read_bytes())
        os.replace(staged, destination)
    return result | {'finalUrl': final_url, 'destination': str(destination)}


def inspect(path, reader=read_authenticode):
    """Report facts for a reviewer refreshing the pin; accepts nothing."""
    data = Path(path).read_bytes()
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'signature': reader(path),
            'note': 'Inspection only. Compare with official Microsoft sources before editing the pin.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('fetch', help='download from the pinned Microsoft link into vendor/webview2 if it matches the pin')
    check = sub.add_parser('verify', help='verify a local bootstrapper against the pin')
    check.add_argument('path', nargs='?', default=str(DEFAULT_PATH))
    look = sub.add_parser('inspect', help='print hash and signature facts without accepting the file')
    look.add_argument('path')
    args = parser.parse_args()
    try:
        if args.command == 'fetch':
            output = fetch(load_pin())
        elif args.command == 'verify':
            with tempfile.TemporaryDirectory() as tmp:
                pin = load_pin()
                output = verify(snapshot(args.path, tmp, pin), pin)
        else:
            output = inspect(args.path)
        print(json.dumps(output, indent=2))
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(f'REJECTED: {error}', file=sys.stderr)
        sys.exit(1)
