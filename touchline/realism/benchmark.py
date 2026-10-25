"""Compare untouched baseline and current simulator using identical seeds."""
import importlib.util
import json
import math
import subprocess
from pathlib import Path
from .calibrate import summary

ROOT=Path(__file__).resolve().parents[1]

def simulate(module, seeds):
    rows=[]; totals=[]
    for seed in seeds:
        sim=module.Match(seed)
        for frame in range(1,module.DURATION*module.HZ+1): sim.step(frame)
        game=[]
        for e in sim.events:
            if e['type'] not in ('pass','shot','carry'): continue
            if e['type']=='pass' and e.get('pass_height')!='ground': continue
            start=e['start_location']; end=e['end_location']
            direction=1 if (e['team_id']=='HOME')==(e['period']==1) else -1
            x=start[0] if direction==1 else 105-start[0]
            ex=end[0] if direction==1 else 105-end[0]
            r={'kind':e['type'],'x':x,'y':start[1]}
            if r['kind']=='pass':
                r.update(distance=math.dist(start,end),backward=ex<x-1,big_back=x>88 and ex<x-30,
                         success=e['outcome']=='complete',pressured=e.get('under_pressure',False))
            if r['kind']=='shot': r.update(distance=math.hypot(105-x,start[1]-34),success=e['outcome']=='goal')
            game.append(r)
        rows.extend(game)
        stats=summary(game); stats.update(seed=seed,goals=sum(sim.score),decisions=len(getattr(sim,'decisions',[])))
        stats['unpressured_large_backpasses_near_goal']=sum(r.get('big_back',False) and not r.get('pressured',False) for r in game)
        totals.append(stats)
    return summary(rows),totals

def main():
    path=ROOT/'.local/baseline_generate.py'
    path.parent.mkdir(exist_ok=True)
    # HEAD is the unmodified repository generator; save commit identity in the report.
    path.write_bytes(subprocess.check_output(['git','show','HEAD:generate.py'],cwd=ROOT))
    spec=importlib.util.spec_from_file_location('baseline_generate',path); old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    import generate
    seeds=[20261019,12345,712]
    baseline,old_games=simulate(old,seeds); current,new_games=simulate(generate,seeds)
    reference=json.loads((ROOT/'artifacts/realism/real-data-validation.json').read_text())['held_out']
    gaps={key:{'before':abs(baseline[key]-reference[key]),'after':abs(current[key]-reference[key])}
          for key in ('pass_distance_m','pass_completion','backward_pass_share','shot_distance_m','shot_conversion')}
    report={'seeds':seeds,'baseline_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'real_held_out':reference,'baseline':baseline,'modified':current,'absolute_gaps':gaps,
            'baseline_matches':old_games,'modified_matches':new_games,
            'scope':'Synthetic regular-play actions vs real Regular Play events; synthetic restarts include a forced carry. Ground passes only. Rates do not establish tactical correctness. Initial 8 development matches informed revisions. Final held-out matches were not used to fit or revise the policy.'}
    (ROOT/'artifacts/realism/generator-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
