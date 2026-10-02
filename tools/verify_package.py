"""Inspect a built ZIP without executing or extracting its contents."""
import hashlib
import base64
import json
import re
import sys
import zipfile
from pathlib import PurePosixPath, Path

def verify(path):
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
            if re.search(r'(^|/)(\.env[^/]*|hosts\.yml|auth\.json|events\.jsonl|answers\.json|manifest\.json|upload-state\.json|summary\.json|receipt\.json|.*\.dpapi|.*\.nose|.*private\.pem|click-\d+\.jpg)$', short, re.I):
                raise ValueError('Private file in package')
            with archive.open(item) as stream:
                data = stream.read(min(item.file_size,150*1024*1024)+1)
            if len(data) != item.file_size:
                raise ValueError('Package entry size mismatch')
            files[short] = data
        required = {'NoseCalibration.exe','NoseCalibration.dll','public-key.pem','web/index.html','web/style.css','web/questions.js','web/grader.js','web/app.js','web/ui.js','START-HERE.txt','Install.ps1','package-files.json'}
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
        if json.loads(files.get('oauth-client.json', b'{}').decode('utf-8-sig')) != {'clientId': pin['oauthClientId']}:
            raise ValueError('OAuth application identifier pin mismatch')
        if any(name.startswith('vendor/') for name in files):
            raise ValueError('Collector must not include a bundled authentication CLI')
        key = files['public-key.pem']
        if not key.startswith(b'-----BEGIN PUBLIC KEY-----') or b'PRIVATE' in key:
            raise ValueError('Invalid public recipient key')
        der = base64.b64decode(re.sub(rb'-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----|\s',b'',key),validate=True)
        if hashlib.sha256(der).hexdigest() != pin['recipientSpkiSha256']:
            raise ValueError('Recipient public key pin mismatch')
        if any(b'-----BEGIN PRIVATE KEY-----' in data or b'-----BEGIN RSA PRIVATE KEY-----' in data for data in files.values()):
            raise ValueError('Private key marker in package')
        return {'fileCount':len(files), 'guideIncluded':'Nose-Calibration-Setup.pdf' in files, 'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}

if __name__ == '__main__':
    print(json.dumps(verify(sys.argv[1]), indent=2))
