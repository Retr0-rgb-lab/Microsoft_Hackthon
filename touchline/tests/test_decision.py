import copy
import json
import math
import unittest
from pathlib import Path
from decision.engine import analyze, review


def sample():
    players = [['H01', 50, 34, 0, 0], ['H02', 65, 20, 0, 0],
               ['H03', 93, 30, 0, 0], ['A01', 102, 34, 0, 0],
               ['A02', 80, 40, 0, 0], ['A03', 60, 55, 0, 0]]
    frame = {'players': players, 'period': 1, 't_ms': 20000, 'in_play': True,
             'ball_owner_id': 'H01', 'ball': [50, 34, 0, 0, 0, 0]}
    metadata = {'players': [{'player_id': p[0], 'team_id': 'HOME' if p[0][0]=='H' else 'AWAY'} for p in players]}
    return frame, metadata


class DecisionTests(unittest.TestCase):
    def test_mirrored_halves_preserve_evaluation(self):
        f, m = sample()
        a = analyze(f, m)
        mirror = copy.deepcopy(f); mirror['period'] = 2
        for p in mirror['players']:
            p[1], p[3] = 105-p[1], -p[3]
        b = analyze(mirror, m)
        for x, y in zip(a['candidates'], b['candidates']):
            self.assertEqual(x['action_id'], y['action_id'])
            self.assertAlmostEqual(x['value_gain'], y['value_gain'])

    def test_offside_never_recommended(self):
        f, m = sample(); r = analyze(f, m)
        illegal = next(c for c in r['candidates'] if c['receiver_id']=='H03')
        self.assertFalse(illegal['feasible_by_rules'])
        self.assertNotEqual(r['recommended_action_id'], illegal['action_id'])

    def test_defender_in_lane_reduces_feasibility(self):
        f, m = sample()
        before = next(c for c in analyze(f,m)['candidates'] if c['receiver_id']=='H02')
        f['players'][-1][1:3] = [57.5, 27]
        after = next(c for c in analyze(f,m)['candidates'] if c['receiver_id']=='H02')
        self.assertLess(after['feasibility_index'], before['feasibility_index'])

    def test_unknown_owner_is_unavailable(self):
        f,m = sample(); f['ball_owner_id'] = None
        self.assertEqual(analyze(f,m)['status'], 'unavailable')

    def test_no_future_events_consumed(self):
        f,m = sample(); a = analyze(f,m)
        f['future_events'] = [{'outcome':'goal'}]
        self.assertEqual(a, analyze(f,m))
        self.assertFalse(review(a)['is_multi_agent'])

    def test_invalid_tracking_rejected(self):
        f,m = sample(); f['players'][0][1] = math.nan
        with self.assertRaises(ValueError): analyze(f,m)

    def test_existing_preview_can_be_analyzed(self):
        p = next((Path(__file__).resolve().parents[1]/'data/league/matches').glob('*/preview-60s.json'))
        data = json.loads(p.read_text())
        f = next(f for f in data['frames'] if f['in_play'] and f['ball_owner_id'])
        r = analyze(f,data['metadata'])
        self.assertGreater(len(r['candidates']),0)
        self.assertTrue(all(math.isfinite(c['value_gain']) for c in r['candidates']))

if __name__ == '__main__': unittest.main()
