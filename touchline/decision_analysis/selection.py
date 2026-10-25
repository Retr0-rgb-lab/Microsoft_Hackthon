"""Deterministic representative sampling; never imposes action recommendation quotas."""
from collections import Counter


def representative(rows):
    eligible = [r for r in rows if r.get('analyzable')]
    chosen = []; players = Counter(); teams = Counter(); categories = Counter(); possessions = set()
    limits = {'opportunity': 10, 'favoured': 5, 'similar': 5, 'comparison': 5}
    def allowed(r):
        return (r not in chosen and players[r['actor_id']] < 2 and teams[r['team_id']] < 10
                and r['possession_id'] not in possessions and categories[r['category']] < limits[r['category']]
                and all(r['actor_id'] != q['actor_id'] or abs(r['t_ms']-q['t_ms']) >= 30000 for q in chosen))
    def pick(team, zone=None):
        pool = [r for r in eligible if r['team_id'] == team and (zone is None or r['zone'] == zone) and allowed(r)]
        if not pool:return
        r = min(pool, key=lambda r:(players[r['actor_id']], categories[r['category']],
                    -(r.get('value_loss') or 0) if r['category']=='opportunity' else -r['best_q'], r['t_ms'],r['decision_id']))
        chosen.append(r);players[r['actor_id']]+=1;teams[team]+=1;categories[r['category']]+=1;possessions.add(r['possession_id'])
    for zone, n in [(0,3),(1,3),(2,4)]:
        for _ in range(n):
            for team in ('HOME','AWAY'):pick(team,zone)
    for _ in range(10):
        for team in ('HOME','AWAY'):
            if len(chosen)<20:pick(team)
    return [r['decision_id'] for r in sorted(chosen,key=lambda r:r['t_ms'])]


def filter_records(rows, team='', player='', kind='', scope='representative', representative_ids=(), largest_ids=()):
    ids = set(representative_ids if scope=='representative' else largest_ids)
    return [r for r in rows if (not team or r['team_id']==team) and (not player or r['actor_id']==player)
            and (not kind or r['kind']==kind) and (scope=='all' or scope=='coverage' and not r.get('analyzable')
            or scope in ('representative','largest') and r['decision_id'] in ids)]
