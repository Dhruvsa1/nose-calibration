import io
import json
import struct
import unittest
from unittest.mock import patch
import zipfile
from validate_bundle import validate

SESSION='a'*32
class ValidatorTests(unittest.TestCase):
    def test_embedded_zip64_cannot_override_preflight_directory(self):
        # The visible directory declares one entry. Its comment contains a ZIP64
        # record directing Python to 127 entries, including 126 hidden headers.
        header = b'PK\x01\x02' + bytes(42)
        hidden = header * 126
        visible = bytearray(header)
        struct.pack_into('<H', visible, 32, 76)
        full_size = len(hidden) + len(visible)
        zip64 = struct.pack('<4sQ2H2L4Q', b'PK\x06\x06', 44, 45, 45,
                            0, 0, 127, 127, full_size, 0)
        locator = struct.pack('<4sLQL', b'PK\x06\x07', 0,
                              len(hidden) + len(visible), 1)
        footer = struct.pack('<4s4H2LH', b'PK\x05\x06', 0, 0, 1, 1,
                             len(visible) + 76, len(hidden), 0)
        raw = hidden + visible + zip64 + locator + footer
        # Establish the parser mismatch with a small bounded fixture.
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertEqual(len(archive.infolist()), 127)
        with patch('validate_bundle.zipfile.ZipFile',
                   side_effect=AssertionError('ZipFile allocation reached')):
            with self.assertRaisesRegex(ValueError, 'ZIP64'):
                validate(raw, SESSION)

    def test_central_directory_bound_before_zipfile(self):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            for i in range(126): z.writestr(str(i),'')
        raw=bytearray(out.getvalue())
        end=raw.rfind(b'PK\x05\x06')
        for declared in (126,3):
            struct.pack_into('<HH',raw,end+8,declared,declared)
            with self.subTest(declared=declared),patch('validate_bundle.zipfile.ZipFile',side_effect=AssertionError('ZipFile allocation reached')):
                with self.assertRaises(ValueError): validate(bytes(raw),SESSION)

    def test_directory_offsets_and_truncation(self):
        raw=self.bundle([])
        for changed in (raw[:-1],raw+b'trailing data',raw.replace(b'PK\x01\x02',b'NOPE',1)):
            with self.assertRaises(ValueError):validate(changed,SESSION)
    def bundle(self, events, manifest=None):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            z.writestr('manifest.json', manifest or json.dumps(dict(schemaVersion=1,sessionId=SESSION,consent=True,mode='human',appVersion='0.1.0')))
            z.writestr('summary.json','{}')
            z.writestr('events.jsonl','\n'.join(json.dumps(e) if isinstance(e,dict) else e for e in events))
        return out.getvalue()
    def event(self, **kwargs):
        return dict(id=1,t=1,type='keydown',key='a',code='KeyA',repeat=False,viewport=dict(width=100,height=100),**kwargs)
    def test_valid_key_pairs(self):
        down=self.event()
        up=down|dict(id=2,t=129,type='keyup')
        self.assertEqual(validate(self.bundle([down,up]),SESSION)['keyHoldMedianMs'],128)
    def test_id_order_and_types(self):
        for value in [True,1.5,0,250001,'1']:
            with self.subTest(value=value),self.assertRaises(ValueError):
                validate(self.bundle([self.event()|dict(id=value)]),SESSION)
        with self.assertRaises(ValueError): validate(self.bundle([self.event(),self.event()]),SESSION)
    def test_ambiguous_json(self):
        for value in ['[]','null','{"type":"keydown","type":"keyup"}','{"t":NaN}']:
            with self.subTest(value=value),self.assertRaises(ValueError): validate(self.bundle([value]),SESSION)
    def test_viewport_repeat_and_time(self):
        for change in [dict(viewport=[]),dict(repeat='false'),dict(t=float('inf')),dict(t=-1)]:
            with self.subTest(change=change),self.assertRaises(ValueError): validate(self.bundle([self.event()|change]),SESSION)
    def test_verification_not_participant(self):
        m=json.dumps(dict(schemaVersion=1,sessionId=SESSION,consent=True,mode='verification',appVersion='0.1.0'))
        with self.assertRaises(ValueError):validate(self.bundle([],m),SESSION)
    def test_unsupported_archive_compression(self):
        for method in (zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w',compression=method) as z:
                z.writestr('manifest.json',json.dumps(dict(schemaVersion=1,sessionId=SESSION,consent=True,mode='human',appVersion='0.1.0')))
                z.writestr('summary.json','{}');z.writestr('events.jsonl','')
            with self.assertRaises(ValueError):validate(out.getvalue(),SESSION)

if __name__=='__main__':unittest.main()
