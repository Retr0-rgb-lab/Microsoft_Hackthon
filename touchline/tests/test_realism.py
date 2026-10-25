import copy
import math
import unittest
from generate import Match
from realism.policy import candidates
from realism.model import Model
from realism.calibrate import records, fit

class RealismTests(unittest.TestCase):
    def scene(self):
        sim=Match(12)
        sim.owner=9; sim.possession_team=0
        sim.players[9].update(x=96,y=34)
        for i,p in enumerate(sim.players):
            if p['team']==1: p.update(x=99,y=5+(i-11)*2)
        sim.players[11].update(x=103,y=34)
        sim.players[1].update(x=50,y=34)
        return sim

    def test_offside_excluded_and_direction_mirrored(self):
        sim=self.scene(); sim.players[8].update(x=104,y=30)
        options=candidates(sim)
        self.assertNotIn(8,[o.get('recipient') for o in options])
        before=[(o['kind'],o.get('recipient'),o['weight']) for o in options]
        for p in sim.players: p['x']=105-p['x']; p['vx']=-p['vx']
        sim.period=2
        after=[(o['kind'],o.get('recipient'),o['weight']) for o in candidates(sim)]
        self.assertEqual(before,after)

    def test_near_goal_has_shot_and_backpass_suppressed(self):
        sim=self.scene()
        options=candidates(sim)
        self.assertIn('shot',[o['kind'] for o in options])
        back=next(o for o in options if o.get('recipient')==1)
        self.assertLess(back['weight'], .01)

    def test_goalkeeper_does_not_shoot(self):
        sim=self.scene(); sim.owner=0
        sim.players[0].update(x=96,y=34)
        self.assertNotIn('shot',[o['kind'] for o in candidates(sim)])

    def test_record_is_predecision_and_reproducible(self):
        sims=[self.scene(),self.scene()]
        for sim in sims: sim.choose_action()
        self.assertEqual(sims[0].decisions,sims[1].decisions)
        record=copy.deepcopy(sims[0].decisions[0])
        sims[0].players[9]['x']=1
        self.assertEqual(sims[0].decisions[0],record)
        self.assertNotIn('outcome',record)

    def test_calibration_filters_and_coordinates(self):
        e={'period':1,'play_pattern':{'name':'Regular Play'},'type':{'name':'Pass'},'location':[60,40],
           'pass':{'end_location':[80,40],'body_part':{'name':'Right Foot'},'height':{'name':'Ground Pass'}}}
        row=list(records([e]))[0]
        self.assertEqual(row['x'],52.5); self.assertEqual(row['distance'],17.5)
        e['period']=5; self.assertEqual(list(records([e])),[])

    def test_profile_provenance_and_probabilities(self):
        model=Model(); split=model.profile['provenance']['split']
        self.assertFalse(set(split['train'])&set(split['test']))
        for table in ('pass_success','shot_goal'):
            for cell in model.profile[table].values(): self.assertTrue(0<cell['probability']<1)
