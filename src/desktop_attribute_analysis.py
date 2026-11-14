"""Build and summarize same-seed role attribute experiments."""

from copy import deepcopy
from statistics import mean, stdev


def change_attribute(scenario, side, slot, attribute, target):
    team = scenario['teams'][side]
    index = team['lineup'][slot]
    player = team['players'][index]
    before = player['attributes'][attribute]
    if target == before:
        raise ValueError('测试属性值必须与原值不同')

    modified = deepcopy(scenario)
    modified['teams'][side]['players'][index]['attributes'][attribute] = target
    details = {
        'side': side, 'slot': slot, 'attribute': attribute,
        'before': before, 'after': target,
        'team': team['name'], 'player': player['name'],
        'phases': [{key: cells[slot][key] for key in ('position', 'role')}
                   for cells in team['phases']],
    }
    return modified, details


POSITION_CANDIDATES = {
    'GK': ('Reflexes', 'Handling', 'OneOnOnes', 'Positioning'),
    'DC': ('Positioning', 'Anticipation', 'Pace', 'Tackling'),
    'DL': ('Pace', 'Tackling', 'Crossing', 'Stamina'),
    'DM': ('Tackling', 'Positioning', 'Passing', 'Decisions'),
    'MC': ('Passing', 'Decisions', 'Stamina', 'Tackling'),
    'AM': ('Dribbling', 'Passing', 'OffTheBall', 'Acceleration'),
    'ST': ('Finishing', 'OffTheBall', 'Acceleration', 'Composure'),
}


def candidate_attributes(ip, oop):
    """A short, editable screening list. Match results determine the ranking."""
    position = ip['position']
    if position == 'GK':
        group = 'GK'
    elif position.startswith('DC'):
        group = 'DC'
    elif position in ('DL', 'DR', 'WBL', 'WBR'):
        group = 'DL'
    elif position.startswith('DM'):
        group = 'DM'
    elif position.startswith('MC') or position in ('ML', 'MR'):
        group = 'MC'
    elif position.startswith('AM'):
        group = 'AM'
    else:
        group = 'ST'
    picks = list(POSITION_CANDIDATES[group])
    role = ip['role'] + ' ' + oop['role']
    if 'Playmaker' in role or 'Playmaking' in role:
        picks[-1] = 'Vision'
    elif 'TargetForward' in role:
        picks[-1] = 'JumpingReach'
    elif 'BallPlaying' in role and group in ('GK', 'DC'):
        picks[-1] = 'Passing'
    elif ('InsideForward' in role or 'WideForward' in role) and group == 'AM':
        picks[1] = 'Finishing'
    elif ('FalseNine' in role or 'DeepLyingForward' in role) and group == 'ST':
        picks[-1] = 'Passing'
    elif 'Poacher' in role and group == 'ST':
        picks[-1] = 'Anticipation'
    elif 'Pressing' in role:
        picks[-1] = 'WorkRate'
    elif 'Winger' in role and group == 'AM':
        picks[-1] = 'Crossing'
    return tuple(dict.fromkeys(picks))


FIELD_ATTRIBUTES = ('Crossing', 'Dribbling', 'Finishing', 'Heading', 'LongShots',
    'Marking', 'OffTheBall', 'Passing', 'Tackling', 'Vision', 'Anticipation',
    'Decisions', 'Positioning', 'FirstTouch', 'Technique', 'Flair', 'Teamwork',
    'WorkRate', 'Acceleration', 'Strength', 'Stamina', 'Pace', 'JumpingReach',
    'Balance', 'Bravery', 'Aggression', 'Agility', 'Determination', 'Composure',
    'Concentration')
KEEPER_ATTRIBUTES = ('Handling', 'AerialReach', 'CommandOfArea', 'Communication',
    'Kicking', 'Throwing', 'OneOnOnes', 'Reflexes', 'RushingOut')


def screen_variants(scenario, side, slots, attributes, broad=False, attribute_increase=3,
                    standard_levels=None):
    variants = [] if standard_levels else [('B', scenario)]
    cases = []
    for slot in slots:
        team = scenario['teams'][side]
        player = team['players'][team['lineup'][slot]]
        ip, oop = (cells[slot] for cells in team['phases'])
        names = (FIELD_ATTRIBUTES + (KEEPER_ATTRIBUTES if ip['position'] == 'GK' else ())) if broad else candidate_attributes(ip, oop)
        for name in names:
            attribute = attributes[name]
            levels = standard_levels or [player['attributes'][attribute] / 5]
            for level in levels:
                source = deepcopy(scenario)
                before = player['attributes'][attribute] if not standard_levels else int(level * 5)
                source['teams'][side]['players'][team['lineup'][slot]]['attributes'][attribute] = before
                target = min(100, before + attribute_increase * 5)
                if target == before:
                    continue
                suffix = f'L{int(level):02d}' if standard_levels else ''
                baseline = f'S{slot:02d}A{attribute:02d}{suffix}B' if standard_levels else 'B'
                label = f'S{slot:02d}A{attribute:02d}{suffix}V' if standard_levels else f'S{slot:02d}A{attribute:02d}'
                modified, detail = change_attribute(source, side, slot, attribute, target)
                detail.update(variant=label, baseline=baseline, attribute_label=name,
                              requested_increase=attribute_increase,
                              actual_increase=(target-before)/5,
                              profile_level=int(level) if standard_levels else None)
                cases.append(detail)
                if standard_levels:
                    variants.append((baseline, source))
                variants.append((label, modified))
    return variants, cases


