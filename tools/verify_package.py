"""Inspect a built ZIP without executing or extracting its contents.

This checks integrity and content policy. It cannot establish authenticity: a modified package
with a regenerated manifest passes too. Use --expected-sha256 with the checksum the organizer
published separately from the download.
"""
import argparse
import hashlib
import base64
import json
import re
import sys
import zipfile
from pathlib import PurePosixPath, Path

PRIVATE_NAME = re.compile(
    r'(^|/)(\.env[^/]*|hosts\.yml|auth\.json|events\.jsonl|answers\.json|manifest\.json|upload-state\.json'
    r'|summary\.json|receipt\.json|session\.json|record\.json|enrollment[^/]*\.json|intake[^/]*\.json'
    r'|numeric-(review|advisory)[^/]*\.json|[^/]*-cursor\.json|worker[^/]*\.json|[^/]*\.lock'
    r'|[^/]*\.dpapi|[^/]*\.nose|[^/]*\.enc|[^/]*\.zip|[^/]*\.7z|[^/]*private[^/]*\.pem|recipient[^/]*'
    r'|[^/]*\.(pfx|p12|key|ppk|snk)|id_(rsa|dsa|ecdsa|ed25519)[^/]*|click-\d+\.jpg'
    r'|[^/]*\.(py|pyc|pyw|cs|csproj|sln|ipynb)|[^/]*\.cs\.txt|[^/]*admin[^/]*|intake_worker[^/]*|numeric_review[^/]*'
    r'|[^/]*\.(bat|cmd|vbs|sh)|\.git[^/]*)$'
    r'|(^|/)(sessions|submissions|keys|\.git|vendor)/', re.I)
# Everything shipped must have one of these shapes; runtime assemblies are the only open-ended set.
EXACT_FILES = {'NoseCalibration.exe', 'createdump.exe', 'Install.ps1', 'START-HERE.txt', 'public-key.pem',
               'oauth-client.json', 'package-files.json', 'package-source.json', 'NoseCalibration.deps.json',
               'NoseCalibration.runtimeconfig.json', 'Nose-Calibration-Setup.pdf',
               'Microsoft.Web.WebView2.Core.xml', 'Microsoft.Web.WebView2.WinForms.xml'}
ALLOWED_SHAPE = re.compile(r'([^/]+/)*[^/]+\.dll|web/[A-Za-z0-9_-]+\.(html|css|js)|web/branding/[A-Za-z0-9_-]+\.png')
SECRET_PATTERNS = [
    (re.compile(rb'-----BEGIN [A-Z0-9 ]*PRIVATE KEY( BLOCK)?-----|PRIVATE KEY-----|PuTTY-User-Key-File-'), 'Private key marker in package'),
    (re.compile(rb'(?<![A-Za-z0-9_])(gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})'), 'Token literal in package'),
    (re.compile(rb'(?i)client_secret["\']?\s*[:=]\s*["\']?[A-Za-z0-9_\-]{16,}'), 'Client secret literal in package'),
]
SOURCE_KEYS = {'schema', 'product', 'channel', 'version', 'informationalVersion', 'sourceRevision', 'sourceTreeClean',
               'uncommittedPathCount', 'uncommittedPaths', 'uncommittedPathsTruncated', 'runtimeIdentifier',
               'selfContained', 'targetFramework', 'bundledRuntimeVersion', 'sdkVersion', 'builtAtUtc'}

def scan_secrets(name, data):
    # Strings in .NET assemblies are UTF-16LE; take both byte alignments as ASCII views.
    for view in (data, data[0::2], data[1::2]):
        for pattern, message in SECRET_PATTERNS:
            if pattern.search(view):
                raise ValueError(f'{message}: {name}')

def check_source(files, pin):
    raw = files['package-source.json']
    if len(raw) > 16*1024:
        raise ValueError('Source manifest too large')
    source = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(source, dict) or set(source) != SOURCE_KEYS or source['schema'] != 1 or source['product'] != 'NoseCalibration':
        raise ValueError('Source manifest format mismatch')
    revision, version, channel = source['sourceRevision'], source['version'], source['channel']
    if not (isinstance(revision, str) and re.fullmatch(r'[0-9a-f]{40}', revision)):
        raise ValueError('Source revision missing')
    if not (isinstance(version, str) and re.fullmatch(r'\d+\.\d+\.\d+', version)) or channel not in ('preview', 'release'):
        raise ValueError('Source version or channel invalid')
    clean, count, paths = source['sourceTreeClean'], source['uncommittedPathCount'], source['uncommittedPaths']
    if not isinstance(clean, bool) or not isinstance(count, int) or not isinstance(paths, list) or len(paths) > 50 \
            or clean != (count == 0) or len(paths) > count or not all(isinstance(p, str) and len(p) <= 200 for p in paths):
        raise ValueError('Source tree state invalid')
    if channel == 'release' and not clean:
        raise ValueError('Release package built from uncommitted source')
    expected = version + ('-preview' if channel == 'preview' else '') + '+' + revision + ('' if clean else '.dirty')
    if source['informationalVersion'] != expected:
        raise ValueError('Informational version does not match source identity')
    if source['runtimeIdentifier'] != 'win-x64' or source['selfContained'] is not True:
        raise ValueError('Unexpected runtime identity')
    runtime = json.loads(files['NoseCalibration.runtimeconfig.json'].decode('utf-8-sig'))
    bundled = {f.get('name'): f.get('version') for f in runtime['runtimeOptions'].get('includedFrameworks', [])}
    if bundled.get('Microsoft.NETCore.App') != source['bundledRuntimeVersion']:
        raise ValueError('Bundled runtime version does not match source manifest')
    def runtime_version(value):
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', value):
            raise ValueError('Invalid bundled runtime version')
        return tuple(map(int, value.split('.')))
    minimum = runtime_version(pin['minimumBundledRuntime'])
    for framework in ('Microsoft.NETCore.App', 'Microsoft.WindowsDesktop.App'):
        actual = runtime_version(bundled.get(framework))
        if actual[:2] != minimum[:2] or actual < minimum:
            raise ValueError('Bundled runtime below reviewed minimum or outside reviewed release family')
    # The SDK writes the informational version into the assembly as UTF-8 and UTF-16 (version resource).
    if expected.encode() not in files['NoseCalibration.dll'] or expected.encode('utf-16-le') not in files['NoseCalibration.dll']:
        raise ValueError('Assembly version does not match source manifest')
    return source

