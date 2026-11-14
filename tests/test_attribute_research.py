from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from desktop_attribute_analysis import (FIELD_ATTRIBUTES, KEEPER_ATTRIBUTES,
    research_variants, research_report, validation_labels)


class ResearchTests(unittest.TestCase):
    def test_dual_screen_includes_near_cap_sensitive_attribute(self):
        runs, details = self.experiment()
        details.update(selection_policy='dual_v1', candidate_limit=1, attribute_increase=3)
        for case in details['cases']:
            if case['attribute'] == 3:
                case.update(before=99, after=100)
        rows = research_report(runs, details)
        self.assertEqual([r['attribute'] for r in rows if r['selected']], [0, 3])
        self.assertTrue(rows[3]['recommended'])
        self.assertEqual(len(validation_labels(details, maximum=True)), 6)

    def test_full_validation_can_recommend_outside_exploration_candidates(self):
        runs, details = self.experiment()
        details.update(selection_policy='dual_v1', validation_mode='full', candidate_limit=1)
        row = research_report(runs, details)[3]
        self.assertFalse(row['selected'])
        self.assertTrue(row['recommended'])
        self.assertEqual(row['recommendation_tier'], 'preliminary')

    def test_small_noisy_positive_batch_is_not_stable(self):
        runs, details = self.experiment()
        details.update(selection_policy='dual_v1', validation_seeds=[4, 5], stable_min_pairs=2)
        for run in runs:
            if run['variant'].endswith('A0'):
                run['statistics']['teams'][0]['xg'] = 1 + (.06 if run['seed'] < 4 else (.001 if run['seed'] == 4 else 1))
        row = research_report(runs, details)[0]
        self.assertTrue(row['recommended'])
        self.assertEqual(row['recommendation_tier'], 'recommended')
        self.assertLess(row['lower'], 0)

    def test_stability_reference_is_configurable_without_extra_matches(self):
        runs, details = self.experiment()
        details.update(selection_policy='dual_v1', validation_seeds=[4,5,6,7], stable_min_pairs=8)
        for run in runs:
            if run['variant'].endswith('A0'):
                run['statistics']['teams'][0]['xg'] = 1.06
        self.assertEqual(research_report(runs, details)[0]['recommendation_tier'], 'recommended')
        details['stable_min_pairs'] = 4
        self.assertEqual(research_report(runs, details)[0]['recommendation_tier'], 'stable')

    def test_exact_two_thirds_opponents_can_support_stability(self):
        runs, details = self.experiment()
        details.update(selection_policy='dual_v1')
        extra_cases = [deepcopy(case) for case in details['cases'] if case['baseline'] == '1B']
        for case in extra_cases:
            case.update(baseline='2B', variant='2' + case['variant'][1:], opponent_name='2')
        details['cases'].extend(extra_cases)
        extra_runs = [deepcopy(run) for run in runs if run['variant'].startswith('1')]
        for run in extra_runs:
            run['variant'] = '2' + run['variant'][1:]
        runs.extend(extra_runs)
        for run in runs:
            if run['variant'].endswith('A0'):
                run['statistics']['teams'][0]['xg'] = .99 if run['variant'].startswith('2') else 1.12
        row = research_report(runs, details)[0]
        self.assertAlmostEqual(row['positive_opponent_rate'], 2/3)
        self.assertEqual(row['recommendation_tier'], 'stable')

    def experiment(self):
        cases, runs = [], []
        for opponent in range(2):
            for attr in range(4):
                cases.append(dict(slot=0, attribute=attr, before=60, after=75,
                    baseline=f'{opponent}B', variant=f'{opponent}A{attr}', opponent_name=str(opponent)))
            for seed in range(24):
                def run(label, delta):
                    return dict(variant=label, seed=seed, result={'score':[0,0]},
                        statistics={'teams':[{'xg':1+delta},{'xg':1}]})
                runs.append(run(f'{opponent}B', 0))
                for attr in range(4):
                    # Validation's biggest effect must not change exploration selection.
                    delta = (.04-.01*attr) if seed<4 else (.005 if attr<3 else .9)
                    runs.append(run(f'{opponent}A{attr}',delta))
        details = dict(side=0, cases=cases, tested_slots=[0], exploration_seeds=list(range(4)),
                       validation_seeds=list(range(4,24)))
        return runs, details

    def test_point_zero_two_exploration_and_positive_validation_recommend(self):
        runs, details = self.experiment()
        rows = research_report(runs, details)
        self.assertEqual([r['attribute'] for r in rows if r['recommended']], [0,1,2])
        self.assertFalse(rows[3]['selected'])
        self.assertEqual(rows[0]['n'],20)  # Not 40 independent samples.
        self.assertAlmostEqual(rows[0]['xg_difference_per_three'],.005)

    def test_validation_must_be_complete_but_individual_opponents_may_vary(self):
        runs, details = self.experiment()
        runs = [r for r in runs if not(r['variant']=='1A0' and r['seed']==23)]
        rows = research_report(runs,details)
        self.assertEqual(rows[0]['n'],19)
        self.assertFalse(rows[0]['recommended'])
        for run in runs:
            if run['variant']=='1A1' and run['seed']>=4:
                run['statistics']['teams'][0]['xg']=.999
        rows=research_report(runs,details)
        self.assertGreater(rows[1]['xg_difference_per_three'],0)
        self.assertTrue(rows[1]['recommended'])
        self.assertLess(rows[1]['opponents'][1]['delta'],0)

    def test_below_point_zero_two_is_not_selected(self):
        runs, details = self.experiment()
        for run in runs:
            if run['variant']=='0A2' and run['seed']<4:
                run['statistics']['teams'][0]['xg']=1.019
            if run['variant']=='1A2' and run['seed']<4:
                run['statistics']['teams'][0]['xg']=1.019
        rows = research_report(runs, details)
        self.assertFalse(rows[2]['selected'])
        self.assertFalse(rows[2]['recommended'])

    def test_strong_exploration_still_needs_positive_validation(self):
        runs, details = self.experiment()
        for run in runs:
            if run['variant'].endswith('A0'):
                run['statistics']['teams'][0]['xg'] = 1.06 if run['seed'] < 4 else .99
        row = research_report(runs, details)[0]
        self.assertTrue(row['selected'])
        self.assertFalse(row['recommended'])
        self.assertEqual(row['recommendation_tier'], 'strong_candidate')

    def test_thresholds_and_candidate_limit_follow_run_settings(self):
        runs, details = self.experiment()
        details.update(candidate_threshold=.03, strong_threshold=.06, candidate_limit=1)
        rows = research_report(runs, details)
        self.assertTrue(rows[0]['selected'])
        self.assertTrue(rows[0]['recommended'])
        self.assertEqual(rows[0]['recommendation_tier'], 'preliminary')
        self.assertFalse(rows[1]['selected'])

    def test_evidence_levels_and_per_point_sensitivity(self):
        runs, details = self.experiment()
        for run in runs:
            if run['variant'].endswith('A0'):
                run['statistics']['teams'][0]['xg'] = 1.06 if run['seed'] < 4 else 1.04
            if run['variant'].endswith('A1') and run['seed'] >= 4:
                run['statistics']['teams'][0]['xg'] = 1.04
        rows = research_report(runs, details)
        self.assertEqual(rows[0]['recommendation_tier'], 'stable')
        self.assertEqual(rows[1]['recommendation_tier'], 'recommended')
        self.assertAlmostEqual(rows[0]['xg_difference_per_point'], .04/3)

    def test_standard_levels_and_two_stage_labels(self):
        names=FIELD_ATTRIBUTES+KEEPER_ATTRIBUTES
        attrs={name:i for i,name in enumerate(names)}
        team=dict(name='team',lineup=[0],players=[dict(name='player',attributes=[60]*69)],
            phases=[[dict(position='ST',role='Forward')],[dict(position='ST',role='OPTrackingCentreForward')]])
        source={'teams':[deepcopy(team),deepcopy(team)]}
        variants,cases=research_variants([('one',source),('two',source)],0,[0],attrs,
            broad=False,attribute_increase=3,standard_levels=[8,12,16])
        self.assertEqual(len(cases),24)
        self.assertEqual({case['profile_level'] for case in cases},{8,12,16})
        details={'cases':cases,'tested_slots':[0],'candidate_limit':2}
        maximum=validation_labels(details,maximum=True)
        self.assertEqual(len(maximum),24)  # 2 attrs × 3 levels × 2 opponents × baseline/change.
        selected=validation_labels(details,{(0,cases[0]['attribute'])})
        self.assertEqual(len(selected),12)

        current_variants,current_cases=research_variants([('one',source),('two',source)],0,[0],attrs,
            broad=False,attribute_increase=3)
        current_details={'cases':current_cases,'tested_slots':[0],'candidate_limit':2}
        stage_two_count=4*len(current_variants)+8*len(validation_labels(current_details,maximum=True))
        full_count=12*len(current_variants)
        self.assertEqual((len(current_variants),stage_two_count,full_count),(10,88,120))

    def test_broad_coverage_and_only_one_attribute_changes(self):
        names=FIELD_ATTRIBUTES+KEEPER_ATTRIBUTES
        attrs={name:i for i,name in enumerate(names)}
        team=dict(name='team',lineup=[0],players=[dict(name='player',attributes=[60]*69)],
            phases=[[dict(position='GK',role='Goalkeeper')],[dict(position='GK',role='OPGoalkeeper')]])
        source={'teams':[deepcopy(team),deepcopy(team)]}
        variants,cases=research_variants([('one',source),('two',source)],0,[0],attrs)
        self.assertEqual(len(cases),78)
        originals=dict(variants)
        for case in cases:
            config=deepcopy(originals[case['variant']])
            config['teams'][0]['players'][0]['attributes'][case['attribute']]=60
            self.assertEqual(config,source)
            self.assertIn(case['baseline'], originals)

    def test_multiple_selected_slots_are_built_in_one_experiment(self):
        names=FIELD_ATTRIBUTES+KEEPER_ATTRIBUTES
        attrs={name:i for i,name in enumerate(names)}
        team=dict(name='team',lineup=[0,1],players=[dict(name='striker',attributes=[60]*69),
            dict(name='midfielder',attributes=[60]*69)],phases=[
            [dict(position='ST',role='Forward'),dict(position='MC',role='CentralMidfielder')],
            [dict(position='ST',role='OPTrackingCentreForward'),dict(position='MC',role='OPCentralMidfielder')]])
        source={'teams':[deepcopy(team),deepcopy(team)]}
        variants,cases=research_variants([('one',source)],0,[0,1],attrs,broad=False)
        self.assertEqual({case['slot']for case in cases},{0,1})
        self.assertEqual({slot:sum(case['slot']==slot for case in cases)for slot in(0,1)},{0:4,1:4})
        self.assertEqual(len(variants),9)  # Shared baseline plus four changes per selected slot.