def research_variants(opponents, side, slots, attributes, broad=True, attribute_increase=3,
                      standard_levels=None):
    variants, cases = [], []
    for index, (name, scenario) in enumerate(opponents):
        local, details = screen_variants(scenario, side, slots, attributes, broad,
                                         attribute_increase, standard_levels)
        prefix = f'O{index:02d}'
        variants.extend((prefix + label, config) for label, config in local)
        for case in details:
            case.update(variant=prefix + case['variant'], baseline=prefix + case.get('baseline', 'B'),
                        opponent=index, opponent_name=(f"{name} · 标准属性 {case['profile_level']}"
                            if case.get('profile_level') is not None else name))
            cases.append(case)
    return variants, cases


def validation_labels(details, selected_pairs=None, maximum=False):
    """Return the exact baseline/change variants needed for stage-two validation."""
    groups = {}
    for case in details['cases']:
        groups.setdefault((case['slot'], case['attribute']), []).append(case)
    if maximum:
        selected = set()
        for slot in details['tested_slots']:
            limit = details.get('candidate_limit', 5) * (2 if details.get('selection_policy') == 'dual_v1' else 1)
            selected.update(list(key for key in groups if key[0] == slot)[:limit])
    else:
        selected = set(selected_pairs or ())
    chosen = [case for key, cases in groups.items() if key in selected for case in cases]
    return {case['baseline'] for case in chosen} | {case['variant'] for case in chosen}


def planned_matches(details, variant_count):
    exploration = len(details['exploration_seeds']) * variant_count
    validation_variants = len(validation_labels(details, maximum=True)) if details['validation_mode'] == 'two_stage' else variant_count
    return exploration + len(details['validation_seeds']) * validation_variants


