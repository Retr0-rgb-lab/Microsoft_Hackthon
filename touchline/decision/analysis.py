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

from contracts.model import check_exchange, make_snapshot
from contracts.project import public_candidates, public_response


# A number the interface must not show: a decimal score, a percentage, or a
# "0.059 gain" style claim. The prompt forbids it; this catches it anyway.
_NUMERIC_CLAIM = re.compile(
    r'\b(?:value gain|gain|score|scenario weight)\b[^.]{0,24}?-?\d+(?:\.\d+)?'
    r'|\b\d+(?:\.\d+)?\s*%',
    re.IGNORECASE,
)

# The agent roles, in the order the team runs them.
ROLES = ('attack', 'defense', 'audit')


def numeric_claims(text):
    """Numeric score or percentage claims in the model's prose."""
    return sorted({match.group(0).strip() for match in _NUMERIC_CLAIM.finditer(text or '')})


def agent_trace(result):
    """The team trace in the contract's shape: role, tool, milliseconds, success."""
    trace = []
    for entry in result.get('trace', []):
        if entry.get('event') == 'tool_completed':
            trace.append({'agent': entry.get('agent'), 'tool': entry.get('tool'),
                          'ms': entry.get('elapsed_ms'), 'ok': True})
        elif entry.get('event') == 'failed':
            trace.append({'agent': entry.get('agent'), 'tool': None,
                          'ms': entry.get('elapsed_ms'), 'ok': False,
                          'reason': entry.get('reason')})
    return trace


def cited_evidence(result, candidates, evidence):
    """The evidence ids the answer cites, mapped onto the public registry.

    The team cites engine-level ids (``pass:H09:lane``). The public registry
    publishes one id per option (``ev-option-03``). A citation that belongs to
    a candidate is mapped onto that candidate's id; a citation about
    something else, such as the snapshot itself, is internal and is dropped
    rather than published.
    """
    final = result.get('final') or {}
    declared = final.get('evidence_ids') or result.get('evidence_ids') or []
    by_action = {}
    for candidate, item in zip(candidates, evidence):
        by_action.setdefault(candidate['action_id'], item['evidence_id'])
    known = {item['evidence_id'] for item in evidence}
    cited = []
    for evidence_id in declared:
        if evidence_id in known:
            if evidence_id not in cited:
                cited.append(evidence_id)
            continue
        # Engine ids look like "pass:H09:lane": the first two parts are the
        # action id. "snapshot:..." and "model:..." name something else and
        # stay internal.
        parts = evidence_id.split(':')
        action = ':'.join(parts[:2]) if len(parts) >= 3 else None
        mapped = by_action.get(action) if action else None
        if mapped and mapped not in cited:
            cited.append(mapped)
    return cited


def build_response(snapshot, metadata, request, agent_result=None, actual_action=None):
    """The contract response, with the agent answer folded in when there is one.

    The candidate set and the evidence are always computed. The explanation and
    the trace are added only when the team actually ran.
    """
    candidates, evidence, comparison = public_candidates(
        snapshot['frame'], metadata, actual_action=actual_action)
    limitations = ['Preferred foot was not considered; the simulated profile is unknown.',
                   *comparison['limitations']]
    explanation = None
    trace = []
    status = 'model_unavailable'

    if agent_result is not None:
        # The contract's status vocabulary is ready/partial/unknown/
        # model_unavailable/error. The team's own "complete" means the
        # specialists all finished, which is the contract's "ready".
        status = 'ready' if agent_result.get('status') == 'complete' else 'partial'
        text = agent_result.get('answer') or ''
        cited = cited_evidence(agent_result, candidates, evidence)
        explanation = {'mode': request['mode'], 'text': text, 'cited_evidence_ids': cited}
        trace = agent_trace(agent_result)
        claims = numeric_claims(text)
        if claims:
            status = 'partial'
            # The explanation object is closed by the schema, so the finding
            # goes into the limitations the interface already renders.
            limitations.append(
                'The answer quoted a model internal (' + ', '.join(claims) + '). Those are '
                'uncalibrated scores, not probabilities; the ranking and the wording are the '
                'supported form.')
        if not cited:
            status = 'partial'
            limitations.append('The answer cited no evidence from this candidate set.')

    response = public_response(
        snapshot, metadata, request, actual_action,
        status=status, explanation=explanation, agent_trace=trace, limitations=limitations,
        candidates=candidates, evidence=evidence)
    return response


def _decision_records(root, match_id):
    """The match's own decision records, in time order."""
    from pathlib import Path
    path = Path(root) / 'data' / 'league' / 'matches' / match_id / 'decisions.jsonl'
    if not path.is_file():
        raise ValueError('Unknown match.')
    with path.open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def resolve_snapshot(root, metadata, match_id, snapshot_id):
    """One exact snapshot, resolved on the server.

    The request carries a snapshot id, not a frame. The frame is looked up
    here, in the match's own decision records, and the id is checked against
    the one the client holds. A client therefore never holds the actual
    action, the outcome, or any future frame.
    """
    for record in _decision_records(root, match_id):
        snapshot = make_snapshot(metadata, record['snapshot'])
        if snapshot['snapshot_id'] == snapshot_id:
            return snapshot, record
    raise ValueError('Unknown or stale snapshot.')


def resolve_moment(root, metadata, match_id, t_ms):
    """The decision in force at ``t_ms``, resolved on the server.

    A moment is not always a decision point. The latest decision at or
    before the requested time is used, and its own time comes back with it,
    so the caller asks about the decision that was actually in force rather
    than about a moment that has no decision of its own.
    """
    best = None
    for record in _decision_records(root, match_id):
        if int(record['t_ms']) > int(t_ms):
            break
        best = record
    if best is None:
        raise ValueError('No decision before that moment.')
    return make_snapshot(metadata, best['snapshot']), best


def analyze(metadata, request, frame, agent_result=None, actual_action=None):
    """Build and check one analysis response.

    Raises ``ValueError`` when the exchange does not hold: a stale snapshot, a
    candidate set that does not match, a dangling citation. The caller turns
    that into a transport error rather than a fabricated response.
    """
    snapshot = make_snapshot(metadata, frame)
    request = {**request, 'frame': frame}
    response = build_response(snapshot, metadata, request, agent_result, actual_action)
    check_exchange(request, response, snapshot, metadata)
    return response
