"""Local numerical diagnostics for registered current-generator decisions only."""
import argparse
import json

from .input_adapter import adapt_snapshot
from .q2 import evaluate
from .service import Repository


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--match',help='Current league match ID; defaults to first registered match')
    parser.add_argument('--decision',help='Generator decision ID in the selected match')
    parser.add_argument('--snapshot',help='Canonical snapshot ID; mutually exclusive with --decision')
    args=parser.parse_args()
    if args.decision and args.snapshot:parser.error('Use --decision or --snapshot, not both')
    repo=Repository();match=args.match or next(iter(repo.matches))
    if match not in repo.matches:parser.error('Unknown registered current match')
    records=repo.records(match)
    record=records.get(args.snapshot) if args.snapshot else next((r for r in records.values()
        if args.decision is None or r['decision_id']==args.decision),None)
    if record is None:parser.error('Unknown registered decision or snapshot')
    request=repo.request_for(record['snapshot']);public,private=repo.compare(request)
    snapshot,metadata,ratings=repo.resolve(request);state=adapt_snapshot(snapshot,metadata,ratings)
    xt=repo.model_for(match)['xt']
    private.update(match_id=match,decision_id=record['decision_id'],source=repo.source_info(match),status=public['status'])
    private['risk_sensitivity']={str(scale):[{k:r.get(k) for k in ('key','q','risk','continuation')}
        for r in evaluate(state,xt,risk_scale=scale)] for scale in (.8,1.2)}
    private['sensitivity_note']='Parameter assumptions, not confidence intervals or real-football success validation'
    print(json.dumps(private,ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':main()
