"""Outcome-oriented comparisons with strict separation of pre-action and execution data."""
import json
import math
from pathlib import Path
from realism.model import Model
from .engine import analyze, distance, sigmoid
from .train_value import cell

ROOT=Path(__file__).resolve().parents[1]

class ValueModel:
    def __init__(self):
        path=Path(__file__).with_name('value-model.json')
        self.data=json.loads(path.read_text())
    def value(self,point,direction,horizon=10):
        point=[point[0] if direction==1 else 105-point[0],point[1]]
        return self.data['values_by_horizon'][horizon][cell(point)]

def compare(frame,metadata):
    baseline=analyze(frame,metadata)
    if baseline['status']!='ready': return baseline
    model=ValueModel();rates=Model();players={p[0]:p for p in frame['players']}
    actor=players[frame['ball_owner_id']];direction=baseline['direction']
    teams={p['player_id']:p['team_id'] for p in metadata['players']}
    opponents=[p for p in frame['players'] if teams[p[0]]!=teams[actor[0]]]
    nearest=min(distance(actor[1:3],p[1:3]) for p in opponents)
    speed=math.hypot(*actor[3:5]);current=model.value(actor[1:3],direction)
    action_state={'speed_mps':speed,'movement_heading_deg':math.degrees(math.atan2(actor[4],actor[3])) if speed>.2 else None,
        'nearest_defender_m':nearest,'under_pressure_3m':nearest<3,
        'body_orientation':None,'preferred_foot':None,'touch_stability':None,
        'known_source':'tracking speed/direction and proximity; movement direction is not body orientation'}
    options=[]
    def score(cid,kind,target,weight,provenance,eligible=True,receiver=None):
        success=model.value(target,direction,9)
        failure=-model.value(target,-direction,9)
        if kind=='shot': success=1.;failure=-model.value([105 if direction==1 else 0,34],-direction,9)
        # A three-point assumption envelope, NOT a confidence interval or outcome sampling.
        low=max(.01,weight-.15);high=min(.99,weight+.15)
        gain=lambda w:w*success+(1-w)*failure-current
        item={'action_id':cid,'type':kind,'target':target,'receiver_id':receiver,
              'eligible':eligible,'scenario_weight':weight,'weight_kind':provenance,
              'success_value':success,'failure_value':failure,'value_gain':gain(weight),
              'sensitivity_range':[gain(low),gain(high)],'weight_scenarios':[low,weight,high],
              'range_kind':'assumed_weight_sensitivity_not_confidence_interval'}
        options.append(item)
    for candidate in baseline['candidates']:
        margin=candidate['evidence'][0]['value']
        empirical=rates.pass_success(distance(actor[1:3],candidate['target']),nearest<3)
        weight=empirical*(.45+.55*sigmoid(margin/.45))
        score(candidate['action_id'],'pass',candidate['target'],weight,
              'real_ground_pass_rate_adjusted_by_unvalidated_lane_rule',candidate['feasible_by_rules'],candidate['receiver_id'])
    for name,dx,dy in [('forward',6*direction,0),('left',3*direction,-5),('right',3*direction,5)]:
        target=[max(.5,min(104.5,actor[1]+dx)),max(.5,min(67.5,actor[2]+dy))]
        clearance=min(distance(target,p[1:3]) for p in opponents)
        score('carry:'+name,'carry',target,max(.2,min(.95,.5+.08*(clearance-2))),
              'hand_defined_retention_assumption_not_trained_carry_probability')
    goal=[105 if direction==1 else 0,34]
    local_x=actor[1] if direction==1 else 105-actor[1]
    goal_distance=distance(actor[1:3],goal)
    if goal_distance<=35 and not next((p.get('position')=='GK' for p in metadata['players'] if p['player_id']==actor[0]),False):
        score('shot:goal','shot',goal,rates.shot_goal(local_x,actor[2]),
              'real_foot_shot_goal_frequency_by_distance_not_player_specific')
    score('hold:1s','hold',actor[1:3],max(.3,min(.98,.65+nearest*.035)),
          'hand_defined_one_second_retention_assumption_no_support_prediction')
    options.sort(key=lambda c:(not c['eligible'],-c['value_gain']))
    best=next(c for c in options if c['eligible'])
    return {'status':'ready','version':'outcome-0.1','t_ms':frame['t_ms'],'actor_id':actor[0],
        'action_state':action_state,'current_value':current,'candidates':options,
        'highest_model_action_id':best['action_id'],'score_unit':'risk_adjusted_possession_goal_value_proxy',
        'value_target':model.data['target'],'model_validation':model.data['validation'],
        'components':{'position_value':'trained_on_real_observed_goals_and_transitions',
                      'pass_and_shot_rates':'real_event_frequency_models',
                      'carry_hold_and_lane_response':'unvalidated_rules'},
        'limitations':['Ranking is exploratory, not a validated best-action recommendation.',
            'Values use a 10-action location-only model; turnover value is an assumed opponent restart at target.',
            'Scenario ranges are hand-selected sensitivity checks, NOT confidence intervals.',
            'Body orientation, preferred foot and first-touch stability are unknown.',
            'Observed outcome and future endpoint are not inputs to compare().']}

