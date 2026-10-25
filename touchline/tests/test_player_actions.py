import json
import math
from pathlib import Path
import unittest

from generate import Match
from realism.player_actions import KINDS, style_factors
from realism.policy import candidates

ROOT = Path(__file__).resolve().parents[1]


def profile(**scores):
    return {'status': 'complete', 'attribute_kind': 'outfield',
            'attributes': dict(ATT=50, DEF=50, CRE=50, TEC=50, TAC=50) | scores}


def scene(radar=None):
    sim = Match(714, action_multipliers={k: 1 for k in KINDS})
    sim.owner = 9
    sim.possession_team = 0
    sim.players[9].update(x=87, y=34, sofascore=radar)
    for i, p in enumerate(sim.players):
        if p['team'] == 1:
            p.update(x=98, y=4+(i-11)*5)
    sim.players[11].update(x=103, y=34)
    return sim


def masses(sim):
    options = candidates(sim)
    return {k: sum(o['probability'] for o in options if o['kind'] == k) for k in KINDS}


class PlayerActionTests(unittest.TestCase):
    def test_increasing_attack_raises_shooting_probability(self):
        low, high = scene(profile(ATT=10)), scene(profile(ATT=90))
        self.assertGreater(masses(high)['shot'], masses(low)['shot'])

    def test_creativity_favors_passing_and_technique_favors_carrying(self):
        self.assertGreater(masses(scene(profile(CRE=90)))['pass'],
                           masses(scene(profile(CRE=10)))['pass'])
        self.assertGreater(masses(scene(profile(TEC=90)))['carry'],
                           masses(scene(profile(TEC=10)))['carry'])
        for key in ('TAC', 'DEF'):
            self.assertGreater(masses(scene(profile(**{key: 90})))['pass'],
                               masses(scene(profile(**{key: 10})))['pass'])

    def test_missing_conflicting_and_wrong_radar_types_are_neutral(self):
        neutral = {k: 1.0 for k in KINDS}
        for value in (None, {}, {'status': 'needs_review'},
                      {**profile(ATT=90), 'attribute_kind': 'goalkeeper'},
                      {**profile(ATT=90), 'source_conflicts': {'position': {'source': 'G'}}}):
            self.assertEqual(style_factors(value), neutral)
        partial = profile(ATT=None, TEC=float('nan'))
        self.assertEqual(style_factors(partial), neutral)
        self.assertEqual(style_factors(profile(ATT=99), strength=0), neutral)

    def test_weights_are_bounded_probabilities_normalized_outcomes_unchanged(self):
        for value in (0, 100):
            factors = style_factors(profile(ATT=value, TEC=value, CRE=value, TAC=value, DEF=value))
            self.assertTrue(all(math.exp(-.6) <= v <= math.exp(.6) for v in factors.values()))
        sim = scene(profile(ATT=90, TEC=90))
        adjusted = candidates(sim)
        self.assertAlmostEqual(sum(o['probability'] for o in adjusted), 1)
        sim.attribute_actions = False
        neutral = candidates(sim)
        for a, b in zip(adjusted, neutral):
            self.assertEqual({k: v for k, v in a.items() if k not in ('weight', 'probability')},
                             {k: v for k, v in b.items() if k != 'weight'})

    def test_attributes_do_not_create_illegal_shots_or_passes(self):
        sim = scene(profile(ATT=100))
        sim.players[8].update(x=104, y=34)
        self.assertNotIn(8, [o.get('recipient') for o in candidates(sim)])
        sim.owner = 0
        sim.players[0].update(x=95, y=34, sofascore={'status': 'complete',
            'attribute_kind': 'goalkeeper', 'attributes': {'BAL': 100, 'TAC': 100}})
        self.assertNotIn('shot', [o['kind'] for o in candidates(sim)])
        sim.owner = 9
        sim.players[9]['x'] = 20
        self.assertNotIn('shot', [o['kind'] for o in candidates(sim)])

    def test_pass_reception_is_a_decision_not_a_forced_carry(self):
        sim = scene(profile(CRE=80))
        sim.action = {'id': 'test-pass', 'kind': 'pass', 'team': 0, 'actor': 9,
                      'receiver': 8, 'intended': 8, 'success': True, 'height': 0.,
                      'under_pressure': False, 'start': 0., 'start_ball': [80., 34., 0.]}
        calls = []
        sim.choose_action = lambda: calls.append('choice')
        sim.finish_action()
        self.assertEqual(calls, ['choice'])
        self.assertEqual(sim.owner, 8)

    def test_invalid_calibration_cannot_produce_negative_probabilities(self):
        for scales in ({'pass': 0, 'carry': 1, 'shot': 1}, {'pass': 1},
                       {'pass': float('nan'), 'carry': 1, 'shot': 1}):
            with self.assertRaises(ValueError):
                Match(1, action_multipliers=scales)

    def test_report_uses_disjoint_seeds_and_matches_and_meets_frozen_tolerance(self):
        report = json.loads((ROOT/'artifacts/realism/player-action-validation.json').read_text())
        self.assertFalse(set(report['config']['fit_seeds']) & set(report['validation_seeds']))
        splits = report['source']['split']
        self.assertFalse(set(splits['train']) & set(splits['test']))
        self.assertEqual(report['config']['target'], report['reference']['train'])
        self.assertTrue(report['passed'])
        for kind in KINDS:
            actual = report['attribute_policy']['shares'][kind]
            expected = report['reference']['test']['shares'][kind]
            self.assertLessEqual(abs(actual-expected), report['tolerance'][kind])
        config = json.loads((ROOT/'realism/player-action-profile.json').read_text())
        self.assertEqual(config, report['config'])


if __name__ == '__main__':
    unittest.main()
