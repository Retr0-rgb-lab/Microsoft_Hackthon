"""The public projection of a comparison: what the interface is allowed to see.

The internal candidate objects carry value gains, scenario weights and
sensitivity ranges. Those are model internals, not probabilities, so the public
response keeps only the wording, the rank, the evidence ids and the assumptions.

This is the single place that projection happens, so the pinned contract
fixtures and the live service cannot drift apart.
"""
from decision.engine import analyze
from decision.outcome import compare

from .model import candidate_set_id


def public_candidates(frame, metadata, comparison=None, actual_action=None):
    """Project the comparison onto the contract's public candidate shape.

    Returns ``(candidates, evidence)``. The opportunity and the main risk are
    derived from the computed values, never written by a model.
    """
    comparison = comparison or compare(frame, metadata)
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
    return candidates, evidence, comparison


def public_response(snapshot, metadata, request, actual_action=None, status='model_unavailable',
                    explanation=None, agent_trace=None, limitations=None,
                    candidates=None, evidence=None):
    """A complete analysis response in the contract's shape.

    ``candidates`` and ``evidence`` may be passed in when the caller already
    has them, so the candidate set id and the fields always describe the same
    projection.
    """
    if candidates is None or evidence is None:
        candidates, evidence, comparison = public_candidates(
            snapshot['frame'], metadata, actual_action=actual_action)
    else:
        comparison = compare(snapshot['frame'], metadata)
    if limitations is None:
        limitations = ['Preferred foot was not considered; the simulated profile is unknown.',
                       *comparison['limitations']]
    return {
        'status': status,
        'snapshot_id': snapshot['snapshot_id'],
        'candidate_set_id': candidate_set_id(
            snapshot, request['profile'], comparison['version'], candidates, evidence),
        'data_version': snapshot['data_version'],
        'profile_version': request['profile']['profile_version'],
        'candidates': candidates,
        'evidence': evidence,
        'explanation': explanation,
        'agent_trace': agent_trace or [],
        'limitations': limitations,
    }
