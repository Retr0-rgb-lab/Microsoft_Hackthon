"""Fit action intercepts on real training frequencies; audit on separate seeds.

Run: python3 -m realism.calibrate_player_actions --workers 4
Raw pinned StatsBomb files must already exist in .local/statsbomb/.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import urllib.request

from .calibrate import CACHE, records, summary
from .player_actions import KINDS, COEFFICIENTS, REVISION

ROOT = Path(__file__).resolve().parents[1]
TRAIN_SEEDS = list(range(241000, 241010))
VALIDATION_SEEDS = list(range(242000, 242020))
TOLERANCE = {'pass': .015, 'carry': .015, 'shot': .0035}


def action_summary(rows):
    counts = Counter(r['kind'] for r in rows)
    total = sum(counts.values())
    if not total:
        raise ValueError('No eligible actions to calibrate')
    return {'counts': {k: counts[k] for k in KINDS}, 'total': total,
            'shares': {k: counts[k]/total for k in KINDS}}


def load_reference(download=False):
    provenance = json.loads((ROOT/'realism/profile.json').read_text())['provenance']
    split = provenance['split']
    if any(set(split[a]) & set(split[b]) for a, b in
           (('train', 'test'), ('train', 'development'), ('test', 'development'))):
        raise ValueError('Real match splits overlap')
    rows = {name: [] for name in split}
    for source in provenance['sources']:
        path = CACHE/f"{source['match_id']}.json"
        if not path.exists() and download:
            with urllib.request.urlopen(source['url'], timeout=60) as response:
                raw = response.read()
            if hashlib.sha256(raw).hexdigest() != source['sha256']:
                raise ValueError(f"Downloaded source checksum mismatch: {source['match_id']}")
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source['sha256']:
            raise ValueError(f"Source checksum mismatch: {source['match_id']}")
        subset = next(name for name, ids in split.items() if source['match_id'] in ids)
        rows[subset].extend(records(json.loads(raw)))
    return {name: action_summary(group) for name, group in rows.items()}, provenance


def run_game(job):
    from generate import Match, CLUBS, RATINGS, load_squads, select_lineup, HZ, DURATION
    from .evaluate_system import sim_rows
    seed, index, multipliers, enabled, strength = job
    # Both phases cover every club; held-out seeds use different opponents.
    offset = 1 if seed in TRAIN_SEEDS else 3
    home, away = CLUBS[(index*2) % 20], CLUBS[(index*2+offset) % 20]
    squads = load_squads()
    sim = Match(seed, home=home, away=away,
                ratings=[RATINGS[c['club_id']] for c in (home, away)],
                lineups=[select_lineup(c['club_id'], squads) for c in (home, away)],
                attribute_actions=enabled, action_multipliers=multipliers,
                attribute_strength=strength)
    for frame in range(1, DURATION*HZ+1):
        sim.step(frame)
    # Restart repositioning is not a policy decision; exclude its mandatory carry.
    events = [e for e in sim.events if e.get('selection_origin') != 'restart']
    rows = list(sim_rows(events))
    return {'seed': seed, 'home': home['club_id'], 'away': away['club_id'],
            **action_summary(rows), 'outcome_metrics': summary(rows),
            'goals': sum(sim.score)}


def simulate(pool, seeds, multipliers, enabled=True, strength=1.0):
    games = list(pool.map(run_game, [(seed, i, multipliers, enabled, strength)
                                    for i, seed in enumerate(seeds)]))
    counts = {k: sum(g['counts'][k] for g in games) for k in KINDS}
    total = sum(counts.values())
    return {'counts': counts, 'total': total, 'shares': {k: counts[k]/total for k in KINDS},
            'matches': games}


def gaps(observed, reference):
    return {k: observed['shares'][k]-reference['shares'][k] for k in KINDS}


def fit_intercepts(pool, target, iterations):
    multipliers = {k: 1.0 for k in KINDS}
    history = []
    best = None
    for iteration in range(iterations):
        result = simulate(pool, TRAIN_SEEDS, multipliers)
        error = gaps(result, target)
        loss = sum(abs(v) for v in error.values())
        history.append({'iteration': iteration, 'multipliers': dict(multipliers),
                        'shares': result['shares'], 'signed_gaps': error})
        print(json.dumps(history[-1]), flush=True)
        if best is None or loss < best[0]:
            best = loss, dict(multipliers)
        if abs(error['pass']) < .003 and abs(error['carry']) < .003 and abs(error['shot']) < .001:
            break
        updated = {k: multipliers[k]*(target['shares'][k]/max(result['shares'][k], 1e-6))**.8
                   for k in KINDS}
        center = math.exp(sum(math.log(v) for v in updated.values())/3)
        multipliers = {k: max(.05, min(20, v/center)) for k, v in updated.items()}
    return best[1], history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--iterations', type=int, default=6)
    parser.add_argument('--download', action='store_true', help='Fetch missing pinned source files; never changes the reference version')
    args = parser.parse_args()
    if args.workers < 1 or args.iterations < 1:
        parser.error('workers and iterations must be positive')
    reference, provenance = load_reference(args.download)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        multipliers, history = fit_intercepts(pool, reference['train'], args.iterations)
        # Freeze everything before accessing validation simulations or test metrics.
        config = {'revision': REVISION, 'multipliers': multipliers,
                  'coefficients': COEFFICIENTS, 'attribute_strength': 1.0,
                  'attribute_effect': 'bounded heuristic log-weight, not learned from paired player data',
                  'target': reference['train'], 'source_commit': provenance['commit'],
                  'train_match_ids': provenance['split']['train'], 'fit_seeds': TRAIN_SEEDS,
                  'roster_sha256': hashlib.sha256((ROOT/'data/league/squads.json').read_bytes()).hexdigest()}
        (ROOT/'realism/player-action-profile.json').write_text(json.dumps(config, indent=2)+'\n')
        print('Frozen calibration; evaluating baseline and held-out simulator seeds.', flush=True)
        before = simulate(pool, VALIDATION_SEEDS, {k: 1.0 for k in KINDS}, enabled=False)
        after = simulate(pool, VALIDATION_SEEDS, multipliers)
        neutral = simulate(pool, VALIDATION_SEEDS, multipliers, strength=0.0)
    error = gaps(after, reference['test'])
    report = {'revision': REVISION, 'reference': reference, 'source': provenance,
              'config': config, 'fit_history': history, 'validation_seeds': VALIDATION_SEEDS,
              'baseline': before, 'attribute_policy': after, 'neutral_attribute_ablation': neutral,
              'signed_gaps_vs_test': error, 'tolerance': TOLERANCE,
              'passed': all(abs(error[k]) <= TOLERANCE[k] for k in KINDS),
              'scope': 'Shares among footed ground passes, carries and footed shots. Real reference: Regular Play, periods 1-2. Synthetic: resolved actions excluding mandatory restart carries. Other action types and event volume are outside this calibration.',
              'limitations': [
                  'World Cup reference, not a Premier League benchmark.',
                  'Player radar coefficients are bounded style hypotheses; no paired player/action dataset fits their effects.',
                  'No action quotas or future-event feedback are used at runtime.',
                  'Only training real matches and fitting simulator seeds choose multipliers; development/test references never choose coefficients.',
                  'Current Sofascore profiles are synthetic style inputs, not historical World Cup features.',
                  'Matching action shares does not establish realistic movement, individual behavior or calibrated player outcomes.',
              ]}
    output = ROOT/'artifacts/realism/player-action-validation.json'
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'report': str(output), 'passed': report['passed'],
                      'reference': reference['test']['shares'], 'before': before['shares'],
                      'after': after['shares'], 'gaps': error}), flush=True)


if __name__ == '__main__':
    main()
