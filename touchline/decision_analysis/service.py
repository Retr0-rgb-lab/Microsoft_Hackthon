"""Current-generator registry; canonical public comparison plus explicit research-metrics extension."""
import copy
import gzip
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from contracts import check_exchange, data_version
from .comparison import compare_actions, rollout_action
from .counterfactual import simulate
from .input_adapter import NEUTRAL_PROFILE, match_actual, source_profile
from .metrics import analysis_document

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'tests/fixtures/contracts'

def read(path):return json.loads(Path(path).read_text())

class Repository:
    def __init__(self, root=None):
        catalog=read(ROOT/'decision_analysis/catalog.json')
        self.root=Path(root) if root else ROOT/catalog['datasets'][catalog['default_dataset']]
        if not self.root.resolve().is_relative_to((ROOT/'data').resolve()):raise ValueError('Analysis output must be under registered data root')
        self.manifest=read(self.root/'manifest.json')
        self.matches={m['match_id']:m for m in self.manifest['matches']}
        self.source=ROOT/'data/league'
        # Protect against silently mixing regenerated current files with cached analysis.
        self.signatures={}
        for name,expected in self.manifest['source_hashes'].items():
            # Narration/derived display artifacts are not Q2 inputs; existing report APIs may update them.
            if Path(name).name in ('analysis.json','validation_report.json','heatmaps.json'):continue
            path=self.source/name
            if not path.exists():
                if path.name in ('decisions.jsonl','tracking.jsonl'):continue
                raise ValueError('Required current source file missing: '+name)
            if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError('Source changed; rebuild decision-analysis: '+name)
            stat=path.stat();self.signatures[name]=(stat.st_mtime_ns,stat.st_size)

    def check_live_source(self, match_id=None):
        names=['league.json','squads.json']
        if match_id:
            if match_id not in self.matches:raise KeyError('Unknown match')
            names.extend(name for name in self.signatures if name.startswith('matches/'+match_id+'/'))
        for name in names:
            if name not in self.signatures:continue
            path=self.source/name
            if not path.exists():raise ValueError('Current source removed; restart/rebuild analysis')
            stat=path.stat();signature=(stat.st_mtime_ns,stat.st_size)
            if signature!=self.signatures[name]:
                if hashlib.sha256(path.read_bytes()).hexdigest()!=self.manifest['source_hashes'][name]:
                    raise ValueError('Current source changed while serving; rebuild analysis')
                self.signatures[name]=signature

    @lru_cache(maxsize=8)
    def metadata(self, match_id):
        if match_id not in self.matches:raise KeyError('Unknown match')
        meta=read(self.source/'matches'/match_id/'metadata.json')
        if data_version(meta)!=self.matches[match_id]['data_version']:raise ValueError('Current metadata changed; rebuild analysis')
        return meta

    @lru_cache(maxsize=8)
    def index(self, match_id):
        if match_id not in self.matches:raise KeyError('Unknown match')
        return read(self.root/'matches'/match_id/'index.json')

    @lru_cache(maxsize=4)
    def records(self, match_id):
        if match_id not in self.matches:raise KeyError('Unknown match')
        with gzip.open(self.root/'matches'/match_id/'snapshots.jsonl.gz','rt') as stream:
            result={}
            for line in stream:
                row=json.loads(line);sid=row['snapshot']['snapshot_id']
                if sid in result:raise ValueError('Ambiguous duplicate snapshot')
                result[sid]=row
            return result

    @lru_cache(maxsize=4)
    def model_for(self, match_id):
        for path in sorted((self.root/'models').glob('fold-*.json')):
            model=read(path)
            if model['source_commit']!=self.manifest['source_commit'] or model['source_data_version']!=self.manifest['dataset_version']:
                raise ValueError('Model/source mismatch')
            if match_id in model['test_matches']:return model
        raise KeyError('No isolated model for match')

    def resolve(self, request):
        match=request['match_id'];self.check_live_source(match);meta=self.metadata(match);record=self.records(match).get(request['snapshot_id'])
        if record is None:raise KeyError('Unknown registered snapshot')
        return record['snapshot'],meta,self.index(match)['ratings']

    @staticmethod
    def request_for(snapshot):
        return dict(match_id=snapshot['match_id'],snapshot_id=snapshot['snapshot_id'],t_ms=snapshot['t_ms'],
            actor_id=snapshot['frame']['ball_owner_id'],question='Compare current choices',mode='analyst',language='en',profile=copy.deepcopy(NEUTRAL_PROFILE))

    def compare(self, request):
        snapshot,meta,ratings=self.resolve(request)
        return compare_actions(request,snapshot,meta,self.model_for(request['match_id']),ratings)

    def source_info(self, match_id):
        return dict(dataset='league',root='data/league',source_commit=self.manifest['source_commit'],
            dataset_version=self.manifest['dataset_version'],model_id=self.model_for(match_id)['model_id'],
            snapshot_source='generator_decisions',match_excluded_from_fitting=True)

    def bundle(self, request):
        snapshot,meta,_=self.resolve(request)
        actor=next(p for p in meta['players'] if p['player_id']==request['actor_id'])
        return dict(snapshot=snapshot,metadata=meta,request=request,source_profile=source_profile(actor),source=self.source_info(request['match_id']))

    def document(self, request):
        public,private=self.compare(request);snapshot,meta,_=self.resolve(request)
        record=self.records(request['match_id'])[snapshot['snapshot_id']]
        return analysis_document(request,public,private,snapshot,meta,self.source_info(request['match_id']),record['decision_id'])

    def actual(self, request, public):
        record=self.records(request['match_id'])[request['snapshot_id']]
        key,resolution=match_actual(record['retrospective'],public['candidates'])
        updated=copy.deepcopy(public)
        for c in updated['candidates']:c['is_actual']=c['action_id']==key
        snapshot,meta,_=self.resolve(request);check_exchange(request,updated,snapshot,meta)
        return dict(response=updated,actual_action_id=key,resolution=resolution,
                    note='Retrospective type/recipient only; outcomes and future positions were not scoring inputs.')

