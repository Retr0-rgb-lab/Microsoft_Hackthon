import copy
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import server
from model_service import narrate
from test_analysis_agent import inputs
from analysis_agent import build_report


class ModelServiceTests(unittest.TestCase):
    def test_custom_endpoint_and_evidence(self):
        report = build_report(*inputs())
        original = copy.deepcopy(report)
        prose = {'summary': 'Summary', 'first_half': 'First', 'second_half': 'Second'}
        result = {'status': 'completed', 'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': json.dumps(prose)}]}]}
        with patch('model_service.urlopen', return_value=io.StringIO(json.dumps(result))) as call:
            narrate(report, 'custom-model', 'secret', 'https://example.com/v1/')
        self.assertEqual(call.call_args.args[0].full_url, 'https://example.com/v1/responses')
        self.assertEqual(report['player_of_the_match'], original['player_of_the_match'])
        self.assertEqual(report['summary'], 'Summary')


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Path(self.temp.name) / '.local' / 'model-service.json'
        self.patch = patch.object(server, 'CONFIG', self.config)
        self.patch.start()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.patch.stop()
        self.temp.cleanup()

    def request(self, route, data=None, origin=None):
        req = urllib.request.Request(self.base + route,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type': 'application/json', **({'Origin': origin} if origin else {})})
        try:
            with urllib.request.urlopen(req) as result:
                return result.status, result.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def test_decision_analysis_agents_endpoint(self):
        from decision_analysis.input_adapter import NEUTRAL_PROFILE
        from decision_analysis.service import Repository
        repo = Repository()
        match = 'PL26-W01-MCI-CHE'
        record = repo.index(match)['records'][0]
        request = dict(match_id=match, snapshot_id=record['snapshot_id'], t_ms=record['t_ms'],
                       actor_id=record['actor_id'], question='Why not pass along this route?',
                       mode='fan', language='en', profile=copy.deepcopy(NEUTRAL_PROFILE))
        public, _ = repo.compare(request)
        body = {'request': request, 'candidate_set_id': public['candidate_set_id']}
        status, raw = self.request('/api/decision-analysis/agents', body)
        self.assertEqual(status, 200)
        answer = json.loads(raw)
        # No key is configured for the test, so the computed comparison stands
        # and the agent is reported as unavailable rather than replaced by a
        # fabricated answer.
        self.assertEqual(answer['status'], 'model_unavailable')
        self.assertIsNone(answer['explanation'])
        self.assertEqual(answer['agent_trace'], [])
        self.assertTrue(answer['candidates'])
        # A body that is not exactly the bound request is refused.
        self.assertEqual(self.request('/api/decision-analysis/agents', {'request': request})[0], 400)
        # A stale candidate set is refused rather than answered.
        self.assertEqual(self.request('/api/decision-analysis/agents',
                                       {**body, 'candidate_set_id': 'outcome-0.2:stale'})[0], 400)
        # Only same-origin JSON requests are accepted.
        self.assertEqual(self.request('/api/decision-analysis/agents', body, 'https://evil.example')[0], 403)
        # A spent daily cap still returns the comparison.
        with patch('server.claim_model_call', return_value=False):
            status, raw = self.request('/api/decision-analysis/agents', body)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)['status'], 'model_unavailable')

    def test_decision_and_rollout_endpoints(self):
        from test_decision import sample
        frame, metadata = sample()
        payload = {'frame': frame, 'metadata': metadata, 'mode': 'fan'}
        status, body = self.request('/api/decision', payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['status'], 'ready')
        status, body = self.request('/api/rollout', {**payload, 'action_id': 'pass:H02'})
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)['scenarios']), 4)
        self.assertEqual(self.request('/api/rollout', {**payload, 'action_id': 'pass:H03'})[0], 400)
        self.assertEqual(self.request('/api/rollout', payload, 'https://evil.example')[0], 403)

    def test_action_review_separates_prediction_and_observation(self):
        from test_decision import sample
        frame, metadata = sample()
        metadata.update(match_id='TEST-MATCH', synthetic=True)
        folder = Path(self.temp.name) / 'data/league/matches/TEST-MATCH'
        folder.mkdir(parents=True)
        (folder / 'metadata.json').write_text(json.dumps(metadata))
        record = {'decision_id':'d000001','snapshot':frame,'t_ms':20000,'action_id':'a1',
                  'selected':{'kind':'pass','recipient':1},
                  'candidates':[{'kind':'pass','recipient':1,'recipient_id':'H02'}]}
        event = {'type':'pass','event_id':'e1','action_id':'a1','start_ms':20000,
                 'end_ms':22000,'available_at_ms':22000,'start_location':[50,34],
                 'end_location':[65,20],'outcome':'complete'}
        (folder / 'decisions.jsonl').write_text(json.dumps(record)+'\n')
        (folder / 'events.jsonl').write_text(json.dumps(event)+'\n')
        data = {'dataset':'league','match_id':'TEST-MATCH','decision_id':'d000001'}
        with patch.object(server, 'ROOT', Path(self.temp.name)):
            status, before = self.request('/api/action-review', data)
            self.assertEqual(status,200)
            status, after = self.request('/api/action-review', {**data,'replay_at_ms':22000})
            self.assertEqual(status,200)
            before, after = json.loads(before), json.loads(after)
            self.assertEqual(before['execution']['status'],'pending')
            self.assertEqual(after['execution']['outcome'],'complete')
            self.assertEqual(before['candidates'],after['candidates'])
            self.assertEqual(self.request('/api/action-review', {**data,'match_id':'../private'})[0],400)
            self.assertEqual(self.request('/api/action-review', data, 'https://evil.example')[0],403)

    def test_settings_key_retention_clear_and_permissions(self):
        status, body = self.request('/api/model-settings', {'model': 'test', 'api_key': 'private-secret'})
        self.assertEqual(status, 200)
        self.assertNotIn(b'private-secret', body)
        self.assertTrue(json.loads(body)['has_key'])
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.request('/api/model-settings', {'model': 'other', 'api_key': ''})
        self.assertEqual(server.read_config()['api_key'], 'private-secret')
        status, _ = self.request('/api/model-settings', {'base_url': 'https://example.com/v1'})
        self.assertEqual(status, 400)
        self.request('/api/model-settings', {'clear_key': True})
        self.assertFalse(server.read_config()['api_key'])

    def test_origin_and_private_files(self):
        status, _ = self.request('/api/model-settings', {'model': 'test'}, 'https://evil.example')
        self.assertEqual(status, 403)
        for path in ('/.local/model-service.json', '/%2elocal/model-service.json', '/.git/config'):
            self.assertEqual(self.request(path)[0], 404)

    def test_invalid_match_and_missing_configuration(self):
        self.assertEqual(self.request('/api/match-summary', {'match_id': '../bad'})[0], 400)
        self.assertEqual(self.request('/api/match-summary', {'match_id': inputs()[0]['match_id']})[0], 400)

    def test_generation_and_provider_failure(self):
        metadata, summary, events = inputs()
        root = Path(self.temp.name)
        folder = root / 'data' / 'league' / 'matches' / metadata['match_id']
        folder.mkdir(parents=True)
        for name, data in [('metadata', metadata), ('summary', summary)]:
            (folder / f'{name}.json').write_text(json.dumps(data))
        (folder / 'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
        server.save_config({'model': 'test', 'api_key': 'private-secret'})
        with patch.object(server, 'ROOT', root), patch.object(server, 'narrate') as model:
            status, body = self.request('/api/match-summary', {'match_id': metadata['match_id']})
            self.assertEqual(status, 200)
            model.assert_called_once()
            saved = (folder / 'analysis.json').read_text()
            self.assertNotIn('private-secret', saved)
            model.side_effect = RuntimeError('private-secret')
            status, body = self.request('/api/match-summary', {'match_id': metadata['match_id']})
            self.assertEqual(status, 502)
            self.assertNotIn(b'private-secret', body)
            self.assertEqual((folder / 'analysis.json').read_text(), saved)
