"""Real current-save player attributes with approximate match rosters."""
import json

PROFILE='observed-plan-static-players-v1'


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def roster(lib,key,club,team,preferred=()):
    """Use real current members; historical or exact match-day XI is optional."""
    folder=lib.folder(key);lib.ensure_rosters(folder,[club])
    people={p['unique_id']:p for p in read(folder/'rosters'/f'{club}.json')
            if p.get('unique_id') is not None and p.get('club_uid')==club}
    if len(people)<11:raise ValueError('该队不足11名可读取真实属性的球员')
    first=[p for p in people.values() if p.get('team_slot')==0]
    pool=first if len(first)>=11 else list(people.values())
    allowed={p['unique_id']:p for p in pool};chosen=[]
    def ability(p):return p.get('ability',{}).get('current') or 0
    positions={'GK':'gk','DCL':'dc','DCR':'dc','DC':'dc','DL':'dl','DR':'dr','WBL':'wbl','WBR':'wbr',
               'DML':'dm','DMR':'dm','DMC':'dm','DM':'dm','MCL':'mc','MCR':'mc','MC':'mc','ML':'ml','MR':'mr',
               'AML':'aml','AMR':'amr','AMCL':'amc','AMCR':'amc','AMC':'amc','STCL':'stc','STCR':'stc','STC':'stc','ST':'stc','STL':'stc','STR':'stc'}
    preferred=list(preferred)
    for i,cell in enumerate(team['phases'][0]):
        uid=preferred[i] if i<len(preferred) else None
        if uid not in allowed or uid in chosen:
            position=positions.get(cell['position'],'mc')
            uid=max((u for u in allowed if u not in chosen),
                    key=lambda u:(allowed[u]['positions'].get(position,0),ability(allowed[u]),-u))
        chosen.append(uid)
    rest=[u for u in preferred[11:] if u in allowed and u not in chosen]
    rest=list(dict.fromkeys(rest))
    rest+=sorted((u for u in allowed if u not in chosen and u not in rest),key=lambda u:(-ability(allowed[u]),u))
    capacity=min(23,len(team['players']));uids=(chosen+rest)[:capacity]
    for i,uid in enumerate(uids):
        person=allowed[uid];values,profile=lib.player_values(person)
        team['players'][i].update(name=person['name'],source_uid=uid,attributes=values,native_profile=profile)
    for player in team['players'][len(uids):]:player.pop('source_uid',None);player['name']='未入比赛名单'
    team.update(roster_source={'id':key,'club_uid':club},lineup=list(range(11)),roster_size=len(uids),captains=[],takers={k:[] for k in lib.app.TAKER_KEYS})
    return team
