from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from desktop_attribute_analysis import (
    candidate_attributes, change_attribute, screen_variants,
)


class AttributeAnalysisTests(unittest.TestCase):
    def test_changes_selected_starter_not_roster_order(self):
        team = {
            'name': 'Test team', 'lineup': [1, 0],
            'players': [{'name': 'Other', 'attributes': [45] * 69},
                        {'name': 'Starter', 'attributes': [65] * 69}],
            'phases': [[{'position': 'MC', 'role': 'CentralMidfielder'}],
                       [{'position': 'DM', 'role': 'OPDefensiveMidfielder'}]],
        }
        source = {'teams': [deepcopy(team), team]}
        changed, details = change_attribute(source, 1, 0, 49, 80)
        self.assertEqual(details['player'], 'Starter')
        self.assertEqual([phase['position'] for phase in details['phases']], ['MC', 'DM'])
        self.assertEqual(changed['teams'][0], team)
        self.assertEqual(changed['teams'][1]['players'][0], team['players'][0])
        self.assertEqual(source['teams'][1]['players'][1]['attributes'][49], 65)
        changed['teams'][1]['players'][1]['attributes'][49] = 65
        self.assertEqual(changed, source)
        with self.assertRaises(ValueError):
            change_attribute(source, 1, 0, 49, 65)

    def test_screen_uses_roles_and_changes_one_selected_starter_attribute(self):
        team = {
            'name': 'Test team', 'lineup': list(range(11)),
            'players': [{'name': str(index), 'attributes': [60] * 69}
                        for index in range(11)],
            'phases': [
                [{'position': 'ST', 'role': 'TargetForward'} for _ in range(11)],
                [{'position': 'ST', 'role': 'OPTrackingCentreForward'} for _ in range(11)],
            ],
        }
        scenario = {'teams': [deepcopy(team), team]}
        self.assertIn('JumpingReach', candidate_attributes(
            team['phases'][0][0], team['phases'][1][0]))
        self.assertIn('Finishing', candidate_attributes(
            {'position': 'AMR', 'role': 'InsideForward'},
            {'position': 'AMR', 'role': 'OPWinger'}))
        self.assertIn('Passing', candidate_attributes(
            {'position': 'DC', 'role': 'BallPlayingCentreBack'},
            {'position': 'DC', 'role': 'OPCentreBack'}))
        attributes = {name: index for index, name in enumerate(
            ('Finishing', 'OffTheBall', 'Acceleration', 'Composure', 'JumpingReach'), 17)}
        variants, cases = screen_variants(scenario, 1, [3], attributes)
        self.assertEqual(len(variants), 5)
        for case, (variant, modified) in zip(cases, variants[1:]):
            self.assertEqual(case['variant'], variant)
            self.assertEqual(case['slot'], 3)
            self.assertEqual(modified['teams'][0], scenario['teams'][0])
            modified['teams'][1]['players'][3]['attributes'][case['attribute']] = case['before']
            self.assertEqual(modified, scenario)

    def test_screen_increase_is_configurable_and_capped_at_twenty(self):
        names = ('Finishing', 'OffTheBall', 'Acceleration', 'Composure')
        attributes = {name: index for index, name in enumerate(names, 17)}
        team = {
            'name': 'Test team', 'lineup': [0],
            'players': [{'name': 'Starter', 'attributes': [60] * 69}],
            'phases': [[{'position': 'ST', 'role': 'Forward'}],
                       [{'position': 'ST', 'role': 'OPTrackingCentreForward'}]],
        }
        team['players'][0]['attributes'][attributes['Finishing']] = 95
        scenario = {'teams': [deepcopy(team), deepcopy(team)]}
        variants, cases = screen_variants(scenario, 0, [0], attributes, attribute_increase=3)
        finishing = next(case for case in cases if case['attribute_label'] == 'Finishing')
        self.assertEqual(finishing['after'], 100)
        self.assertEqual(finishing['actual_increase'], 1)
        self.assertEqual(finishing['requested_increase'], 3)
        _, two_point_cases = screen_variants(scenario, 0, [0], attributes, attribute_increase=2)
        off_ball = next(case for case in two_point_cases if case['attribute_label'] == 'OffTheBall')
        self.assertEqual(off_ball['after'], 70)
        for attribute in attributes.values():
            scenario['teams'][0]['players'][0]['attributes'][attribute] = 100
        variants, cases = screen_variants(scenario, 0, [0], attributes, attribute_increase=3)
        self.assertEqual(variants, [('B', scenario)])
        self.assertEqual(cases, [])
