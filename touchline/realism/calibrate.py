"""Fetch pinned StatsBomb events, fit on matches, evaluate on disjoint matches."""
import argparse
import hashlib
import json
import math
import urllib.request
from collections import defaultdict
from pathlib import Path
from .model import bucket, shot_bucket

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT/'.local'/'statsbomb'

def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()

def records(events):
    for e in events:
        if e.get('period', 0) > 2 or e.get('play_pattern', {}).get('name') != 'Regular Play':
            continue
        kind = e.get('type', {}).get('name', '').lower()
        if kind not in ('pass', 'carry', 'shot') or 'location' not in e:
            continue
        x, y = e['location'][:2]
        x, y = x*105/120, y*68/80
        r = {'kind': kind, 'x': x, 'y': y}
        if kind == 'pass':
            p = e['pass']
            if p.get('body_part', {}).get('name') not in ('Left Foot', 'Right Foot') or p.get('height', {}).get('name') != 'Ground Pass':
                continue
            end = p.get('end_location')
            if not end:
                continue
            ex, ey = end[0]*105/120, end[1]*68/80
            r.update(distance=math.hypot(ex-x, ey-y), backward=ex < x-1,
                     big_back=x>88 and ex<x-30, pressured=bool(e.get('under_pressure')),
                     success='outcome' not in p)
        elif kind == 'shot':
            if e['shot'].get('body_part', {}).get('name') not in ('Left Foot', 'Right Foot'):
                continue
            r.update(distance=math.hypot(105-x, y-34), success=e['shot']['outcome']['name']=='Goal')
        yield r

def fit(rows):
    groups = {'pass_success': defaultdict(list), 'shot_goal': defaultdict(list)}
    actions = defaultdict(lambda: defaultdict(int))
    for r in rows:
        actions[str(min(3, int(r['x']//26.25)))][r['kind']] += 1
        if r['kind']=='pass':
            groups['pass_success'][f"{bucket(r['distance'])}:{int(r['pressured'])}"].append(r['success'])
        if r['kind']=='shot':
            groups['shot_goal'][str(shot_bucket(r['x'], r['y']))].append(r['success'])
    result = {}
    for name, cells in groups.items():
        all_values = [v for cell in cells.values() for v in cell]
        prior = sum(all_values)/len(all_values)
        result[name] = {key: {'n': len(values), 'probability': (sum(values)+20*prior)/(len(values)+20)}
                        for key, values in cells.items()}
    result['pass_geometry'] = {}
    for zone in range(4):
        group = [r for r in rows if r['kind']=='pass' and min(3,int(r['x']//26.25))==zone]
        result['pass_geometry'][str(zone)] = {'backward': (sum(r['backward'] for r in group)+1)/(len(group)+2),
            'lengths': [(sum(bucket(r['distance'])==b for r in group)+1)/(len(group)+5) for b in range(5)]}
    result['actions'] = {key: {kind: (counts[kind]+1)/(sum(counts.values())+3)
                              for kind in ('pass','carry','shot')} for key, counts in actions.items()}
    return result

def summary(rows):
    passes = [r for r in rows if r['kind']=='pass']
    shots = [r for r in rows if r['kind']=='shot']
    return {'actions': len(rows), 'passes': len(passes), 'shots': len(shots),
            'pass_distance_m': sum(r['distance'] for r in passes)/max(1,len(passes)),
            'pass_completion': sum(r['success'] for r in passes)/max(1,len(passes)),
            'backward_pass_share': sum(r['backward'] for r in passes)/max(1,len(passes)),
            'shot_distance_m': sum(r['distance'] for r in shots)/max(1,len(shots)),
            'shot_conversion': sum(r['success'] for r in shots)/max(1,len(shots))}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    manifest_path = CACHE/'manifest.json'
    if args.download:
        commit = json.loads(fetch('https://api.github.com/repos/statsbomb/open-data/commits/master'))['sha']
        base = f'https://raw.githubusercontent.com/statsbomb/open-data/{commit}'
        matches = sorted(json.loads(fetch(base+'/data/matches/43/106.json')), key=lambda m:m['match_id'])[:32]
        sources = []
        for m in matches:
            mid = m['match_id']; url = f'{base}/data/events/{mid}.json'
            raw = fetch(url); (CACHE/f'{mid}.json').write_bytes(raw)
            sources.append({'match_id': mid, 'url': url, 'sha256': hashlib.sha256(raw).hexdigest()})
            print('Downloaded', mid, flush=True)
        manifest_path.write_text(json.dumps({'commit':commit,'competition':'2022 World Cup', 'sources':sources},indent=2))
    manifest = json.loads(manifest_path.read_text())
    splits = {'train': [], 'development': [], 'test': []}; ids = {'train': [], 'development': [], 'test': []}
    for index, source in enumerate(manifest['sources']):
        raw = (CACHE/f"{source['match_id']}.json").read_bytes()
        assert hashlib.sha256(raw).hexdigest()==source['sha256']
        split = 'test' if index>=24 else ('development' if index%3==2 else 'train')
        ids[split].append(source['match_id']); splits[split].extend(records(json.loads(raw)))
    profile = fit(splits['train']); profile['provenance'] = {**manifest, 'split':ids}
    (ROOT/'realism/profile.json').write_text(json.dumps(profile,indent=2)+'\n')
    from .model import Model
    model = Model(); metrics = {}
    for kind in ('pass','shot'):
        train = [r for r in splits['train'] if r['kind']==kind]
        test = [r for r in splits['test'] if r['kind']==kind]
        prior = sum(r['success'] for r in train)/len(train)
        predictions = [model.pass_success(r['distance'],r['pressured']) if kind=='pass' else model.shot_goal(r['x'],r['y']) for r in test]
        metrics[kind] = {'n':len(test),'brier':sum((p-r['success'])**2 for p,r in zip(predictions,test))/len(test),
                         'constant_train_prior_brier':sum((prior-r['success'])**2 for r in test)/len(test),
                         'observed_rate':sum(r['success'] for r in test)/len(test),'mean_prediction':sum(predictions)/len(test)}
    report = {'source':manifest,'split':ids,'scope':'Regular Play, periods 1-2; footed ground passes and footed shots; carries. Coordinates rescaled 120x80 to 105x68. Event counts are not equal to decision opportunities.',
              'train':summary(splits['train']),'held_out':summary(splits['test']),'predictive_metrics':metrics,
              'limitations':['One tournament; not Premier League validation.','No continuous tracking: cannot validate defensive movement, counterfactual choices or optimal actions.','No arbitrary overall realism score.','Sparse cells use 20-observation empirical Bayes smoothing.']}
    (ROOT/'artifacts/realism/real-data-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='source'},indent=2))

if __name__=='__main__': main()
