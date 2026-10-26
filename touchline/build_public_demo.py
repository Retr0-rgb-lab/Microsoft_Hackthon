"""Build a compact, secret-free browser demonstration from synthetic snapshots."""
import argparse
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def league_root():
    """Where the synthetic league lives.

    A validated league is used when it is present, because that is the copy
    the calibration run analysed. The checked-in league is the fallback, so a
    clean checkout can still build the public demonstration.
    """
    for candidate in (ROOT/'data/league',):
        if (candidate/'matches').is_dir():
            return candidate
    raise SystemExit('No synthetic league found under data/.')


def build(league=None):
    out=ROOT/'public-demo';out.mkdir(exist_ok=True)
    league=Path(league) if league else league_root()
    matches=[];parity=[]
    for folder in sorted((league/'matches').iterdir()):
        if not (folder/'decisions.jsonl').exists():
            # The decision records are generated, not checked in. A match
            # without them has nothing to show.
            continue
        meta=json.loads((folder/'metadata.json').read_text())
        with (folder/'decisions.jsonl').open() as stream: records=[json.loads(line) for line in stream]
        with (folder/'events.jsonl').open() as stream: events={e.get('action_id'):e for e in map(json.loads,stream) if e['type'] in ('pass','carry','shot')}
        picked={}
        for kind in ('pass','carry','shot'):
            for d in [r for r in records if r['selected']['kind']==kind][:2]:picked[d['decision_id']]=d
        for t in (1200,3000,5000):
            valid=[d for d in records if d['snapshot']['in_play'] and d['action_id'] in events]
            if valid:
                d=min(valid,key=lambda d:abs(d['t_ms']-t*1000));picked[d['decision_id']]=d
        cases=[{'record':d,'event':events.get(d['action_id'])} for d in sorted(picked.values(),key=lambda d:d['t_ms']) if d['snapshot']['in_play']]
        matches.append({'match_id':folder.name,'metadata':meta,'cases':cases})
    (out/'data.json').write_text(json.dumps({'synthetic':True,'selection':'Up to nine curated moments per match; not full-match video or all decisions.','matches':matches},ensure_ascii=False,separators=(',',':')))
    shutil.copyfile(ROOT/'decision/value-model.json',out/'value-model.json')
    shutil.copyfile(ROOT/'realism/profile.json',out/'rates.json')
    shutil.copyfile(ROOT/'coach.css',out/'coach.css')
    html=(ROOT/'action-review.html').read_text().replace('action-review.js?v=2','app.js?v=1')
    html=html.replace('<a href="coach.html?dataset=validated">← Replay analysis</a>', '<a href="https://github.com/Retr0-rgb-lab/Microsoft_Hackthon">Source on GitHub</a>')
    html=html.replace('artifacts/realism/outcome-value-validation.json','value-model.json').replace('realism-validation.html','validation.html')
    html=html.replace('Synthetic replay sample ·', 'Interactive demo · curated moments from 40 synthetic matches · runs in the browser, no key needed ·')
    controls='<div class="controls"><button id="play-hypothesis" disabled>Play the hypothetical development</button><select id="hypothesis-case" aria-label="Defensive reaction assumption"><option value="quick">Quick reaction 0.1 s</option><option value="baseline" selected>Baseline reaction 0.3 s</option><option value="delayed">Delayed reaction 0.65 s</option><option value="wide_error">Landed 1.5 m off</option></select><button id="reset-hypothesis">Return to the pre-action snapshot</button></div><p id="hypothesis-status" role="status">The rollout covers legal ground passes only; the four cases are not a success-rate sample.</p>'
    html=html.replace('<div class="metrics">',controls+'<div class="metrics">')
    html=html.replace('</main>', '<footer style="margin:36px 0;color:#b5c7be"><p>Data and model training reference: StatsBomb Open Data. The matches are synthetic; action rankings still rest on unvalidated assumptions.</p><a href="https://github.com/hudl/open-data"><img src="statsbomb-logo.png" alt="StatsBomb" style="width:170px;max-width:55%;padding:12px;background:white;border-radius:8px"></a></footer></main>')
    (out/'index.html').write_text(html)
    # Remove machine-specific paths and large local-only audit download links from this copy.
    report=(ROOT/'realism-validation.html').read_text().replace('action-review.html','index.html').replace('coach.html?dataset=validated','index.html').replace('coach.html?realism=1','index.html')
    import re
    report=re.sub(r'<a href=[\"\']artifacts/[^>]+>.*?</a>','<span>The full audit files are in the artifacts/realism directory on GitHub</span>',report)
    (out/'validation.html').write_text(report)
    print(json.dumps({'matches':len(matches),'moments':sum(len(m['cases']) for m in matches),'data_bytes':(out/'data.json').stat().st_size}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--league',type=Path,default=None,help='synthetic league root (default: the checked-in one)')
    args=parser.parse_args()
    build(args.league)
