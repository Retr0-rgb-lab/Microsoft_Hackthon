"""End-to-end audit of fresh match files, coach analysis and real-event fit.

No parameters are fitted here. Real test matches and simulator seeds are immutable.
"""
import argparse
import hashlib
import json
import math
import random
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from .calibrate import records, summary
from .model import Model
from decision.engine import analyze
from decision.rollout import simulate

ROOT=Path(__file__).resolve().parents[1]


def lines(path):
    with path.open() as stream:
        for line in stream:
            if line.strip(): yield json.loads(line)


def sim_rows(events):
    for e in events:
        if e['type'] not in ('pass','carry','shot'): continue
        if e['type']=='pass' and e.get('pass_height')!='ground': continue
        start,end=e['start_location'],e['end_location']
        direction=1 if (e['team_id']=='HOME')==(e['period']==1) else -1
        x=start[0] if direction==1 else 105-start[0]
        ex=end[0] if direction==1 else 105-end[0]
        r={'kind':e['type'],'x':x,'y':start[1]}
        if r['kind']=='pass':
            r.update(distance=math.dist(start,end),backward=ex<x-1,
                     big_back=x>88 and ex<x-30,pressured=bool(e.get('under_pressure')),
                     success=e['outcome']=='complete')
        if r['kind']=='shot':
            r.update(distance=math.hypot(105-x,start[1]-34),success=e['outcome']=='goal')
        yield r


