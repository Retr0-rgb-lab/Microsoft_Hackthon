import copy
import math
import unittest
from decision.rollout import simulate, DT
from test_decision import sample


class RolloutTests(unittest.TestCase):
    def test_bounded_reproducible_and_no_future_data(self):
        f,m = sample(); original = copy.deepcopy(f)
        r = simulate(f,m,'pass:H02')
        self.assertEqual(f,original)
        f['future_events'] = ['goal']
        self.assertEqual(r,simulate(f,m,'pass:H02'))
        self.assertEqual(len(r['scenarios']),4)
        for s in r['scenarios']:
            self.assertLessEqual(s['duration_s'],4)
            self.assertEqual(s['frames'][0]['players'],original['players'])
            for previous, current in zip(s['frames'],s['frames'][1:]):
                self.assertGreater(current['elapsed_s'],previous['elapsed_s'])
                for p,q in zip(previous['players'],current['players']):
                    self.assertLessEqual(math.hypot(q[1]-p[1],q[2]-p[2]),7.2*DT+1e-8)
                    self.assertTrue(0<=q[1]<=105 and 0<=q[2]<=68)
                self.assertLessEqual(math.dist(previous['ball'],current['ball']),14*DT+1e-8)

    def test_offside_rejected(self):
        f,m = sample()
        with self.assertRaises(ValueError): simulate(f,m,'pass:H03')

    def test_clear_lane_received_and_blocked_lane_intercepted(self):
        f,m = sample()
        f['players'][0][1:3] = [10,34]
        f['players'][1][1:3] = [30,34]
        f['players'][2][1:3] = [20,60]
        for p in f['players'][3:]: p[1:3] = [95,60]
        clear = simulate(f,m,'pass:H02')
        self.assertEqual(clear['scenarios'][1]['outcome'],'received')
        f['players'][-1][1:3] = [20,34]
        blocked = simulate(f,m,'pass:H02')
        self.assertEqual(blocked['scenarios'][1]['outcome'],'intercepted')
        self.assertEqual(blocked['scenarios'][1]['controller_id'],'A03')

    def test_four_second_horizon_does_not_claim_reception(self):
        f,m = sample()
        f['players'][0][1:3] = [1,1]
        f['players'][1][1:3] = [90,1]
        for p in f['players'][2:]: p[1:3] = [104,67]
        r = simulate(f,m,'pass:H02')
        self.assertEqual(r['scenarios'][1]['outcome'],'unresolved')
