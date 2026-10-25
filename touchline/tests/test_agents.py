import copy
import json
import unittest
from unittest.mock import patch
from decision.agents import run_team, ROLES
from test_decision import sample

CONFIG = {'model':'test-model','api_key':'secret-test-key','base_url':'https://example.com/v1'}


def scripted_transport(fail=None, invalid_ref=False):
    requests = []
    def transport(payload):
        requests.append(copy.deepcopy(payload))
        role = next(r for r,prompt in ROLES.items() if payload['instructions'].endswith(prompt))
        if role == fail: raise RuntimeError('provider secret body')
        outputs = [x for x in payload['input'] if x.get('type')=='function_call_output']
        args = {}
        if role == 'coordinator' and len(outputs)<3:
            name = 'delegate'; args = {'agent':['attack','defense','audit'][len(outputs)]}
        elif not outputs:
            name = {'attack':'evaluate_options','defense':'simulate_pass','audit':'check_evidence'}[role]
            if role == 'defense': args = {'action_id':'pass:H02'}
        else:
            value = {'answer':role+' reviewed the available model evidence.', 'action_id':'pass:H02',
                     'evidence_ids':['invented' if invalid_ref else 'pass:H02:value'],
                     'caveats':['Heuristic model; no real probability claim.']}
            return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
        return {'status':'completed','output':[{'type':'function_call','call_id':role+str(len(outputs)),
                                                'name':name,'arguments':json.dumps(args)}]}
    return transport,requests


class AgentsTests(unittest.TestCase):
    def test_requested_language_reaches_all_agent_contexts(self):
        f,m = sample(); transport,requests = scripted_transport()
        r = run_team(f,m,'为什么传球？','fan',CONFIG,transport,language='zh')
        self.assertEqual(r['status'],'complete')
        self.assertTrue(all('Response language: Simplified Chinese.' in p['instructions'] for p in requests))
        with self.assertRaises(ValueError):
            run_team(f,m,'Why?','fan',CONFIG,transport,language='invalid')

    def test_missing_config_never_calls_provider(self):
        f,m = sample()
        with patch('decision.agents.urlopen') as network:
            r = run_team(f,m,'Why pass?','fan',{})
        self.assertEqual(r['status'],'not_configured')
        self.assertFalse(r['is_multi_agent']); network.assert_not_called()

    def test_four_contexts_actual_handoffs_and_tools(self):
        f,m = sample(); f['future_events'] = ['UNSEEN_FUTURE_GOAL']
        transport,requests = scripted_transport()
        r = run_team(f,m,'Why pass?','fan',CONFIG,transport)
        self.assertEqual(r['status'],'complete')
        self.assertTrue(r['is_multi_agent']); self.assertEqual(r['model_requests'],10)
        self.assertEqual([t['target'] for t in r['trace'] if t['event']=='handoff'],['attack','defense','audit'])
        self.assertTrue(any(t.get('tool')=='simulate_pass' for t in r['trace']))
        audit_request = next(p for p in requests if p['instructions'].endswith(ROLES['audit']))
        self.assertIn('defense',audit_request['input'][0]['content'])
        self.assertNotIn('UNSEEN_FUTURE_GOAL',json.dumps(requests))
        self.assertNotIn('secret-test-key',json.dumps(r))
        self.assertIn('pass:H02:rollout',r['evidence'])

    def test_failure_preserves_other_specialists(self):
        f,m = sample(); transport,_ = scripted_transport(fail='defense')
        r = run_team(f,m,'Why pass?','fan',CONFIG,transport)
        self.assertEqual(r['status'],'partial')
        self.assertFalse(r['is_multi_agent'])
        self.assertEqual(r['agent_outputs']['defense']['status'],'failed')
        self.assertEqual(r['agent_outputs']['audit']['status'],'complete')
        self.assertNotIn('provider secret body',json.dumps(r))

    def test_fabricated_references_are_not_published(self):
        f,m = sample(); transport,_ = scripted_transport(invalid_ref=True)
        r = run_team(f,m,'Why pass?','fan',CONFIG,transport)
        self.assertEqual(r['status'],'failed')
        self.assertNotIn('final',r)

    def test_early_coordinator_answer_is_rejected(self):
        f,m = sample()
        def transport(payload):
            return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({
                'answer':'All done','action_id':None,'evidence_ids':['model:limitations'],'caveats':[]})}]}]}
        r = run_team(f,m,'Why pass?','fan',CONFIG,transport)
        self.assertEqual(r['status'],'failed'); self.assertFalse(r['is_multi_agent'])

    def test_round_budget_stops_repeated_calls(self):
        f,m = sample()
        def transport(payload):
            return {'status':'completed','output':[{'type':'function_call','call_id':'x','name':'unknown','arguments':'{}'}]}
        r = run_team(f,m,'Why pass?','fan',CONFIG,transport)
        self.assertEqual(r['status'],'failed'); self.assertEqual(r['model_requests'],5)