def distribution(rows,kind):
    bins=[0]*5
    for r in rows:
        if r['kind']==kind: bins[min(4,int(r['distance']//10))]+=1
    n=sum(bins)
    return [v/n for v in bins] if n else None


def js_distance(p,q):
    m=[(a+b)/2 for a,b in zip(p,q)]
    return math.sqrt(sum((a*math.log2(a/c) if a else 0)+(b*math.log2(b/c) if b else 0)
                         for a,b,c in zip(p,q,m) if c)/2)


def model_metrics(model,rows,kind,prior):
    group=[r for r in rows if r['kind']==kind]
    predictions=[model.pass_success(r['distance'],r['pressured']) if kind=='pass'
                 else model.shot_goal(r['x'],r['y']) for r in group]
    n=len(group)
    return {'n':n,'brier':sum((p-r['success'])**2 for p,r in zip(predictions,group))/n if n else None,
            'constant_train_prior_brier':sum((prior-r['success'])**2 for r in group)/n if n else None,
            'observed':sum(r['success'] for r in group)/n if n else None,
            'predicted_mean':sum(predictions)/n if n else None}


def paired_brier_interval(model, games, kind, prior):
    components=[]
    for rows in games:
        group=[r for r in rows if r['kind']==kind]
        delta=0.
        for r in group:
            probability=model.pass_success(r['distance'],r['pressured']) if kind=='pass' else model.shot_goal(r['x'],r['y'])
            delta+=(prior-r['success'])**2-(probability-r['success'])**2
        components.append((delta,len(group)))
    rng=random.Random(20261023)
    estimates=[]
    for _ in range(2000):
        sample=[rng.choice(components) for _ in components]
        n=sum(count for _,count in sample)
        if n: estimates.append(sum(delta for delta,_ in sample)/n)
    estimates.sort()
    return {'metric':'constant Brier minus fitted Brier; positive favors fitted',
            'resampling_unit':'match','bootstrap_replicates':2000,
            'ci95':[estimates[int(.025*len(estimates))],estimates[int(.975*len(estimates))]],
            'per_match':[{'brier_improvement_sum':delta,'n':n} for delta,n in components]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--league',type=Path,default=ROOT/'data/league')
    parser.add_argument('--stream',action='store_true',help='Analyze finished match folders while the league is generating')
    args=parser.parse_args()
    out=ROOT/'artifacts/realism';out.mkdir(parents=True,exist_ok=True)
    model=Model(); provenance=model.profile['provenance']; real=[];train=[];source_audit=[];real_games=[];real_seconds=0.;synthetic_seconds=0.
    splits=provenance['split']
    for source in provenance['sources']:
        raw=(ROOT/'.local/statsbomb'/f"{source['match_id']}.json").read_bytes()
        if hashlib.sha256(raw).hexdigest()!=source['sha256']: raise ValueError('Source checksum mismatch')
        events=json.loads(raw)
        assert len(events)==len({e['id'] for e in events})
        source_audit.append({'match_id':source['match_id'],'events':len(events),'unique_ids':True,'checksum':'verified'})
        if source['match_id'] in splits['test']:
            rows=list(records(events)); real.extend(rows); real_games.append(rows)
            for period in (1,2):
                timestamps=[]
                for e in events:
                    if e['period']==period:
                        hours,minutes,seconds=e['timestamp'].split(':')
                        timestamps.append(float(hours)*3600+float(minutes)*60+float(seconds))
                real_seconds+=max(timestamps)
        elif source['match_id'] in splits['train']: train.extend(records(events))
    assert not(set(splits['train'])&set(splits['test']))
    real_stats=summary(real);all_rows=[];games=[];totals=Counter();coach_errors=[];brier_sum=0.;brier_n=0;cancelled_counts=Counter();unavailable_snapshots=[]
    details=(out/'system-analysis.jsonl').open('w')
    try:
        plan=args.league/'fixtures.jsonl'
        if args.stream and not plan.exists(): plan=ROOT/'data/league/fixtures.jsonl'
        fixtures=list(lines(plan))
        for fixture in fixtures:
            folder=args.league/'matches'/fixture['match_id']
            deadline=time.monotonic()+1200
            if args.stream:
                while not (folder/'analysis.json').exists():
                    if time.monotonic()>deadline: raise TimeoutError('Waiting for generated match '+fixture['match_id'])
                    time.sleep(1)
            metadata=json.loads((folder/'metadata.json').read_text())
            synthetic_seconds+=metadata['duration_ms']/1000
            report=json.loads((folder/'analysis.json').read_text())
            assert report.get('status')=='complete' and report.get('match_id')==fixture['match_id'], 'Invalid post-match analysis'
            events=list(lines(folder/'events.jsonl'))
            cancellations={e['action_id']:e['reason'] for e in events if e['type']=='action_cancelled'}
            by_action={e['action_id']:e for e in events if e['type'] in ('pass','carry','shot') and 'action_id' in e}
            rows=list(sim_rows(events));all_rows.extend(rows)
            counts=Counter();contexts=Counter();rollouts=Counter()
            for d in lines(folder/'decisions.jsonl'):
                counts['decisions']+=1
                frame=d['snapshot']
                assert frame['t_ms']==d['t_ms']
                event=by_action.get(d['action_id'])
                if event is None:
                    assert d['action_id'] in cancellations, 'Unexplained unresolved action'
                    cancelled_counts[cancellations[d['action_id']]]+=1
                    counts['cancelled_or_unresolved_actions']+=1
                else:
                    assert event['start_ms']==d['t_ms'], 'Decision/event timing mismatch'
                if event and event['type']=='pass':
                    predicted=d['selected']['success'];truth=event['outcome']=='complete'
                    brier_sum+=(predicted-truth)**2;brier_n+=1
                try:
                    result=analyze(frame,metadata)
                    counts['analyzed']+=1
                    if result['status']!='ready':
                        counts['unavailable']+=1;unavailable_snapshots.append((fixture['match_id'],d['t_ms']));continue
                    legal=[c for c in result['candidates'] if c['feasible_by_rules']]
                    counts['candidates']+=len(result['candidates']);counts['legal_candidates']+=len(legal)
                    for c in result['candidates']:
                        assert all(math.isfinite(c[k]) for k in ('feasibility_index','value_gain'))
                    counts['no_legal_pass']+=not bool(legal)
                    counts['all_passes_negative']+=bool(legal) and max(c['value_gain'] for c in legal)<0
                    byid={p[0]:p for p in frame['players']}
                    actor=byid[d['player_id']]
                    team=next(p['team_id'] for p in metadata['players'] if p['player_id']==d['player_id'])
                    forward=1 if (team=='HOME')==(frame['period']==1) else -1
                    ahead=sum(1 for c in legal if forward*(byid[c['receiver_id']][1]-actor[1])>1)
                    contexts['no_forward_legal_target']+=ahead==0
                    selected=d['selected']
                    if selected['kind']=='pass' and selected['advance'] < -1:
                        contexts['selected_backpass']+=1
                        contexts['backpass_with_no_forward_target']+=ahead==0
                    candidate_id=result.get('recommended_action_id')
                    if legal and counts['rollout_runs']<2:
                        rollout=simulate(frame,metadata,candidate_id)
                        counts['rollout_runs']+=1
                        for scenario in rollout['scenarios']:
                            rollouts[scenario['outcome']]+=1
                            assert all(f['elapsed_s']<=4.0001 for f in scenario['frames'])
                    details.write(json.dumps({'match_id':fixture['match_id'],'decision_id':d['decision_id'],
                        't_ms':d['t_ms'],'recommended_action_id':candidate_id,'legal_candidates':len(legal),
                        'forward_legal_targets':ahead,'max_pass_value':max((c['value_gain'] for c in legal),default=None),
                        'selected_kind':selected['kind']},separators=(',',':'))+'\n')
                except (ValueError,AssertionError,KeyError) as error:
                    coach_errors.append({'match_id':fixture['match_id'],'decision_id':d['decision_id'],'error':str(error)})
            totals.update(counts)
            games.append({'match_id':fixture['match_id'],'stats':summary(rows),'analysis':dict(counts),
                          'contexts':dict(contexts),'rollout_outcomes':dict(rollouts),
                          'postmatch_report':'present','tracking':fixture['tracking']})
            print(f"Analyzed {len(games)}/{len(fixtures)}: {fixture['match_id']} ({counts['analyzed']} snapshots)",flush=True)
    finally: details.close()
    assert [f['match_id'] for f in lines(args.league/'fixtures.jsonl')]==[f['match_id'] for f in fixtures], 'Generated fixture plan mismatch'
    simulated=summary(all_rows)
    real_scores={}
    for kind in ('pass','shot'):
        population=[r for r in train if r['kind']==kind]
        prior=sum(r['success'] for r in population)/len(population)
        real_scores[kind]=model_metrics(model,real,kind,prior)
        real_scores[kind]['paired_match_bootstrap']=paired_brier_interval(model,real_games,kind,prior)
    zone_fit=[]
    for zone in range(4):
        real_zone=[r for r in real if min(3,int(r['x']//26.25))==zone]
        sim_zone=[r for r in all_rows if min(3,int(r['x']//26.25))==zone]
        zone_fit.append({'zone':zone,'real':summary(real_zone),'synthetic':summary(sim_zone)})
    report={'exposure_minutes':{'real':real_seconds/60,'synthetic':synthetic_seconds/60},
        'per90_selected_events':{key:{'real':real_stats[key]/(real_seconds/5400),'synthetic':simulated[key]/(synthetic_seconds/5400)} for key in ('passes','shots')},
        'zone_fit':zone_fit,'generated_at_utc':datetime.now(timezone.utc).isoformat(),'league_root':str(args.league),
        'generator_version':json.loads((args.league/'league.json').read_text())['competition']['generator'],
        'profile_sha256':hashlib.sha256((ROOT/'realism/profile.json').read_bytes()).hexdigest(),
        'source_revision':provenance['commit'],'source_match_audit':source_audit,
        'splits':splits,'real_held_out':real_stats,'synthetic':simulated,
        'fit_absolute_gaps':{key:abs(simulated[key]-real_stats[key]) for key in ('pass_distance_m','pass_completion','backward_pass_share','shot_distance_m','shot_conversion')},
        'distance_distribution_js_distance':{kind:js_distance(distribution(all_rows,kind),distribution(real,kind)) for kind in ('pass','shot')},
        'real_outcome_model_metrics':real_scores,'synthetic_selected_pass_brier':brier_sum/brier_n if brier_n else None,
        'synthetic_selected_pass_n':brier_n,'cancelled_decision_audit':dict(cancelled_counts),'unavailable_snapshot_audit':unavailable_snapshots,'pipeline_counts':dict(totals),'analysis_errors':coach_errors,'matches':games,
        'interpretation':['JS distance ranges 0-1; lower means closer distance distributions, not football intelligence.',
            'Real holdout data has already been examined in the earlier run; this is a reproducibility/scale audit, not a fresh blind experiment.',
            'Real outcome calibration is measured separately from the coach feasibility index. Coach scores are NOT validated probabilities.',
            'Synthetic outcome Brier is an internal self-consistency measure, not independent real-world validation.',
            'Coach compares passes only. Negative values do not mean a real player made a bad decision.',
            'Real reference uses regular-play footed ground passes and footed shots in 8 World Cup matches; no continuous tracking.',
            'Synthetic pass end locations for failed passes point to a defender; distance comparisons have an endpoint-definition mismatch.',
            'Real under_pressure annotations and the simulator 3-metre proximity flag are different pressure definitions.',
            'LLM agents are not invoked in this batch; deterministic analysis and four-scenario rollout tools are audited.']}
    (out/'system-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('synthetic','pipeline_counts','analysis_errors','real_outcome_model_metrics')},indent=2))

if __name__=='__main__':main()
