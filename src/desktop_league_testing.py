"""Current-save five-league teams, independent of the human manager."""
import copy
import desktop_coach_presets
import desktop_opponent_scope
import desktop_static_plans

# Stable FM competition database IDs, never save-local IDs or fixed club lists.
TOP_FIVE=((11,'英超'),(67,'西甲'),(16,'法甲'),(22,'德甲'),(32,'意甲'))

def five_leagues(data):
    result=[]
    for database_id,name in TOP_FIVE:
        entries=[e for e in data.get('leagues',[]) if data.get('competitions',{}).get(str(e['competition_id']))==database_id]
        today=data['date']
        active=[e for e in entries if e.get('first_date','9999')<=today<=e.get('last_date','')]
        future=[e for e in entries if e.get('first_date','')>today]
        past=[e for e in entries if e.get('last_date','9999')<today]
        entry=(sorted(active,key=lambda e:e['first_date'],reverse=True) or
               sorted(future,key=lambda e:e['first_date']) or
               sorted(past,key=lambda e:e['last_date'],reverse=True))
        result.append({**(entry[0] if entry else {}),'name':name,'database_id':database_id,
                       'available':bool(entry),'club_uids':entry[0]['club_uids'] if entry else [],
                       'reason':None if entry else '当前存档没有可核实的该联赛赛程，请检查游戏中是否加载该联赛'})
    return result

def catalog(lib,key):
    data=lib.index_data(lib.folder(key));leagues=five_leagues(data)
    info={int(uid):c for uid,c in data.get('league_clubs',{}).items()}
    info.update({c['uid']:c for c in data['clubs']})
    managed={m['club_uid'] for m in data['managed']}
    membership={uid:l for l in leagues for uid in l['club_uids']}
    clubs=[]
    for uid in managed|set(membership):
        c=info.get(uid)
        if not c:continue
        league=membership.get(uid,{})
        clubs.append({'uid':uid,'name':c.get('short_name') or c.get('name') or str(uid),
                      'players':data.get('first_team_counts',{}).get(str(uid)),
                      'league_key':league.get('key'),'league_name':league.get('name'),
                      'managed':uid in managed})
    clubs.sort(key=lambda c:(not c['managed'],c['league_name'] or '',c['name']))
    return {'leagues':leagues,'clubs':clubs}

def bench_for_selection(team,selected,requested=None):
    if requested is not None:return requested
    starters=set(selected)
    candidates=[p.get('source_uid') for p in team['players'][11:team['roster_size']]]
    candidates += [p.get('source_uid') for p in team['players'][:11]]
    candidates += [p.get('source_uid') for p in team.get('squad',[])]
    return list(dict.fromkeys(uid for uid in candidates if uid is not None and uid not in starters))[:min(12,len(team['players'])-11)]

def load_board(lib,key,club,scenario,side=0,selected=None,substitutes=None):
    """Keep the user's tactics, replacing only current-save roster and identity."""
    app=lib.app;side=app.integer(side,0,1,'球队')
    allowed={c['uid'] for c in catalog(lib,key)['clubs']}
    if club not in allowed:raise ValueError('请选择当前存档五大联赛或执教球队')
    scenario=app.validate_scenario(scenario)
    team=lib.board_roster(key,club,side,scenario)
    people=desktop_static_plans.read(lib.folder(key)/'rosters'/f'{club}.json')
    team['squad']=[]
    for person in people:
        if person.get('club_uid')!=club or person.get('unique_id') is None:continue
        values,profile=lib.player_values(person)
        team['squad'].append({'name':person['name'],'source_uid':person['unique_id'],'attributes':values,
                              'initial_attributes':values[:],'native_profile':profile})
    team['tactic_name']='当前战术板 · 存档真实阵容'
    scenario['teams'][side]=team
    if selected is not None:
        scenario=lib.select_squad(scenario,side,selected,bench_for_selection(team,selected,substitutes),initial=True)
    result=app.validate_scenario(scenario)
    data=lib.index_data(lib.folder(key))
    return {'scenario':result,'source':{'save_id':key,'club_uid':club,'date':data['date'],
            'tactic_index':'board','tactic_name':team['tactic_name'],'selected_tactic_confirmed':False,
            'notice':'已读取当前存档真实阵容；球队与个人战术沿用当前战术板，可继续编辑。体能、士气使用统一开赛条件。',
            'roster_count':len(people),'match_roster_count':result['teams'][side]['roster_size']}}

