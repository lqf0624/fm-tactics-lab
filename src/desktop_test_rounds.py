"""Two disjoint seeded rounds, retained separately in the experiment record."""
def plan(first,count,retest):
    for value,label in ((first,'起始种子'),(count,'首轮场数'),(retest,'复测场数')):
        if type(value) is not int:raise ValueError(label+'必须为整数')
    if not 0<=first<=0xffffffff:raise ValueError('起始种子超出范围')
    if any(not 2<=v<=10000 or v%2 for v in (count,retest)):
        raise ValueError('两轮每队场数必须为2–10000的偶数')
    end=first+count//2+retest//2
    if end-1>0xffffffff:raise ValueError('两轮种子超出范围')
    return split(list(range(first,end)),count)

def split(seeds, count):
    boundary=count//2
    return [{'number':1,'name':'第一轮筛选','seeds':seeds[:boundary]},
            {'number':2,'name':'第二轮新种子复测','seeds':seeds[boundary:]}]

def round_number(rounds,seed):
    return next((r['number'] for r in rounds if seed in r['seeds']),None)

def neutralize(scenario):
    for team in scenario['teams']:
        oi=team['opposition']
        neutral={'press':0,'mark':0,'tackle':0,'foot':0}
        for row in oi['players']+list(oi['positions'].values()):
            row.update(neutral)
        oi.pop('by_player_uid',None)
        for phase in team['phases']:
            for cell in phase:
                cell['instructions']['14']=0
                cell['target_player']=255
                cell['target_position']=0
    return scenario

def ranking(metrics):
    # Stable tie-breaking must not turn a tie into evidence of improvement.
    return sorted((g for g,m in metrics.items() if m),
                  key=lambda g:(-metrics[g]['win_rate'],-metrics[g]['points'],
                                -(metrics[g]['goals_for']-metrics[g]['goals_against']),g))