@lru_cache(maxsize=1)
def repository():return Repository()


def handle_get(handler):
    route=urlsplit(handler.path)
    if not route.path.startswith('/api/decision-analysis/'):return False
    if not handler.trusted():handler.reply(403,{'error':'Same-origin local requests only'});return True
    try:
        repo=repository();query=parse_qs(route.query)
        repo.check_live_source(query.get('match_id',[None])[0])
        if route.path=='/api/decision-analysis/catalog':
            handler.reply(200,dict(schema_version='decision-analysis-1',dataset='league',totals=repo.manifest['totals'],
                source_commit=repo.manifest['source_commit'],matches=[dict(match_id=m['match_id'],covered=m['counts']['covered']) for m in repo.matches.values()]))
        elif route.path=='/api/decision-analysis/index':handler.reply(200,repo.index(query.get('match_id',[''])[0]))
        elif route.path=='/api/decision-analysis/context':
            match=query.get('match_id',[''])[0];decision=query.get('decision_id',[''])[0]
            row=next(r for r in repo.index(match)['records'] if r['decision_id']==decision)
            snapshot=repo.records(match)[row['snapshot_id']]['snapshot']
            handler.reply(200,repo.bundle(repo.request_for(snapshot)))
        else:handler.reply(404,{'error':'Unknown decision-analysis route'})
    except (KeyError,StopIteration,FileNotFoundError):handler.reply(404,{'error':'Registered match or decision unavailable'})
    except (ValueError,TypeError):handler.reply(400,{'error':'Source mismatch or invalid request; rebuild analysis if source changed'})
    return True


def handle_post(handler,route,data):
    if not route.startswith('/api/decision-analysis/'):return False
    try:
        repo=repository()
        if route=='/api/decision-analysis/compare':handler.reply(200,repo.compare(data)[0])
        elif route=='/api/decision-analysis/analyze':handler.reply(200,repo.document(data))
        elif route in ('/api/decision-analysis/counterfactual','/api/decision-analysis/rollout','/api/decision-analysis/routes','/api/decision-analysis/actual','/api/decision-analysis/agents'):
            expected={'request','candidate_set_id'}|({'action_id'} if route.endswith(('/rollout','/counterfactual')) else set())
            if not isinstance(data,dict) or set(data)!=expected:raise ValueError('Invalid bound request')
            request=data['request'];public,private=repo.compare(request)
            if data['candidate_set_id']!=public['candidate_set_id']:raise ValueError('Stale candidate set')
            snapshot,metadata,_=repo.resolve(request)
            if route.endswith('/counterfactual'):
                handler.reply(200,simulate(request,public,private,snapshot,metadata,data['action_id'],data['candidate_set_id']))
            elif route.endswith('/rollout'):
                handler.reply(200,rollout_action(request,public,private,snapshot,metadata,data['action_id'],data['candidate_set_id']))
            elif route.endswith('/routes'):
                eligible={c['action_id'] for c in public['candidates'] if c['eligible']}
                handler.reply(200,dict(candidate_set_id=public['candidate_set_id'],routes=[dict(action_id=a['key'],start=snapshot['frame']['ball'][:2],target=a['target'])
                    for a in private.get('options',[]) if a['key'] in eligible]))
            elif route.endswith('/actual'):handler.reply(200,repo.actual(request,public))
            else:handler.reply(200,public) # no fabricated Agent trace
        else:handler.reply(404,{'error':'Unknown decision-analysis route'})
    except (KeyError,StopIteration,FileNotFoundError):handler.reply(404,{'error':'Unknown registered match, snapshot, model or action'})
    except (ValueError,TypeError):handler.reply(400,{'error':'Invalid or stale request; recompute comparison'})
    return True