def execution(event,replay_at_ms,expected_weight=None):
    if event is None:return {'status':'unavailable','reason':'Action was cancelled or did not resolve.'}
    if replay_at_ms<event['available_at_ms']:
        return {'status':'pending','reason':'Outcome hidden until it is available in the replay.'}
    result={'status':'observed','type':event['type'],'outcome':event.get('outcome'),
        'event_id':event['event_id'],'available_at_ms':event['available_at_ms'],
        'observed_distance_m':distance(event['start_location'],event['end_location']),
        'duration_s':(event['end_ms']-event['start_ms'])/1000,
        'technical_quality_score':None,
        'unknown':['intended_target_accuracy','contact_quality','body_orientation','preferred_foot'],
        'interpretation':'Observed result and motion facts; not an expert technique grade or decision label.'}
    if event['type'] in ('pass','shot') and expected_weight is not None:
        successful=event.get('outcome')==('complete' if event['type']=='pass' else 'goal')
        result['outcome_minus_scenario_weight']=int(successful)-expected_weight
        result['residual_kind']='descriptive_surprise_under_assumptions_not_execution_skill'
    return result

def review_record(root,dataset,match_id,decision_id,replay_at_ms=None):
    if dataset not in ('league','realism-sample'):raise ValueError('Invalid dataset')
    import re
    if not re.fullmatch(r'[A-Za-z0-9-]+',match_id) or not re.fullmatch(r'd[0-9]{6}',decision_id):raise ValueError('Invalid identifiers')
    folder=root/'data'/dataset
    if dataset!='realism-sample':folder=folder/'matches'/match_id
    meta=json.loads((folder/'metadata.json').read_text())
    if meta['match_id']!=match_id:raise ValueError('Match mismatch')
    with (folder/'decisions.jsonl').open() as stream:
        record=next((r for r in map(json.loads,stream) if r['decision_id']==decision_id),None)
    if record is None:raise ValueError('Unknown decision')
    # Comparison receives only the frozen frame + metadata, never selected action or event result.
    result=compare(record['snapshot'],meta)
    selected=record['selected'];cid=None
    if selected['kind']=='pass':
        recipient=next(c['recipient_id'] for c in record['candidates'] if c['kind']=='pass' and c['recipient']==selected['recipient'])
        cid='pass:'+recipient
    elif selected['kind']=='shot':cid='shot:goal'
    else:cid='carry:forward'
    actual=next((c for c in result.get('candidates',[]) if c['action_id']==cid),None)
    with (folder/'events.jsonl').open() as stream:
        events=[json.loads(line) for line in stream]
    event=next((e for e in events if e.get('action_id')==record['action_id'] and e['type'] in ('pass','shot','carry')),None)
    if replay_at_ms is None:replay_at_ms=record['t_ms']
    if not isinstance(replay_at_ms,(int,float)) or not math.isfinite(replay_at_ms) or replay_at_ms<record['t_ms']:raise ValueError('Invalid replay time')
    result.update(match_id=match_id,decision_id=decision_id,synthetic=bool(meta.get('synthetic')),
        source_snapshot=record['snapshot'],actual_action_id=cid,
        actual_action_match='exact_recipient_or_shot' if selected['kind']!='carry' else 'carry_type_proxy_not_actual_path',
        actual_model_value_gain=actual['value_gain'] if actual else None,
        execution=execution(event,replay_at_ms,actual['scenario_weight'] if actual else None),
        outcome_available_at_ms=event['available_at_ms'] if event else None)
    return result
