"""Bounded source-generation extension to a desktop scenario, with no paths."""
import struct

PROFILE='controlled-fresh-duel-v1'
MAX_FORMATION_CODE = 69


def normalize(value,teams):
    if not isinstance(value,dict)or value.get('profile')!=PROFILE:raise ValueError('未知电脑球队生成输入')
    h=value.get('payload_hex','')
    if not isinstance(h,str)or len(h)!=1168:raise ValueError('电脑球队生成输入长度无效')
    try:payload=bytes.fromhex(h)
    except ValueError:raise ValueError('电脑球队生成输入编码无效')
    if payload[:8]!=b'FM27DUL1':raise ValueError('电脑球队生成输入版本无效')
    for side,team in enumerate(teams):
        p=payload[8+288*side:8+288*(side+1)]
        count=struct.unpack_from('<I',p,12)[0];mode=struct.unpack_from('<I',p,272)[0]
        if mode not in (0,1)or not 11<=count<=23 or count!=team.get('roster_size',26):raise ValueError('电脑球队比赛名单不一致')
        if struct.unpack_from('<I',p,8)[0]>10000 or max(p[16:68])>100 or max(p[68:76])>MAX_FORMATION_CODE or max(p[76:83])>20 or p[83]>100 or struct.unpack_from('<H',p,194)[0]>32:raise ValueError('电脑教练参数越界')
        uids=list(struct.unpack_from('<'+str(count)+'I',p,84))
        if len(set(uids))!=count or uids!=[r.get('source_uid')for r in team['players'][:count]]:raise ValueError('生成输入与真实球员身份不一致')
    return {'profile':PROFILE,'payload_hex':payload.hex()}


def encode(config,value):
    payload=bytes.fromhex(value['payload_hex']);records=[struct.unpack_from('<5I',config,i)for i in range(12,len(config),20)]
    modes=[struct.unpack_from('<I',payload,8+288*side+272)[0]for side in range(2)]
    records=[r for r in records if (modes[r[1]]or r[0]in (1,15,17))and not(r[0]==31 or r[0]==30 and r[2]==0)]
    return b'FM27CFG2'+struct.pack('<I',len(records))+b''.join(struct.pack('<5I',*r)for r in records)+payload
