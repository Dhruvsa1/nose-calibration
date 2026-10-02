import io
import json
import unittest
import zipfile
from validate_bundle import validate

SESSION='a'*32
class ValidatorTests(unittest.TestCase):
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

if __name__=='__main__':unittest.main()
