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
    def bundle(self, events, manifest=None, answers=None):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            z.writestr('manifest.json', manifest or json.dumps(dict(schemaVersion=1,sessionId=SESSION,consent=True,mode='human',appVersion='0.1.0')))
            z.writestr('summary.json','{}')
            z.writestr('events.jsonl','\n'.join(json.dumps(e) if isinstance(e,dict) else e for e in events))
            if answers is not None: z.writestr('answers.json', answers if isinstance(answers,str) else json.dumps(answers))
        return out.getvalue()
    # Test selection: exact known tuples; schemaVersion 1 maps to the original test without reinterpretation.
    TUPLES={'practice-js-5':(1,5),'practice-js-13':(1,13)}
    def manifest(self, schema=2, **fields):
        return json.dumps(dict(schemaVersion=schema,sessionId=SESSION,consent=True,mode='human',appVersion='0.1.0',**fields))
    def answers(self, test_id, version, count, values=None, score=None, total=None, grades=None):
        values=['']*count if values is None else values
        grades={str(i):dict(passed=True,message='ok') for i in range(count)} if grades is None else grades
        return dict(testId=test_id,testVersion=version,questionCount=count,values=values,grades=grades,score=count if score is None else score,total=count if total is None else total,grading='client-reported')
    def test_legacy_recording_maps_to_original_test(self):
        legacy_answers=dict(values=['12','5','do...while','a','b'],grades={'0':dict(passed=True)},score=1,total=5)
        for answers in (None, legacy_answers, dict(values=[])):
            with self.subTest(answers=answers):
                metrics=validate(self.bundle([],answers=answers),SESSION)
                self.assertEqual(metrics['assessment'],dict(testId='practice-js-5',testVersion=1,questionCount=5,source='legacy-manifest-v1'))
        for bad in (dict(values=['']*6), legacy_answers|dict(total=13), legacy_answers|dict(score=6), legacy_answers|dict(grades={'5':{}}),
                    self.answers('practice-js-13',1,13), self.answers('practice-js-5',2,5)):
            with self.subTest(bad=bad),self.assertRaises(ValueError): validate(self.bundle([],answers=bad),SESSION)
        # A legacy manifest naming a test is not a legacy recording.
        for fields in (dict(testId='practice-js-5'),dict(testId='practice-js-5',testVersion=1,questionCount=5),dict(questionCount=5)):
            with self.subTest(fields=fields),self.assertRaises(ValueError): validate(self.bundle([],self.manifest(1,**fields)),SESSION)
    def test_known_tuples_accepted(self):
        for test_id,(version,count) in self.TUPLES.items():
            with self.subTest(test_id=test_id):
                m=self.manifest(testId=test_id,testVersion=version,questionCount=count)
                metrics=validate(self.bundle([],m,self.answers(test_id,version,count)),SESSION)
                self.assertEqual(metrics['assessment'],dict(testId=test_id,testVersion=version,questionCount=count,source='manifest-v2'))
                self.assertEqual(validate(self.bundle([],m),SESSION)['assessment']['questionCount'],count)
    def test_wrong_or_unknown_manifest_tuple_rejected(self):
        for fields in (dict(testId='practice-js-13',testVersion=1,questionCount=5),dict(testId='practice-js-5',testVersion=1,questionCount=13),
                       dict(testId='practice-js-13',testVersion=2,questionCount=13),dict(testId='practice-js-6',testVersion=1,questionCount=6),
                       dict(testId='practice-js-13',testVersion=True,questionCount=13),dict(testId='practice-js-13',testVersion=1,questionCount='13'),
                       dict(testId='practice-js-13',testVersion=1.0,questionCount=13),dict(testId='practice-js-13',testVersion=1),dict()):
            with self.subTest(fields=fields),self.assertRaises(ValueError): validate(self.bundle([],self.manifest(**fields)),SESSION)
        for schema in (0,3,'2',True):
            with self.subTest(schema=schema),self.assertRaises(ValueError):
                validate(self.bundle([],self.manifest(schema,testId='practice-js-13',testVersion=1,questionCount=13)),SESSION)
    def test_answers_must_match_recording_tuple(self):
        m=self.manifest(testId='practice-js-13',testVersion=1,questionCount=13)
        good=self.answers('practice-js-13',1,13)
        unnamed={k:v for k,v in good.items() if k not in ('testId','testVersion','questionCount')}
        for bad in (self.answers('practice-js-5',1,5), good|dict(testVersion=2), good|dict(questionCount=5), unnamed,
                    good|dict(values=['']*12), good|dict(values=['']*14), good|dict(total=5), good|dict(score=14), good|dict(score=-1),
                    good|dict(grades={'13':{}}), good|dict(grades={'01':{}}), good|dict(grades=[])):
            with self.subTest(bad={k:bad[k] for k in bad if k!='values'}),self.assertRaises(ValueError): validate(self.bundle([],m,bad),SESSION)
        five=self.manifest(testId='practice-js-5',testVersion=1,questionCount=5)
        self.assertEqual(validate(self.bundle([],five,self.answers('practice-js-5',1,5)),SESSION)['assessment']['testId'],'practice-js-5')
        with self.assertRaises(ValueError): validate(self.bundle([],five,good),SESSION)
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
