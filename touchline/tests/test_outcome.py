import copy
import json
import math
import unittest
from pathlib import Path
from decision.outcome import compare, execution, review_record
from decision.train_value import fit, cell
from test_decision import sample

ROOT=Path(__file__).resolve().parents[1]

class OutcomeTests(unittest.TestCase):
    def test_comparison_contains_cross_action_options(self):
        f,m=sample();r=compare(f,m)
        self.assertTrue({'pass','carry','hold'} <= {c['type'] for c in r['candidates']})
        f['players'][0][1]=90
        self.assertIn('shot',{c['type'] for c in compare(f,m)['candidates']})

    def test_future_labels_and_endpoints_do_not_change_preaction_scores(self):
        f,m=sample();first=compare(f,m)
        f.update(actual_outcome='goal',end_location=[105,34],future_events=[{'outcome':'goal'}])
        self.assertEqual(first,compare(f,m))

    def test_unknown_attributes_and_ranges_are_honest(self):
        f,m=sample();r=compare(f,m)
        for key in ('body_orientation','preferred_foot','touch_stability'):
            self.assertIsNone(r['action_state'][key])
        for c in r['candidates']:
            self.assertTrue(math.isfinite(c['value_gain']))
            self.assertLessEqual(c['sensitivity_range'][0],c['sensitivity_range'][1])
            self.assertIn('not_confidence',c['range_kind'])

    def test_execution_hidden_until_available(self):
        e={'type':'pass','event_id':'e1','available_at_ms':2000,'start_ms':1000,'end_ms':2000,
           'start_location':[10,20],'end_location':[20,20],'outcome':'complete'}
        hidden=execution(e,1999,.8)
        self.assertEqual(hidden['status'],'pending');self.assertNotIn('outcome',hidden)
        e['outcome']='intercepted';self.assertEqual(hidden,execution(e,1999,.8))
        visible=execution(e,2000,.8)
        self.assertIsNone(visible['technical_quality_score'])
        self.assertAlmostEqual(visible['outcome_minus_scenario_weight'],-.8)

    def test_value_training_uses_goal_outcomes(self):
        base={'cell':cell([95,34]),'kind':'shot','goal':False}
        before=fit([base]*30)['values_by_horizon'][-1][base['cell']]
        after=fit([{**base,'goal':True}]*30)['values_by_horizon'][-1][base['cell']]
        self.assertGreater(after,before)

    def test_record_review_does_not_rescore_when_outcome_revealed(self):
        folder=ROOT/'data/league-validated/matches'
        if not folder.exists(): self.skipTest('Optional generated league unavailable')
        match=sorted(folder.iterdir())[0].name
        with (folder/match/'decisions.jsonl').open() as stream:
            d=json.loads(stream.readline())
        before=review_record(ROOT,'league-validated',match,d['decision_id'])
        after=review_record(ROOT,'league-validated',match,d['decision_id'],6000000)
        self.assertEqual(before['candidates'],after['candidates'])
        self.assertEqual(before['execution']['status'],'pending')
        self.assertEqual(after['execution']['status'],'observed')

    def test_path_traversal_rejected(self):
        with self.assertRaises(ValueError):review_record(ROOT,'league-validated','../private','d000001')
