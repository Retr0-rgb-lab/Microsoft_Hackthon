import copy
import json
import math
import os
import subprocess
import threading
import unittest
import urllib.request
import urllib.error
from collections import Counter
from pathlib import Path
from unittest.mock import patch
import server
from decision_analysis.service import Repository
from decision_analysis.counterfactual import simulate
from decision_analysis.selection import representative
from decision_analysis.metrics import FEATURE_UNITS
from decision_analysis.comparison import compare_actions

ROOT=Path(__file__).resolve().parents[1]

def schema(name,value):
    result=subprocess.run([os.environ.get('NODE_BINARY','node'),str(ROOT/'scripts/validate_decision_analysis.mjs'),'--stdin'],
        input=json.dumps({'schema':name,'value':value})+'\n',text=True,capture_output=True,check=True)
    return json.loads(result.stdout)

class DecisionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo=Repository();cls.match='PL26-W01-MCI-CHE'
        cls.record=next(iter(cls.repo.records(cls.match).values()));cls.snap=cls.record['snapshot'];cls.request=cls.repo.request_for(cls.snap)
        cls.public,cls.private=cls.repo.compare(cls.request);cls.meta=cls.repo.metadata(cls.match)

    def test_extension_json_is_complete_and_valid_while_public_stays_rank_text_only(self):
        document=self.repo.document(self.request)
        self.assertTrue(schema('analysis_response',document)['valid'])
        self.assertTrue(schema('context_response',self.repo.bundle(self.request))['valid'])
        self.assertEqual(document['source']['dataset'],'league');self.assertFalse(document['assessment']['actual_action_included'])
        self.assertEqual(len(FEATURE_UNITS),30)
        for candidate in document['candidates']:
            if candidate['eligible']:
                self.assertEqual(set(candidate['features']),set(FEATURE_UNITS))
                self.assertAlmostEqual(sum(candidate['outcome_probabilities'].values()),1)
                d=candidate['decomposition'];self.assertAlmostEqual(candidate['q2'],d['immediate']+d['continuation']-d['risk'])
                self.assertTrue(candidate['judgment']['counterfactual_available'])
        self.assertAlmostEqual(sum(c['relative_score'] or 0 for c in document['candidates']),100)
        self.assertFalse(any('q2' in c or 'relative_score' in c for c in document['public']['candidates']))
        bad=copy.deepcopy(document);bad['future_goal']=True;self.assertFalse(schema('analysis_response',bad)['valid'])

    def test_all_supported_action_families_have_bound_reproducible_counterfactuals(self):
        for kind in ('pass','carry','shot'):
            action=next(c for c in self.public['candidates'] if c['eligible'] and c['type']==kind)
            # Original canonical contract remains pass-only; extension does not change it.
            self.assertEqual(action['rollout_supported'],kind=='pass')
            a=simulate(self.request,self.public,self.private,self.snap,self.meta,action['action_id'],self.public['candidate_set_id'])
            b=simulate(self.request,self.public,self.private,self.snap,self.meta,action['action_id'],self.public['candidate_set_id'])
            self.assertEqual(a,b);self.assertEqual(a['action_type'],kind);self.assertTrue(schema('counterfactual_response',a)['valid'])
            self.assertTrue(a['ranking_unchanged']);self.assertEqual(len(a['scenarios']),4)
            for scenario in a['scenarios']:
                self.assertEqual(scenario['frames'][0]['players'],self.snap['frame']['players'])
                self.assertEqual(scenario['frames'][0]['ball'],self.snap['frame']['ball'])
                self.assertLessEqual(scenario['duration_s'],4)
                for frame in scenario['frames'][1:]:
                    self.assertTrue(all(0<=p[1]<=105 and 0<=p[2]<=68 and math.hypot(*p[3:5])<=7.200001 for p in frame['players']))
                    self.assertTrue(all(math.isfinite(v) for v in frame['ball']))
        with self.assertRaises(ValueError):simulate(self.request,self.public,self.private,self.snap,self.meta,'hold:1s',self.public['candidate_set_id'])
        with self.assertRaises(ValueError):simulate(self.request,self.public,self.private,self.snap,self.meta,'shot:goal','outcome-3.0:0000000000000000')

    def test_counterfactual_never_runs_past_current_period_boundary(self):
        from contracts import make_snapshot
        meta=copy.deepcopy(self.meta);frame=copy.deepcopy(self.snap['frame'])
        period=next(p for p in meta['periods'] if p['period']==frame['period'])
        frame['t_ms']=period['start_ms']+period['duration_ms']-200;frame['period_ms']=period['duration_ms']-200
        frame['frame_id']=int(frame['t_ms']*meta['tracking_hz']/1000)
        snap=make_snapshot(meta,frame);request={**self.request,'snapshot_id':snap['snapshot_id'],'t_ms':snap['t_ms']}
        public,private=compare_actions(request,snap,meta,self.repo.model_for(self.match),self.repo.index(self.match)['ratings'])
        for kind in ('pass','carry','shot'):
            action=next(c['action_id'] for c in public['candidates'] if c['eligible'] and c['type']==kind)
            result=simulate(request,public,private,snap,meta,action,public['candidate_set_id'])
            for scenario in result['scenarios']:self.assertLessEqual(scenario['duration_s'],.2+1e-9)
        name='matches/'+self.match+'/metadata.json';saved=self.repo.signatures[name]
        try:
            self.repo.signatures[name]=(-1,-1)
            with patch('decision_analysis.service.hashlib.sha256') as fake:
                fake.return_value.hexdigest.return_value='modified-live-source'
                with self.assertRaises(ValueError):self.repo.check_live_source(self.match)
        finally:self.repo.signatures[name]=saved

    def test_actual_overlay_never_enters_analysis_and_profile_remains_neutral(self):
        before=self.repo.document(self.request);actual=self.repo.actual(self.request,self.public)
        after=self.repo.document(self.request);self.assertEqual(before,after)
        self.assertEqual(actual['response']['candidate_set_id'],before['candidate_set_id'])
        request=copy.deepcopy(self.request);request['profile'].update(preferred_foot='left',weak_foot=1)
        changed=self.repo.document(request);self.assertNotEqual(changed['candidate_set_id'],before['candidate_set_id'])
        self.assertEqual([c['q2'] for c in before['candidates']],[c['q2'] for c in changed['candidates']])
        for forbidden in ('actual_outcome','end_location','future_goal'):
            bad={**self.request,forbidden:True}
            with self.assertRaises(ValueError):self.repo.compare(bad)

    def test_representative_sampling_enforces_players_teams_possessions_and_spacing(self):
        for match in self.repo.matches:
            index=self.repo.index(match);rows=index['records']
            if not rows or 'analyzable' not in rows[0]:continue
            ids=representative(rows);self.assertEqual(ids,index['representative_ids']);selected=[r for r in rows if r['decision_id'] in ids]
            self.assertLessEqual(len(selected),20);self.assertTrue(all(v<=2 for v in Counter(r['actor_id'] for r in selected).values()))
            self.assertTrue(all(v<=10 for v in Counter(r['team_id'] for r in selected).values()))
            self.assertEqual(len({r['possession_id'] for r in selected}),len(selected))
            for r in selected:
                self.assertTrue(r['analyzable'])
                for q in selected:
                    if r!=q and r['actor_id']==q['actor_id']:self.assertGreaterEqual(abs(r['t_ms']-q['t_ms']),30000)

    def test_source_is_current_and_mutated_metadata_or_source_cannot_silently_load(self):
        self.assertEqual(self.repo.metadata(self.match),json.loads((ROOT/'data/league/matches'/self.match/'metadata.json').read_text()))
        self.assertFalse(any(name.endswith('/analysis.json') for name in self.repo.signatures))
        for match in self.repo.matches:
            model=self.repo.model_for(match);self.assertIn(match,model['test_matches']);self.assertNotIn(match,model['fitting_matches']+model['calibration_matches'])
        with patch('decision_analysis.service.hashlib.sha256') as fake:
            fake.return_value.hexdigest.return_value='changed'
            with self.assertRaises(ValueError):Repository()
        altered=copy.deepcopy(self.meta);altered['seed']+=1
        with self.assertRaises(ValueError):compare_actions(self.request,self.snap,altered,self.repo.model_for(self.match),self.repo.index(self.match)['ratings'])

class DecisionHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.http.server_port);repo=Repository();cls.req=repo.request_for(next(iter(repo.records('PL26-W01-MCI-CHE').values()))['snapshot'])
    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.thread.join()
    def call(self,path,body=None,origin=None):
        request=urllib.request.Request(self.base+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json',**({'Origin':origin} if origin else {})})
        try:
            with urllib.request.urlopen(request) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:
            return error.code,None
    def test_new_api_does_not_replace_existing_decision_or_settings_routes(self):
        self.assertEqual(self.call('/api/model-settings')[0],200)
        self.assertEqual(self.call('/api/decision',{'invalid':True})[0],400)
        status,catalog=self.call('/api/decision-analysis/catalog');self.assertEqual(status,200);self.assertEqual(len(catalog['matches']),40)
        self.assertTrue(schema('catalog_response',catalog)['valid'])
        self.assertTrue(schema('index_response',self.call('/api/decision-analysis/index?match_id=PL26-W01-MCI-CHE')[1])['valid'])
        self.assertEqual(self.call('/api/decision-analysis/analyze',self.req)[0],200)
        self.assertEqual(self.call('/api/decision-analysis/analyze',self.req,'https://invalid.example')[0],403)
        self.assertEqual(self.call('/api/decision-analysis/index?match_id=../../.local')[0],404)
    def test_extension_and_legacy_rollout_are_separate_and_stale_ids_are_rejected(self):
        _,doc=self.call('/api/decision-analysis/analyze',self.req);body={'request':self.req,'candidate_set_id':doc['candidate_set_id'],'action_id':'shot:goal'}
        self.assertEqual(self.call('/api/decision-analysis/counterfactual',body)[0],200)
        self.assertEqual(self.call('/api/decision-analysis/rollout',body)[0],400)
        self.assertEqual(self.call('/api/decision-analysis/counterfactual',{**body,'candidate_set_id':'outcome-3.0:0000000000000000'})[0],400)
        self.assertEqual(self.call('/api/decision-analysis/actual',{'request':self.req,'candidate_set_id':doc['candidate_set_id']})[0],200)
        self.assertEqual(self.call('/api/decision-analysis/analyze',{**self.req,'actual_outcome':'goal'})[0],400)

if __name__=='__main__':unittest.main()