def verify(path, expected_sha256=None):
    if Path(path).stat().st_size > 400*1024*1024:
        raise ValueError('Package archive too large')
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist()) > 1500 or sum(i.file_size for i in archive.infolist()) > 700*1024*1024:
            raise ValueError('Package expanded size or entry count exceeded')
        names = archive.namelist()
        if len(names) != len(set(n.casefold() for n in names)):
            raise ValueError('Duplicate package entries')
        files = {}
        for item in archive.infolist():
            name = item.filename.replace('\\', '/')
            parts = PurePosixPath(name).parts
            if not parts or parts[0] != 'NoseCalibration' or '..' in parts or ':' in name:
                raise ValueError('Unexpected package path')
            if item.is_dir():
                continue
            if item.file_size > 150*1024*1024:
                raise ValueError('Unexpected package entry size')
            short = '/'.join(parts[1:])
            if PRIVATE_NAME.search(short):
                raise ValueError(f'Private file in package: {short}')
            if short not in EXACT_FILES and not ALLOWED_SHAPE.fullmatch(short):
                raise ValueError(f'Unexpected file in package: {short}')
            with archive.open(item) as stream:
                data = stream.read(min(item.file_size,150*1024*1024)+1)
            if len(data) != item.file_size:
                raise ValueError('Package entry size mismatch')
            files[short] = data
        required = {'NoseCalibration.exe','NoseCalibration.dll','public-key.pem','web/index.html','web/style.css','web/questions.js','web/grader.js','web/app.js','web/ui.js','START-HERE.txt','Install.ps1','package-files.json','package-source.json','NoseCalibration.runtimeconfig.json'}
        if not required <= files.keys():
            raise ValueError('Missing required application files')
        branding = {'web/branding/'+name+'.png' for name in ('icon-light','icon-dark','wordmark-light','wordmark-dark')}
        if not branding <= files.keys():
            raise ValueError('Missing brand artwork')
        manifest = json.loads(files['package-files.json'].decode('utf-8-sig'))
        if len(manifest) != len(files)-1 or {v['path'] for v in manifest} != files.keys()-{'package-files.json'}:
            raise ValueError('Package manifest coverage mismatch')
        for entry in manifest:
            data = files[entry['path']]
            if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise ValueError('Package digest mismatch')
        pin = json.loads((Path(__file__).resolve().parents[1]/'docs/security-pins.json').read_text())
        if json.loads(files.get('oauth-client.json', b'{}').decode('utf-8-sig')) != {'clientId': pin['githubAppClientId'], 'appId': pin['githubAppId'], 'slug': pin['githubAppSlug']}:
            raise ValueError('GitHub App registration pin mismatch')
        key = files['public-key.pem']
        if not key.startswith(b'-----BEGIN PUBLIC KEY-----') or b'PRIVATE' in key:
            raise ValueError('Invalid public recipient key')
        der = base64.b64decode(re.sub(rb'-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----|\s',b'',key),validate=True)
        if hashlib.sha256(der).hexdigest() != pin['recipientSpkiSha256']:
            raise ValueError('Recipient public key pin mismatch')
        for name, data in files.items():
            scan_secrets(name, data)
        source = check_source(files, pin)
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256.strip().lower():
        raise ValueError('ZIP SHA-256 differs from the expected published value')
    return {'fileCount':len(files), 'guideIncluded':'Nose-Calibration-Setup.pdf' in files, 'sha256':digest,
            'channel':source['channel'], 'informationalVersion':source['informationalVersion'],
            'sourceRevision':source['sourceRevision'], 'sourceTreeClean':source['sourceTreeClean'],
            'bundledRuntimeVersion':source['bundledRuntimeVersion'],
            'expectedSha256Matched':expected_sha256 is not None,
            'note':'Integrity and content-policy check only; authenticity requires the separately published checksum.'}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('zip')
    parser.add_argument('--expected-sha256', help='checksum published by the organizer through a separate channel')
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.zip, args.expected_sha256), indent=2))
    except (ValueError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        print(f'REJECTED: {error}', file=sys.stderr)
        sys.exit(1)
