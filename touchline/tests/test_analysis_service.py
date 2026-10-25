"""The analysis service: the contract, wired to the live model.

The contract itself lives in ``contracts/``. This module connects it to the
running system: it builds the snapshot, asks the comparison for the public
candidates, asks the agent team for the explanation when a model is available,
and refuses to return anything that does not pass ``check_exchange``.

One check the schema cannot do lives here. A schema validates structure; it
cannot read prose. The model sometimes quotes a model internal ("value gain
around 0.059") in its answer, and a rule assumption dressed as a probability
is the one thing this contract exists to prevent. A response that does that is
marked ``partial`` and the claim is named, rather than reaching the interface
as if it were a probability.
"""
import json
import re
import subprocess
import unittest
from pathlib import Path

from contracts.model import check_exchange, make_snapshot

from decision.analysis import (
    analyze,
    build_response,
    cited_evidence,
    numeric_claims,
    resolve_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
MATCH = 'PL26-W01-BHA-MUN'
FOLDER = ROOT / 'data' / 'league' / 'matches' / MATCH


def fixture_case(name):
    """One of the pinned contract cases, straight from the fixtures.

    The pinned cases come from the top-level single-match sample
    (``data/decisions.jsonl``), not from a league match, so they are
    validated against ``data/metadata.json``.
    """
    return json.loads((ROOT / f'tests/fixtures/contracts/case-{name}/snapshot.json').read_text())


def fixture_metadata():
    return json.loads((ROOT / 'data/metadata.json').read_text())


class NumericClaimTests(unittest.TestCase):
    def test_a_model_internal_is_found(self):
        self.assertTrue(numeric_claims('a value gain of 0.059'))
        self.assertTrue(numeric_claims('it succeeds 75% of the time'))

    def test_geometry_is_not_a_claim(self):
        self.assertEqual(numeric_claims('the defender is 1.4 m away'), [])
        self.assertEqual(numeric_claims('reaches the ball 1.3 s earlier'), [])


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata = fixture_metadata()

    def request(self, snapshot):
        # The contract requires the actor to be the current ball owner.
        return {'match_id': snapshot['match_id'], 'snapshot_id': snapshot['snapshot_id'],
                't_ms': snapshot['t_ms'], 'actor_id': snapshot['frame']['ball_owner_id'],
                'question': 'Why not pass to the striker?',
                'mode': 'fan', 'language': 'en',
                'profile': {'profile_version': 'sim-1', 'kind': 'simulated',
                            'preferred_foot': None, 'weak_foot': None}}

    def test_the_response_satisfies_the_published_schema(self):
        snapshot = fixture_case('a')
        response = analyze(self.metadata, self.request(snapshot), snapshot['frame'])
        path = Path('/tmp/itg_schema_check.json')
        path.write_text(json.dumps(response, ensure_ascii=False))
        result = subprocess.run(
            ['node', 'scripts/validate_contracts.mjs', '--file', 'contract.analysis_response', str(path)],
            cwd=ROOT, capture_output=True, text=True)
        payload = json.loads(result.stdout)
        self.assertTrue(payload['valid'], payload['errors'])
        self.assertEqual(payload['errors'], [])

    def test_a_response_with_a_quoted_internal_still_satisfies_the_schema(self):
        snapshot = fixture_case('a')
        leaky = {'status': 'complete', 'answer': 'A value gain of 0.059 makes it best.',
                 'final': {'evidence_ids': []}, 'trace': []}
        response = analyze(self.metadata, self.request(snapshot), snapshot['frame'], leaky)
        self.assertEqual(response['status'], 'partial')
        self.assertTrue(any('not probabilities' in l for l in response['limitations']))
        path = Path('/tmp/itg_schema_check2.json')
        path.write_text(json.dumps(response, ensure_ascii=False))
        result = subprocess.run(
            ['node', 'scripts/validate_contracts.mjs', '--file', 'contract.analysis_response', str(path)],
            cwd=ROOT, capture_output=True, text=True)
        self.assertTrue(json.loads(result.stdout)['valid'])

    def test_the_model_being_down_still_returns_the_comparison(self):
        snapshot = fixture_case('a')
        response = analyze(self.metadata, self.request(snapshot), snapshot['frame'], None)
        self.assertEqual(response['status'], 'model_unavailable')
        self.assertTrue(response['candidates'])
        self.assertTrue(response['evidence'])
        self.assertEqual(response['explanation'], None)

    def test_engine_citations_map_onto_the_public_registry(self):
        candidates = [{'action_id': 'pass:H09', 'evidence_ids': ['ev-option-01']}]
        evidence = [{'evidence_id': 'ev-option-01'}]
        result = {'final': {'evidence_ids': ['pass:H09:lane', 'snapshot:abc', 'model:limitations']}}
        self.assertEqual(cited_evidence(result, candidates, evidence), ['ev-option-01'])

    def test_a_stale_snapshot_is_refused(self):
        snapshot = fixture_case('a')
        request = self.request(snapshot)
        request['snapshot_id'] = '0' * 16
        with self.assertRaises(ValueError):
            check_exchange(request, {'status': 'ready'}, snapshot, self.metadata)


if __name__ == '__main__':
    unittest.main()
