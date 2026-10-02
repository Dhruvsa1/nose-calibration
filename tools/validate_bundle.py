"""Pure-data validation. Never extracts files, decodes images, or executes solutions."""
import collections, hashlib, io, json, math, re, statistics, struct, zipfile

MAX_ZIP = 30 * 1024 * 1024
KINDS = {'pointermove','pointerdown','pointerup','keydown','keyup','wheel','scroll','focus','selection','input','grade','question','screenshot'}

def object_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Duplicate JSON property')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON value')))
    if not isinstance(value, dict): raise ValueError('Expected JSON object')
    return value

def jpeg_dimensions(data):
    if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
        raise ValueError('Invalid JPEG signature')
    i = 2
    while i + 4 <= len(data):
        if data[i] != 255: raise ValueError('Invalid JPEG marker')
        while i < len(data) and data[i] == 255: i += 1
        if i >= len(data): break
        marker = data[i]; i += 1
        if marker in (0xD8, 0xD9): continue
        n = int.from_bytes(data[i:i+2], 'big')
        if n < 2 or i+n > len(data): raise ValueError('Invalid JPEG segment')
        if marker in (0xC0,0xC1,0xC2):
            if n < 8: raise ValueError('Invalid JPEG dimensions')
            h=int.from_bytes(data[i+3:i+5],'big'); w=int.from_bytes(data[i+5:i+7],'big')
            if not 1<=w<=8192 or not 1<=h<=8192 or w*h>40000000: raise ValueError('Image too large')
            return w,h
        i += n
    raise ValueError('JPEG dimensions not found')

def preflight_directory(raw):
    """Bound central-directory entry allocation before ZipFile creates objects.

    Collector archives are single-disk, non-ZIP64, without trailing signatures.
    Count actual headers too: trusting only the footer's declared count is unsafe.
    """
    end = raw.rfind(b'PK\x05\x06', max(0, len(raw) - 65557))
    if end < 0 or end + 22 > len(raw): raise ValueError('Invalid ZIP directory')
    # Python consults this locator before the 32-bit directory. It can be hidden
    # inside a central entry comment; reject it before ZipFile can allocate.
    if end >= 20 and raw[end - 20:end - 16] == b'PK\x06\x07':
        raise ValueError('ZIP64 is not supported')
    _, disk, start_disk, on_disk, count, size, offset, comment = struct.unpack_from('<4s4H2LH', raw, end)
    if disk or start_disk or on_disk != count or count > 125 or end + 22 + comment != len(raw) or offset + size != end:
        raise ValueError('Unsupported ZIP directory')
    position = offset
    actual = 0
    while position < end:
        actual += 1
        if actual > 125 or position + 46 > end or raw[position:position + 4] != b'PK\x01\x02':
            raise ValueError('Too many or invalid directory entries')
        name, extra, note = struct.unpack_from('<3H', raw, position + 28)
        position += 46 + name + extra + note
        if position > end: raise ValueError('Truncated directory entry')
    if actual != count: raise ValueError('Directory entry count mismatch')


