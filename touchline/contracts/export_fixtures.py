"""Export the three pinned development cases: python3 -m contracts.export_fixtures.

Responses are computed contract EXAMPLES, not responses from the legacy HTTP API.
No model calls or network access. Re-exporting requires local data/decisions.jsonl.
"""
import json
from pathlib import Path

from decision.engine import analyze
from decision.outcome import compare
from .model import candidate_set_id, check_exchange, make_match, make_snapshot

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tests/fixtures/contracts'
CASES = [
    ('A', 'd000001', 'pass:H09', 'pass:H11', 'Why not pass to the apparently open teammate?'),
    ('B', 'd000322', 'shot:goal', 'pass:H09', 'Why shoot instead of making one more pass?'),
    ('C', 'd000029', 'pass:A08', 'pass:A09', 'Why pass backward instead of forward under pressure?'),
]


def response_example(snapshot, metadata, request, actual_action):
    frame = snapshot['frame']
    comparison = compare(frame, metadata)
    lanes = {c['action_id']: c for c in analyze(frame, metadata)['candidates']}
    evidence, candidates = [], []
    rank = 0
    for index, c in enumerate(comparison['candidates'], 1):
        evidence_id = f'ev-option-{index:02d}'
        assumptions = ['preferred_foot_not_considered', 'location_value_model_exploratory']
        if c['type'] == 'pass':
            margin = lanes[c['action_id']]['evidence'][0]['value']
            opportunity = 'Move possession to an active teammate.'
            risk = ('A defender can reach the passing lane before the ball under the lane rule.'
                    if margin < 0 else 'Defender reactions and receiver control remain uncertain.')
            value = f'Minimum defender arrival margin: {margin:.4f} s; eligible: {str(c["eligible"]).lower()}.'
            assumptions.append('lane_rule_unvalidated')
        elif c['type'] == 'shot':
            opportunity = 'Use the current shooting window.'
            risk = 'Shooting ends the current possession opportunity if the attempt fails.'
            value = 'Actor is inside the model shooting range; eligibility is geometric.'
            assumptions.append('population_shot_frequency_not_individual_skill')
        elif c['type'] == 'carry':
            opportunity = 'Move the ball toward the candidate carrying target.'
            risk = 'Retention and defender response are hand-defined assumptions.'
            value = 'Candidate target is projected from the current position and attacking direction.'
            assumptions.append('carry_retention_unvalidated')
        else:
            opportunity = 'Keep possession briefly while preserving current options.'
            risk = 'Support movement and changing pressure are not predicted.'
            value = 'Holding is a one-second retention assumption from current defender proximity.'
            assumptions.append('hold_retention_unvalidated')
        if not c['eligible']:
            risk = 'Receiver is offside at release under the geometric eligibility rule.'
        evidence.append({'evidence_id': evidence_id, 'kind': 'computed',
                         'source': 'outcome.compare', 'value': value})
        if c['eligible']:
            rank += 1
        candidates.append({'action_id': c['action_id'], 'type': c['type'],
            'is_actual': c['action_id'] == actual_action, 'eligible': c['eligible'],
            'opportunity': opportunity, 'main_risk': risk,
            'rank': rank if c['eligible'] else None, 'evidence_ids': [evidence_id],
            'assumptions': assumptions, 'rollout_supported': c['type'] == 'pass' and c['eligible']})
    return {'status': 'model_unavailable', 'snapshot_id': snapshot['snapshot_id'],
        'candidate_set_id': candidate_set_id(snapshot, request['profile'], comparison['version'], candidates, evidence),
        'data_version': snapshot['data_version'], 'profile_version': request['profile']['profile_version'],
        'candidates': candidates, 'evidence': evidence, 'explanation': None, 'agent_trace': [],
        'limitations': ['Contract example only: no language model was called.',
                       'Preferred foot was not considered; the simulated profile is unknown.',
                       *comparison['limitations']]}


def main():
    metadata = json.loads((ROOT / 'data/metadata.json').read_text())
    needed = {c[1] for c in CASES}
    records = {}
    with (ROOT / 'data/decisions.jsonl').open() as source:
        for line in source:
            record = json.loads(line)
            if record['decision_id'] in needed:
                records[record['decision_id']] = record
    if needed != records.keys():
        raise ValueError('Pinned decisions missing; regenerate the documented seed before exporting')
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    write(OUT / 'match.json', make_match(metadata))
    for name, decision, actual, focus, question in CASES:
        record = records[decision]
        selected = record['selected']
        if selected['kind'] == 'pass':
            selected_id = 'pass:' + next(c['recipient_id'] for c in record['candidates']
                if c['kind'] == 'pass' and c['recipient'] == selected['recipient'])
        else:
            selected_id = {'shot': 'shot:goal', 'carry': 'carry:forward'}[selected['kind']]
        if selected_id != actual:
            raise ValueError('Pinned actual action changed; review case selection')
        snapshot = make_snapshot(metadata, record['snapshot'])
        request = {'match_id': metadata['match_id'], 'snapshot_id': snapshot['snapshot_id'],
            't_ms': snapshot['t_ms'], 'actor_id': record['player_id'], 'question': question,
            'mode': 'fan', 'language': 'en', 'profile': {'profile_version': 'sim-1',
                'kind': 'simulated', 'preferred_foot': None, 'weak_foot': None}}
        response = response_example(snapshot, metadata, request, actual)
        check_exchange(request, response, snapshot, metadata)
        folder = OUT / f'case-{name.lower()}'
        write(folder / 'snapshot.json', snapshot)
        write(folder / 'request.json', request)
        write(folder / 'response.example.json', response)
        write(folder / 'context.json', {'case': name, 'source': 'data/decisions.jsonl',
            'decision_id': decision, 'actual_action_id': actual, 'focus_action_id': focus,
            'note': 'Presentation context only. Do not pass actual_action_id or future events to compare().'})


if __name__ == '__main__':
    main()
