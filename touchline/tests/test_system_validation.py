import unittest
from realism.evaluate_system import js_distance, sim_rows

class ValidationMetricsTests(unittest.TestCase):
    def test_identical_and_disjoint_histograms(self):
        self.assertEqual(js_distance([1,0],[1,0]),0)
        self.assertEqual(js_distance([1,0],[0,1]),1)

    def test_second_half_uses_attacking_direction(self):
        e={'type':'pass','pass_height':'ground','start_location':[20,34],
           'end_location':[40,34],'team_id':'HOME','period':2,'outcome':'complete'}
        r=list(sim_rows([e]))[0]
        self.assertTrue(r['backward'])
        self.assertEqual(r['x'],85)
        self.assertEqual(r['distance'],20)
