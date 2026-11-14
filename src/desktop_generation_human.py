"""Locate the human NON_PLAYER body without exporting avatar/history payloads.

Candidates are bounded by the exact closing person identity and must still pass
the original native NON_PLAYER reader before use in a match.
"""
import hashlib
import json
import struct
from pathlib import Path


def locate(data,header,selector,native_uid):
    ceiling=min(len(data),header+64*1024**2)
    closing=struct.pack('<IIIB',selector,native_uid,native_uid,8)
    end=data.find(closing,header+13,ceiling)
    if end<0 or data.find(closing,end+1,ceiling)>=0:
        raise ValueError('Human closing person identity is not unique within bound: '+str((header,selector,native_uid,end)))
    candidates=[]
    for tag in range(max(header+34,end-4096),end-53):
        if data[tag]!=12:continue
        profile=bytes(data[tag+1:tag+53]);codes=bytes(data[tag-8:tag])
        reps=struct.unpack_from('<5H',data,tag-19)
        if max(profile)>100 or not any(profile)or max(codes)>32 or max(reps[:3])>10000 or max(reps[3:])>200:continue
        for count in range(65):
            start=tag-21-7*count
            if start<header+13 or struct.unpack_from('<H',data,start)[0]!=count:continue
            candidates.append({'body_offset':start,'closing_person_offset':end,
                'raw_52_bytes_hex':profile.hex(),'formation_codes_hex':codes.hex(),
                'ability_and_reputation_words':list(reps),'entry_count':count,
                'profile_offset':tag+1,'ability_offset':tag-13,'native_marshalling_verified':False})
    if len(candidates)>1:
        # FM27 writes each seven-byte entry as a one-byte marker followed by
        # two three-byte values. Check their observed tags before accepting a
        # count that could also occur inside the preceding human history.
        candidates=[row for row in candidates if all(
            data[offset:offset+2]==b'\x01\x05' and data[offset+4]==5
            for offset in range(row['body_offset']+2,row['ability_offset']-6,7))]
    if len(candidates)!=1:raise ValueError('Human NON_PLAYER body not unique: '+str(len(candidates)))
    return candidates[0]


def export(folder):
    import desktop_save_compat
    desktop_save_compat.install()
    import fmsave
    import fmsave.readers.staff as reader
    from fmsave import _version
    from desktop_storage import bounded_output
    _version.FM27_FRAME_DECOMPRESSED_CAP=768*1024**2
    _version.FM27_TOTAL_DECOMPRESSED_CAP=1536*1024**2
    folder=Path(folder);bounded_output(folder)
    d=json.loads((folder/'generation_inputs.json').read_text(encoding='utf8'))
    source=Path(d['source']);before=source.stat()
    with source.open('rb')as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    if digest!=d['source_sha256']:raise ValueError('Source save changed')
    original=reader._PersonObject;humans=[]
    def capture(*a,**kw):
        obj=original(*a,**kw)
        if obj.is_human_manager:humans.append(obj)
        return obj
    reader._PersonObject=capture
    try:
        with fmsave.open(source)as save:
            with save._context.section('game_db')as db:
                list(save.staff())
                if len(humans)!=1:raise ValueError('Select a single source human manager')
                human=humans[0];selector=struct.unpack_from('<I',db,human.header)[0]+1
                profile=locate(db,human.header,selector,human.unique_id)
                start=profile['body_offset'];raw=bytes(db[start:profile['closing_person_offset']])
    finally:reader._PersonObject=original
    after=source.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Source changed during read')
    # The fragment contains less than 4 KiB, never the multi-megabyte avatar.
    out=folder/'human_staff_fragments';out.mkdir(exist_ok=True)
    (out/f'{selector}.bin').write_bytes(raw)
    row={'person_selector':selector,'uid':human.unique_id,'start':start,
         'raw_sha256':hashlib.sha256(raw).hexdigest(),'profile_hex':profile['raw_52_bytes_hex'],
         'codes_hex':profile['formation_codes_hex'],'ability_and_reputation_words':profile['ability_and_reputation_words'],
         'profile_offset_in_fragment':profile['profile_offset']-start,
         'ability_offset_in_fragment':profile['ability_offset']-start,'body_end_bound':profile['closing_person_offset']}
    (folder/'human_staff_fragments.json').write_text(json.dumps({'source_sha256':digest,'rows':[row]},indent=2),encoding='utf8')
    return {'source_sha256':digest,'selector':selector,'native_uid':human.unique_id,'fragment_bytes':len(raw),'profile':profile}


if __name__=='__main__':
    import sys
    print(json.dumps(export(sys.argv[1]),ensure_ascii=False),flush=True)
