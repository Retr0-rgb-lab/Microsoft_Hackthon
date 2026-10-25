"""Versioned agent-facing diagnostics extension; canonical public contract stays intact."""
import math
import copy
from .input_adapter import source_profile

VERSION = 'decision-analysis-1'
FEATURE_UNITS = dict(progress='m',y='m',vx='m/s',vy='m/s',ball_speed='m/s',distance='m',advance='m',lateral='m',
    duration='s',source_pressure='index',receiver_pressure='index',nearest_defender='m',closing_speed='m/s',
    lane_pressure='index',intercept_margin='s',goal_distance='m',goal_angle='rad',blockers='index',keeper_offset='m',
    target_speed='m/s',attack_ratio='ratio',passing_ratio='ratio',time_fraction='ratio',score_difference='goals',
    player_difference='players',receiver_nearest_defender='m',receiver_reachable='boolean_as_0_or_1',
    keeper_depth='m',keeper_cover='index',state_quality='exact_snapshot_indicator')


def conditions(snapshot, metadata):
    f=snapshot['frame'];actor=next((p for p in f['players'] if p[0]==f['ball_owner_id']),None)
    if actor is None:return None
    teams={p['player_id']:p['team_id'] for p in metadata['players']}
    opponents=sorted(({'player_id':p[0],'distance_m':math.dist(actor[1:3],p[1:3])} for p in f['players']
                      if teams[p[0]]!=teams[actor[0]]),key=lambda p:(p['distance_m'],p['player_id']))
    speed=math.hypot(*actor[3:5]);heading=math.degrees(math.atan2(actor[4],actor[3]))%360 if speed>.2 else None
    d=1 if snapshot['attacking_direction'][teams[actor[0]]]=='positive_x' else -1
    relative=math.degrees(math.atan2(d*actor[4],d*actor[3]))%360 if heading is not None else None
    labels=['Forward','Forward-right','Right','Backward-right','Backward','Backward-left','Left','Forward-left']
    return dict(player_id=actor[0],team_id=teams[actor[0]],speed_mps=speed,speed_kmh=3.6*speed,
        movement_heading_deg=heading,movement_label=labels[int(relative/45+.5)%8] if relative is not None else 'Stationary / slow',
        nearest_opponent=opponents[0] if opponents else None,under_pressure_3m=opponents[0]['distance_m']<3 if opponents else None,
        opponents_within_5m=sum(p['distance_m']<5 for p in opponents),ball_distance_m=math.dist(actor[1:3],f['ball'][:2]),
        attacking_direction=snapshot['attacking_direction'][teams[actor[0]]],body_orientation=None,
        provenance='observed_generator_snapshot; proximity includes opposing goalkeeper')


def analysis_document(request, public, private, snapshot, metadata, source, decision_id):
    """No historical selection/outcome argument. Actuals are a separate route."""
    by={c['action_id']:c for c in public['candidates']};rows=[]
    best=max((r['q'] for r in private.get('options',[]) if r.get('q') is not None),default=None)
    values=sorted((r['q'] for r in private.get('options',[]) if r.get('q') is not None),reverse=True)
    close_top=len(values)>1 and values[0]-values[1]<.005
    for r in private.get('options',[]):
        c=by[r['key']];supported=c['eligible'];f=r.get('features');q=r.get('q')
        rows.append(dict(action_id=r['key'],type=c['type'],eligible=supported,rank=c['rank'],recipient_id=r['recipient'],
            target=r['target'],planned_duration_s=r['duration'],mode=r['mode'],features=f,
            outcome_probabilities=r.get('probabilities'),q2=q,q1=r.get('one_step_q'),
            softmax_weight=r.get('softmax_weight'),relative_score=r.get('relative_score'),
            value_gap=None if q is None or best is None else max(0.,best-q),
            decomposition=None if q is None else dict(immediate=r['immediate'],continuation=r['continuation'],risk=r['risk']),
            judgment=dict(reason=c['opportunity'],risk=c['main_risk'],assumptions=c['assumptions'],evidence_ids=c['evidence_ids'],
                similar_to_best=q is not None and best-q<.005 and (q<best or close_top),
                comparison_tolerance=.005,counterfactual_available=supported and r['kind'] in ('pass','carry','shot'))))
    top=next((c['action_id'] for c in public['candidates'] if c['rank']==1),None)
    return dict(schema_version=VERSION,match_id=snapshot['match_id'],decision_id=decision_id,
        snapshot_id=snapshot['snapshot_id'],candidate_set_id=public['candidate_set_id'],data_version=snapshot['data_version'],
        source=source,request=copy.deepcopy(request),snapshot=snapshot,public=public,action_conditions=conditions(snapshot,metadata),
        player_source_profile=source_profile(next(p for p in metadata['players'] if p['player_id']==request['actor_id'])),
        model=dict(model_id=private.get('model_id'),evaluation_mode='two_step_Q2',temperature=private.get('temperature'),
            feature_units=FEATURE_UNITS,probability_basis='unvalidated_tactical_assumption',
            relative_score_meaning='softmax preference share within supported candidates, sum 100; not success or ability'),
        candidates=rows,assessment=dict(recommended_action_id=top,candidate_count=sum(c['eligible'] for c in public['candidates']),
            actual_action_included=False,similar_value_tolerance=.005,agent_available=False),
        limitations=public['limitations']+['Numerical metrics are research diagnostics, not validated real-football probabilities.',
            'The 0.005 similar-value tolerance is a versioned display assumption, not a calibrated error bound.'])