def research_report(runs, details):
    """Average fixed opponents within seed before estimating uncertainty.

    Exploration selects a configurable number of attributes per slot above a
    configurable xG-difference gain. Disjoint validation seeds assess them; a positive
    validation mean is enough for a practical recommendation. The four-SE
    range remains descriptive and is no longer a recommendation gate.
    """
    indexed = {}
    for run in runs:
        indexed.setdefault(run['variant'], {})[run['seed']] = run
    groups = {}
    for case in details['cases']:
        groups.setdefault((case['slot'], case['attribute']), []).append(case)
    rows = []
    candidate_threshold = details.get('candidate_threshold', .02)
    strong_threshold = details.get('strong_threshold', .05)
    candidate_limit = details.get('candidate_limit', 5)
    dual = details.get('selection_policy') == 'dual_v1'
    full = details.get('validation_mode') == 'full'
    increase = details.get('attribute_increase', 3)
    keys = ('goals_for', 'goals_against', 'xg', 'xga', 'xg_difference',
            'possession', 'shots', 'shots_on_target', 'passes', 'completed_passes',
            'pass_completion', 'opponent_shots', 'opponent_shots_on_target')
    side = details['side']

    def values(run):
        score, teams = run['result']['score'], run['statistics']['teams']
        own, other = teams[side], teams[1-side]
        return {'goals_for': score[side], 'goals_against': score[1-side],
                'xg': own['xg'], 'xga': other['xg'],
                'xg_difference': own['xg'] - other['xg'],
                'possession': own.get('possession', 0), 'shots': own.get('shots', 0),
                'shots_on_target': own.get('shots_on_target', 0),
                'passes': own.get('passes', 0), 'completed_passes': own.get('completed_passes', 0),
                'pass_completion': own.get('completed_passes', 0) / max(1, own.get('passes', 0)),
                'opponent_shots': other.get('shots', 0),
                'opponent_shots_on_target': other.get('shots_on_target', 0)}

    def stats(samples):
        return {'delta': mean(samples) if samples else None,
                'standard_error': stdev(samples)/len(samples)**0.5 if len(samples)>1 else None}

    for cases in groups.values():
        per_opponent = []
        for case in cases:
            base = indexed.get(case['baseline'], {})
            changed = indexed.get(case['variant'], {})
            direction = 1 if case['after'] > case['before'] else -1
            paired = {seed: {key: direction * (values(changed[seed])[key] - values(base[seed])[key])
                              for key in keys} for seed in base.keys() & changed.keys()}
            per_opponent.append((case, paired))
        common = set.intersection(*(set(pairs) for _, pairs in per_opponent))
        stage_stats = {}
        for stage in ('exploration', 'validation'):
            seeds = sorted(common & set(details[stage + '_seeds']))
            xg_samples = [mean(pairs[seed]['xg_difference'] for _, pairs in per_opponent) for seed in seeds]
            point_samples = [mean(pairs[seed]['xg_difference'] /
                max(.2, abs(case['after']-case['before'])/5) for case, pairs in per_opponent)
                for seed in seeds]
            stage_stats[stage] = {'n': len(seeds), 'metrics': {
                key: stats([mean(pairs[seed][key] for _, pairs in per_opponent) for seed in seeds])
                for key in keys}, 'xg_difference_per_point': stats(point_samples),
                'positive_seed_rate': (sum(value > 0 for value in xg_samples) / len(xg_samples)
                                       if xg_samples else None)}
        validation = stage_stats['validation']
        metric = validation['metrics']['xg_difference']
        opponents = []
        for case, pairs in per_opponent:
            seeds = sorted(set(pairs) & set(details['validation_seeds']))
            opponents.append({'name': case['opponent_name'], 'n': len(seeds),
                              **stats([pairs[seed]['xg_difference'] for seed in seeds]),
                              'profile_level': case.get('profile_level')})
        delta, error = metric['delta'], metric['standard_error']
        rows.append({**cases[0], 'n': validation['n'], 'metrics': validation['metrics'],
                     'exploration': stage_stats['exploration'], 'opponents': opponents,
                     'xg_difference_per_three': delta, 'standard_error': error,
                     'xg_difference_per_point': validation['xg_difference_per_point']['delta'],
                     'positive_seed_rate': validation['positive_seed_rate'],
                     'lower': delta-4*error if error is not None else None,
                     'upper': delta+4*error if error is not None else None,
                     'selected': False, 'recommended': False,
                     'recommendation_tier': None})
    for slot in details['tested_slots']:
        candidates = [row for row in rows if row['slot']==slot]
        discovery_complete = all(row['exploration']['n']==len(details['exploration_seeds']) for row in candidates)
        if not discovery_complete:
            continue
        candidates.sort(key=lambda row: row['exploration']['metrics']['xg_difference']['delta'], reverse=True)
        eligible = [row for row in candidates
                    if row['exploration']['metrics']['xg_difference']['delta'] >= candidate_threshold]
        chosen = eligible[:candidate_limit]
        if dual:
            sensitive = sorted(candidates, key=lambda row: row['exploration']['xg_difference_per_point']['delta'], reverse=True)
            sensitive = [row for row in sensitive if row['exploration']['xg_difference_per_point']['delta'] >= candidate_threshold / increase][:candidate_limit]
            chosen = [row for row in candidates if row in chosen or row in sensitive]
        for row in chosen:
            row['selected'] = True
        # Keep legacy selection for saved experiments so resuming cannot change their tasks.
        for row in (candidates if dual and full else chosen):
            exploration_delta = row['exploration']['metrics']['xg_difference']['delta']
            validation_complete = row['n'] == len(details['validation_seeds'])
            row['recommended'] = (validation_complete and row['xg_difference_per_three'] is not None
                                  and row['xg_difference_per_three'] > 0)
            if row['recommended']:
                positive_opponents = sum(op['delta'] is not None and op['delta'] > 0 for op in row['opponents'])
                opponent_rate = positive_opponents / len(row['opponents']) if row['opponents'] else 0
                stable = (exploration_delta >= strong_threshold
                          and row['xg_difference_per_three'] >= candidate_threshold
                          and (row['positive_seed_rate'] or 0) >= .6 and opponent_rate >= .67)
                general = exploration_delta >= candidate_threshold and row['xg_difference_per_three'] >= candidate_threshold
                if dual:
                    general = general or (row['exploration']['xg_difference_per_point']['delta'] >= candidate_threshold / increase
                        and row['xg_difference_per_point'] >= candidate_threshold / increase)
                    stable = (exploration_delta >= strong_threshold
                        and row['xg_difference_per_three'] >= strong_threshold
                        and row['n'] >= details.get('stable_min_pairs', 8)
                        and row['lower'] is not None and row['lower'] > 0
                        and (row['positive_seed_rate'] or 0) >= .6
                        and positive_opponents * 3 >= len(row['opponents']) * 2)
                row['recommendation_tier'] = ('stable' if stable else 'recommended'
                    if (general if dual else row['xg_difference_per_three'] >= candidate_threshold) else 'preliminary')
                row['positive_opponent_rate'] = opponent_rate
            elif exploration_delta >= strong_threshold:
                row['recommendation_tier'] = 'strong_candidate'
    for row in rows:
        row['evidence_warnings'] = []
        if row['n'] < details.get('stable_min_pairs', 8):
            row['evidence_warnings'].append('验证样本较少')
        if row['lower'] is None or row['lower'] <= 0:
            row['evidence_warnings'].append('正向收益仍有波动风险')
        if len(details.get('opponent_names', [])) == 1:
            row['evidence_warnings'].append('仅覆盖当前对手')
    return rows