def coach_catalog(lib,key,league):
    _,entry=lib._league_entry(lib.folder(key),league)
    return desktop_coach_presets.ensure(lib,key,clubs=entry['club_uids'],slot=lib._league_token(league))

def opponents(lib,key,own):
    data=lib.index_data(lib.folder(key));scope=desktop_opponent_scope.identify(data,own)
    candidates=[e for e in data.get('leagues',[]) if own in e['club_uids']
                and set(e['club_uids'])==scope['same_league']|{own}]
    if len(candidates)!=1:raise ValueError('当前存档不能唯一确认该球队的当季联赛')
    entries={e['key']:e for e in five_leagues(data) if e['available']}
    entries.setdefault(candidates[0]['key'],candidates[0])
    rows=[];failures=[];members=set()
    for league,entry in entries.items():
        value=coach_catalog(lib,key,league)
        failures.extend(value['failures']);members.update(entry['club_uids'])
        for row in desktop_coach_presets.opponents(lib,key,own,value=value):
            row['key']=row['fixture_key']='league-coach:'+league+':'+str(row['coach']['team_id'])
            row.update(league_key=league,league_name=entry.get('name','本队联赛'))
            rows.append(row)
    # Human managers have no AI coach preset. Their saved plans are usable and labelled.
    managed = {m['club_uid'] for m in data['managed']}
    for uid in (members & managed)-{own}:
        stored=next(((i,t) for i,t in enumerate(data['tactics']) if t.get('club_uid')==uid
                     and t.get('team_slot')==0 and t.get('raw_plan')),None)
        if not stored or any(r['club_uid']==uid for r in rows):continue
        i,t=stored;c=next(c for c in data['clubs'] if c['uid']==uid)
        token=f'saved-club:{uid}:{i}'
        rows.append({'key':token,'fixture_key':token,'club_uid':uid,'name':c.get('short_name') or c['name'],
                     'side':1,'available':True,'source_kind':'saved_club_tactic','date':data['date'],
                     'member':t['name'],'source':'该存档的一线队保存战术 · '+t['name']+'；非当天实战还原。',
                     'cache_roster_count':0,'match_roster_count':0,'excluded_substitute_uids':[]})
    for row in rows:
        entry=next(e for e in entries.values() if row['club_uid'] in e['club_uids'])
        row.update(league_key=entry['key'],league_name=entry.get('name','本队联赛'))
    available={r['club_uid'] for r in rows}
    info=data.get('league_clubs',{});errors={f['club_uid']:f['error'] for f in failures}
    report={'recovery_profile':lib.OPPONENT_PROFILE,'binding':value['binding'],'opponents':rows,
            'failures':failures,'leagues':[{'key':k,'name':e.get('name','本队联赛')} for k,e in entries.items()],'source_policy':'coach_preference_preset','source_kind':'league_selection',
            'unrecovered_clubs':[{'club_uid':uid,'name':info.get(str(uid),{}).get('name',str(uid)),
                                'reason':errors.get(uid,'没有可核实的一线队战术来源')} for uid in scope['same_league']-available],
            'played_opponent_clubs':len(scope['played']),'checked':len(rows),'total_cached':0,
            'native_executed':0,'snapshot_cache_hits':0,'elapsed_seconds':0}
    desktop_opponent_scope.annotate(report,data,own,scope)
    lib.write(lib.folder(key)/f'opponents_{own}.json',report)
    return report

def opponent_team(lib,key,candidate):
    app=lib.app
    if candidate.startswith('saved-club:'):
        _,club,index=candidate.split(':');club=int(club);index=int(index)
        lib.ensure_rosters(lib.folder(key),[club])
        return lib.load_team(key,club,index,None,1,copy.deepcopy(app.DEFAULT))['scenario']['teams'][1]
    league,ident=candidate[len('league-coach:'):].rsplit(':',1)
    value=coach_catalog(lib,key,league)
    t=next((t for t in value['teams'] if t['team_id']==int(ident)),None)
    if t is None:raise ValueError('教练方案不属于当前联赛')
    team=desktop_coach_presets.preset_by_index_team(lib,key,t['preset_index'],t['name'],t['preset_sha256'])
    desktop_static_plans.roster(lib,key,t['club_uid'],team)
    return team
