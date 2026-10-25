"""A's frozen cases: structural contracts plus semantic/citation/staleness checks."""
import copy
import json
import math
from pathlib import Path
import subprocess
import unittest

from contracts import candidate_set_id, check_exchange, check_snapshot, data_version, make_snapshot
from contracts.export_fixtures import response_example
from decision.engine import analyze
from decision.outcome import compare
from decision.rollout import simulate
from generate import Match, build_metadata

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/contracts'


def read(path):
    return json.loads(path.read_text())


def validate_batch(items):
    result = subprocess.run(['node', str(ROOT / 'scripts/validate_contracts.mjs'), '--stdin'],
        input=''.join(json.dumps({'schema': name, 'value': value}) + '\n' for name, value in items),
        text=True, capture_output=True, cwd=ROOT)
    if result.returncode:
        raise AssertionError('Contract validator failed (run npm ci first): ' + result.stderr)
    results = [json.loads(line) for line in result.stdout.splitlines()]
    if len(results) != len(items):
        raise AssertionError('Validator did not check every supplied record')
    return results


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.match = read(FIXTURES / 'match.json')
        cls.metadata = cls.match['metadata']
        cls.cases = {name: {key: read(FIXTURES / ('case-' + name) / filename)
            for key, filename in [('snapshot', 'snapshot.json'), ('request', 'request.json'),
                                  ('response', 'response.example.json'), ('context', 'context.json')]}
            for name in ('a', 'b', 'c')}

    def test_fixed_cases_and_current_roster_pass_schema(self):
        items = [('contract.match', self.match), ('data.squads', read(ROOT / 'data/league/squads.json'))]
        for case in self.cases.values():
            items += [('contract.snapshot', case['snapshot']), ('contract.analysis_request', case['request']),
                      ('contract.analysis_response', case['response'])]
        for item, result in zip(items, validate_batch(items)):
            self.assertTrue(result['valid'], (item[0], result['errors']))

    def test_missing_fields_wrong_types_and_unsupported_public_fields_fail(self):
        base = self.cases['a']
        invalid = []
        def mutate(name, value, fn):
            value = copy.deepcopy(value)
            fn(value)
            invalid.append((name, value))
        for key in ('match_id', 'snapshot_id', 'actor_id', 't_ms', 'question', 'mode', 'language', 'profile'):
            mutate('contract.analysis_request', base['request'], lambda v, k=key: v.pop(k))
        for key, value in [('kind', 'observed'), ('weak_foot', 0), ('weak_foot', 6),
                           ('weak_foot', 2.5), ('preferred_foot', 'unknown')]:
            mutate('contract.analysis_request', base['request'], lambda v, k=key, x=value: v['profile'].update({k: x}))
        for key, value in [('snapshot_id', 'not-a-hash'), ('t_ms', -1), ('language', 'xx'),
                           ('actor_id', 'HOME-08'), ('mode', 'invalid')]:
            mutate('contract.analysis_request', base['request'], lambda v, k=key, x=value: v.update({k: x}))
        for key, value in [('status', 'unavailable'), ('value_gain', .3), ('success_pct', 75)]:
            mutate('contract.analysis_response', base['response'], lambda v, k=key, x=value: v.update({k: x}))
        for key, value in [('value_gain', .3), ('scenario_weight', .8), ('rollout_supported', True)]:
            mutate('contract.analysis_response', base['response'],
                   lambda v, k=key, x=value: next(c for c in v['candidates'] if c['type'] == 'carry').update({k: x}))
        mutate('contract.analysis_response', base['response'], lambda v: v.update(candidates=[]))
        mutate('contract.analysis_response', base['response'], lambda v: v.update(status='ready', explanation=None))
        mutate('contract.snapshot', base['snapshot'], lambda v: v['frame'].update(future_events=[]))
        mutate('contract.snapshot', base['snapshot'], lambda v: v['frame']['players'][0].__setitem__(1, 106))
        mutate('contract.snapshot', base['snapshot'], lambda v: v['attacking_direction'].update(AWAY=v['attacking_direction']['HOME']))
        for item, result in zip(invalid, validate_batch(invalid)):
            self.assertFalse(result['valid'], item)

    def test_all_five_response_statuses_and_unknown_profile(self):
        items = []
        for status in ('ready', 'partial', 'unknown', 'model_unavailable', 'error'):
            response = copy.deepcopy(self.cases['a']['response'])
            response['status'] = status
            if status == 'ready':
                response['explanation'] = {'mode': 'fan', 'text': 'Example explanation, not a model call.',
                    'cited_evidence_ids': [response['evidence'][0]['evidence_id']]}
            if status in ('unknown', 'error'):
                response.update(candidates=[], evidence=[])
            items.append(('contract.analysis_response', response))
        for foot in ('left', 'right', 'both', None):
            items.append(('contract.simulated_profile', {'profile_version': 'sim-1', 'kind': 'simulated',
                'preferred_foot': foot, 'weak_foot': None if foot is None else 2}))
        self.assertTrue(all(r['valid'] for r in validate_batch(items)))

    def test_fixed_hashes_exchange_and_computed_examples_are_reproducible(self):
        self.assertEqual(self.match['data_version'], data_version(self.metadata))
        for case in self.cases.values():
            check_exchange(case['request'], case['response'], case['snapshot'], self.metadata)
            self.assertEqual(case['snapshot'], make_snapshot(self.metadata, case['snapshot']['frame']))
            self.assertEqual(case['response'], response_example(case['snapshot'], self.metadata,
                case['request'], case['context']['actual_action_id']))

    def test_stale_versions_profiles_and_hashes_are_rejected(self):
        for key, value in [('snapshot_id', '0' * 16), ('data_version', 'gen-' + '0' * 16),
                           ('candidate_set_id', 'outcome-0.1:' + '0' * 16), ('profile_version', 'sim-2')]:
            case = copy.deepcopy(self.cases['a'])
            case['response'][key] = value
            with self.assertRaises(ValueError):
                check_exchange(case['request'], case['response'], case['snapshot'], self.metadata)
        case = copy.deepcopy(self.cases['a'])
        case['request']['profile'].update(preferred_foot='left', weak_foot=2)
        with self.assertRaisesRegex(ValueError, 'Candidate set mismatch'):
            check_exchange(case['request'], case['response'], case['snapshot'], self.metadata)
        for key, value in [('seed', 1), ('t_ms', 1)]:
            snapshot = copy.deepcopy(case['snapshot'])
            snapshot[key] = value
            with self.assertRaises(ValueError):
                check_snapshot(snapshot, self.metadata)

    def test_unknown_ball_owner_returns_unknown_without_fabricated_candidates(self):
        case = copy.deepcopy(self.cases['a'])
        frame = case['snapshot']['frame']
        frame['ball_owner_id'] = None
        snapshot = make_snapshot(self.metadata, frame)
        case['request']['snapshot_id'] = snapshot['snapshot_id']
        response = case['response']
        response.update(status='unknown', snapshot_id=snapshot['snapshot_id'], candidates=[], evidence=[])
        response['candidate_set_id'] = candidate_set_id(snapshot, case['request']['profile'], 'outcome-0.1', [], [])
        check_exchange(case['request'], response, snapshot, self.metadata)

    def test_event_type_requirements_and_source_radar_missing_values(self):
        with (ROOT / 'data/events.jsonl').open() as source:
            event = next(e for e in map(json.loads, source) if e['type'] == 'pass')
        items = [('data.event', event)]
        for field, value in [('outcome', 'goal'), ('recipient_id', 'ARS-01'), ('duration_ms', -1)]:
            item = copy.deepcopy(event)
            item[field] = value
            items.append(('data.event', item))
        item = copy.deepcopy(event)
        item.pop('recipient_id')
        items.append(('data.event', item))
        self.assertEqual([r['valid'] for r in validate_batch(items)], [True, False, False, False, False])
        roster = read(ROOT / 'data/league/squads.json')
        profile = next(p['sofascore'] for t in roster['teams'] for p in t['players']
                       if p['sofascore']['status'] == 'complete' and p['sofascore']['attribute_kind'] == 'outfield')
        missing = copy.deepcopy(profile)
        missing['attributes']['ATT'] = None
        partial = copy.deepcopy(missing)
        partial['status'] = 'partial'
        wrong_kind = copy.deepcopy(profile)
        wrong_kind['attribute_kind'] = 'goalkeeper'
        self.assertEqual([r['valid'] for r in validate_batch([
            ('data.sofascore_profile', v) for v in [profile, missing, partial, wrong_kind]])],
            [True, False, True, False])

    def test_cross_record_references_and_ranks_are_checked(self):
        def wrong_receiver(r):
            r['candidates'][0].update(action_id='pass:A01', type='pass')
        mutations = [lambda r: r['candidates'][0].update(evidence_ids=['missing']),
                     lambda r: r['evidence'].append(dict(r['evidence'][0])),
                     lambda r: r['candidates'].append(dict(r['candidates'][0])),
                     lambda r: r['candidates'][0].update(rank=99), wrong_receiver,
                     lambda r: r.update(explanation={'mode': 'fan', 'text': 'Fixture', 'cited_evidence_ids': ['missing']}),
                     lambda r: r.update(explanation={'mode': 'analyst', 'text': 'Fixture', 'cited_evidence_ids': []})]
        for change in mutations:
            case = copy.deepcopy(self.cases['a'])
            response = case['response']
            change(response)
            # Rehash to ensure the semantic guard, not merely the hash guard, rejects it.
            response['candidate_set_id'] = candidate_set_id(case['snapshot'], case['request']['profile'],
                'outcome-0.1', response['candidates'], response['evidence'])
            with self.assertRaises(ValueError):
                check_exchange(case['request'], response, case['snapshot'], self.metadata)

    def test_snapshot_references_are_checked_even_after_rehash(self):
        for change in [lambda f: f['players'].append(list(f['players'][0])),
                       lambda f: f.update(ball_owner_id='H14'),
                       lambda f: f.update(possession_team_id='AWAY'),
                       lambda f: f.update(period_ms=1)]:
            frame = copy.deepcopy(self.cases['a']['snapshot']['frame'])
            change(frame)
            with self.assertRaises(ValueError):
                check_snapshot(make_snapshot(self.metadata, frame), self.metadata)

    def test_revealing_actual_action_does_not_change_ranking_or_candidate_id(self):
        case = copy.deepcopy(self.cases['a'])
        response = case['response']
        for option in response['candidates']:
            option['is_actual'] = False
        self.assertEqual(response['candidate_set_id'], candidate_set_id(case['snapshot'], case['request']['profile'],
            'outcome-0.1', response['candidates'], response['evidence']))
        first = compare(case['snapshot']['frame'], self.metadata)
        self.assertEqual(first, compare(case['snapshot']['frame'], self.metadata))

    def test_three_cases_demonstrate_document_scenarios(self):
        teams = {p['player_id']: p['team_id'] for p in self.metadata['players']}
        for name, case in self.cases.items():
            frame, context = case['snapshot']['frame'], case['context']
            players = {p[0]: p for p in frame['players']}
            actor = players[frame['ball_owner_id']]
            opponents = [p for p in frame['players'] if teams[p[0]] != teams[actor[0]]]
            baseline = analyze(frame, self.metadata)
            focus = next(c for c in baseline['candidates'] if c['action_id'] == context['focus_action_id'])
            self.assertTrue(focus['feasible_by_rules'])
            rollout = simulate(frame, self.metadata, focus['action_id'])
            self.assertEqual(rollout['source_t_ms'], frame['t_ms'])
            if name == 'a':
                receiver = players[focus['receiver_id']]
                self.assertGreater(min(math.dist(receiver[1:3], p[1:3]) for p in opponents), 5)
                self.assertLess(focus['evidence'][0]['value'], 0)
                self.assertIn('intercepted', [s['outcome'] for s in rollout['scenarios']])
            elif name == 'b':
                self.assertEqual(context['actual_action_id'], 'shot:goal')
                self.assertIn('shot:goal', [c['action_id'] for c in compare(frame, self.metadata)['candidates']])
            else:
                self.assertLess(min(math.dist(actor[1:3], p[1:3]) for p in opponents), 3)
                actual = next(c for c in baseline['candidates'] if c['action_id'] == context['actual_action_id'])
                self.assertLess((players[actual['receiver_id']][1] - actor[1]) * baseline['direction'], 0)
                self.assertGreater((players[focus['receiver_id']][1] - actor[1]) * baseline['direction'], 0)
                self.assertLess(focus['evidence'][0]['value'], 0)
                self.assertGreater(actual['evidence'][0]['value'], focus['evidence'][0]['value'])

    def test_same_seed_reproduces_generated_data_and_version_tracks_inputs(self):
        simulations = [Match(20261019), Match(20261019)]
        for sim in simulations:
            for step in range(1, 101):
                sim.step(step)
        self.assertEqual(simulations[0].tracking(100), simulations[1].tracking(100))
        self.assertEqual(simulations[0].events, simulations[1].events)
        self.assertEqual(data_version(build_metadata(simulations[0])), data_version(build_metadata(simulations[1])))
        metadata = copy.deepcopy(self.metadata)
        metadata['seed'] += 1
        self.assertNotEqual(data_version(metadata), self.match['data_version'])
        metadata = copy.deepcopy(self.metadata)
        metadata['players'][0]['nationality'] = 'Changed fixture input'
        self.assertNotEqual(data_version(metadata), self.match['data_version'])


if __name__ == '__main__':
    unittest.main()
