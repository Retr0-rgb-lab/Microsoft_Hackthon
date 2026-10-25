import unittest
from player_heatmaps import Heatmaps

class HeatmapTests(unittest.TestCase):
    def test_boundaries_and_absent_players(self):
        maps = Heatmaps({'players': [{'player_id': 'H01'}, {'player_id': 'H12'}],
                         'duration_ms': 400, 'tracking_hz': 5,
                         'pitch': {'length_m': 105, 'width_m': 68}})
        maps.add({'t_ms': 0, 'players': [['H01', 105, 68, 0, 0]]})
        maps.add({'t_ms': 200, 'players': [['H12', 0, 0, 0, 0]]})
        maps.add({'t_ms': 400, 'players': [['H12', 0, 0, 0, 0]]})
        self.assertEqual(maps.frames, 2)
        self.assertEqual(maps.players['H01'][-1], 1)
        self.assertEqual(maps.players['H12'][0], 1)
        self.assertEqual(sum(maps.players['H01']), 1)
        self.assertEqual(sum(maps.players['H12']), 1)

    def test_incomplete_tracking_cannot_be_published(self):
        maps = Heatmaps({'players': [], 'duration_ms': 400, 'tracking_hz': 5})
        with self.assertRaises(ValueError):
            maps.write('/tmp')