def validate(raw, session_id):
    if len(raw)>MAX_ZIP: raise ValueError('Compressed bundle too large')
    preflight_directory(raw)
    metrics={}; flags=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        entries=z.infolist(); names=[i.filename for i in entries]
        if len(entries)>125 or len(set(n.lower() for n in names))!=len(names): raise ValueError('Too many or duplicate entries')
        if not {'manifest.json','events.jsonl','summary.json'}<=set(names): raise ValueError('Missing required files')
        total=0; files={}; images=[]
        for entry in entries:
            name=entry.filename
            if name not in {'manifest.json','summary.json','answers.json','events.jsonl'} and not re.fullmatch(r'click-\d{8}\.jpg',name): raise ValueError('Unexpected archive entry')
            if entry.is_dir() or (entry.external_attr>>16)&0o170000 == 0o120000 or entry.flag_bits&1: raise ValueError('Unsupported entry')
            if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED): raise ValueError('Unsupported compression method')
            limit=20*1024*1024 if name=='events.jsonl' else 5*1024*1024 if name.endswith('.jpg') else 200000
            if entry.file_size>limit or entry.file_size>max(1,entry.compress_size)*300: raise ValueError('Entry size/ratio limit')
            with z.open(entry) as f: data=f.read(limit+1)
            if len(data)>limit: raise ValueError('Expanded entry limit')
            total+=len(data)
            if total>100*1024*1024: raise ValueError('Expanded bundle limit')
            if name.endswith('.jpg'):
                w,h=jpeg_dimensions(data);images.append({'file':name,'width':w,'height':h,'sha256':hashlib.sha256(data).hexdigest()})
            else:files[name]=data
        manifest=object_json(files['manifest.json'])
        if manifest.get('schemaVersion')!=1 or manifest.get('sessionId')!=session_id or manifest.get('consent') is not True or manifest.get('mode') not in ('human','codex') or manifest.get('appVersion')!='0.1.0': raise ValueError('Invalid manifest')
        counts=collections.Counter();key_times=[];holds=[];down={};last=-1;last_id=0;regions=collections.Counter();screenshot_refs=set();corrections=0
        lines=files['events.jsonl'].splitlines()
        if len(lines)>250120: raise ValueError('Event count limit')
        for line in lines:
            if len(line)>16000: raise ValueError('Event line limit')
            e=object_json(line);kind=e.get('type')
            if kind not in KINDS: raise ValueError('Unknown event type')
            counts[kind]+=1
            if kind=='screenshot':
                name=e.get('file','')
                if name not in names or not re.fullmatch(r'click-\d{8}\.jpg',name): raise ValueError('Invalid screenshot reference')
                screenshot_refs.add(name);continue
            t=e.get('t');viewport=e.get('viewport',{})
            event_id=e.get('id')
            if type(event_id) is not int or not last_id<event_id<=250000: raise ValueError('Invalid or nonmonotonic event ID')
            last_id=event_id
            if not isinstance(viewport,dict): raise ValueError('Invalid viewport')
            if type(t) not in (int,float) or not math.isfinite(t) or not max(last,0)<=t<=1801000: raise ValueError('Nonmonotonic or invalid time')
            last=t
            if any(type(viewport.get(d)) not in (int,float) or not 1<=viewport[d]<=8192 for d in ('width','height')): raise ValueError('Invalid viewport')
            if kind.startswith('pointer') and any(type(e.get(d)) not in (int,float) or not math.isfinite(e[d]) or not -1<=e[d]<=viewport[v]+1 for d,v in [('x','width'),('y','height')]): raise ValueError('Invalid pointer coordinate')
            region=e.get('region','navigation')
            if region not in ('problem','answer-area','question-nav','test-output','navigation'):raise ValueError('Invalid region')
            regions[region]+=1
            if kind in ('keydown','keyup'):
                key=e.get('key','');code=e.get('code','')
                if not isinstance(key,str) or len(key)>40 or not isinstance(code,str) or len(code)>40: raise ValueError('Invalid key event')
                if 'repeat' in e and type(e['repeat']) is not bool: raise ValueError('Invalid repeat flag')
                if kind=='keydown':
                    key_times.append(t);corrections+=key in ('Backspace','Delete')
                    if not e.get('repeat'):down[code]=t
                elif code in down:
                    hold=t-down.pop(code)
                    if 0<=hold<10000:holds.append(hold)
        if len(screenshot_refs)!=len(images): flags.append('orphan_or_duplicate_screenshots')
        gaps=[b-a for a,b in zip(key_times,key_times[1:])]
        summary=object_json(files['summary.json'])
        if not isinstance(summary,dict):raise ValueError('Invalid summary')
        answers=object_json(files.get('answers.json',b'{}'))
        if not isinstance(answers,dict):raise ValueError('Invalid answers')
        # Values remain untrusted and are never executed. Scan likely accidental secrets.
        values=answers.get('values',[])
        if not isinstance(values,list) or len(values)>5 or any(not isinstance(s,str) or len(s)>30000 for s in values):raise ValueError('Invalid answer sizes')
        if re.search(r'(?:sk-(?:ant-|proj-)|gh[pousr]_|-----BEGIN .*PRIVATE KEY)', '\n'.join(values)):flags.append('possible_secret_in_answer')
        metrics={'schemaVersion':1,'sessionId':session_id,'mode':manifest['mode'],'events':dict(counts),'regions':dict(regions),'durationMs':max(last,0),'screenshotCount':len(images),'keyIntervalMedianMs':statistics.median(gaps) if gaps else None,'keyHoldMedianMs':statistics.median(holds) if holds else None,'pausesOver500Ms':sum(g>500 for g in gaps),'correctionKeys':corrections,'flags':flags,'provenance':'client-reported; not proof of human origin','bundleSha256':hashlib.sha256(raw).hexdigest()}
        if last>0 and len(lines)/(last/1000)>1500:flags.append('unusually_high_event_rate')
        return metrics
