#!/usr/bin/env python3
"""Validate a format-v0.1 synthetic match directory (dependency-free).

Checks: frame rate from metadata, frame continuity, centre-origin pitch bounds,
facing range and turn rate, speed / acceleration limits, velocity agreement,
ball attachment, event causality, score/stat agreement, decision_point
consistency, offside and ball-out cross-checks against tracking, and a
forbidden-term scan (real clubs, players, venues, leagues, brands).

    python3 validate.py DATA_DIR [--forbidden forbidden_terms.txt] [--scan extra files...]
"""
import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

HL, HW = 52.5, 34.0
TOL_POS = .011          # rounding tolerance for offside / line checks (m)


def load_lines(path):
    with path.open() as f:
        for line in f:
            yield json.loads(line)


def scan_forbidden(paths, terms_file):
    if not terms_file or not Path(terms_file).exists():
        return {'skipped': 'no forbidden_terms file'}
    terms = [t.strip() for t in Path(terms_file).read_text().splitlines() if t.strip() and not t.startswith('#')]
    rx = re.compile(r'(?<![A-Za-z0-9])(' + '|'.join(re.escape(t) for t in sorted(terms, key=len, reverse=True)) + r')(?![A-Za-z0-9])', re.I)
    hits = []
    for p in paths:
        with open(p, encoding='utf-8', errors='replace') as f:
            for n, line in enumerate(f, 1):
                for m in rx.finditer(line):
                    hits.append(f'{Path(p).name}:{n}: {m.group(0)}')
    assert not hits, ('forbidden terms found', hits[:20])
    return {'terms': len(terms), 'files': len(paths), 'hits': 0}


def offside_margin(frame, receiver, team, home):
    """Return attacker X minus offside line, in the attacking team's direction."""
    d = frame['attack_dir'] if team == 'HOME' else -frame['attack_dir']
    pos = {p[0]: p for p in frame['players']}
    rx = pos[receiver][1] * d
    defenders = sorted((p[1] * d for p in frame['players'] if home[p[0]] != team), reverse=True)
    second_last = defenders[1] if len(defenders) > 1 else -HL
    line = max(second_last, frame['ball'][0] * d, 0.)
    return rx - line


def validate(root, terms_file=None, extra_scan=()):
    meta = json.loads((root / 'metadata.json').read_text())
    summary = json.loads((root / 'summary.json').read_text())
    hz = meta['frame_hz']
    assert isinstance(hz, int) and hz >= max(10, meta.get('min_frame_hz', 10)), hz
    dt = 1 / hz
    cs = meta['coordinate_system']
    assert cs['origin'] == 'centre_spot' and cs['pitch_length_m'] == 105 and cs['pitch_width_m'] == 68
    duration_ms = meta['duration_ms']
    n_frames = int(round(duration_ms / 1000 * hz)) + 1
    assert meta['frame_count'] == n_frames
    half_ms = 3000000
    events = list(load_lines(root / 'events.jsonl'))
    teams = {p['player_id']: p['team_id'] for p in meta['players']}
    ids = set(teams)
    event_by_id = {e['event_id']: e for e in events}
    counts = {'HOME': Counter(), 'AWAY': Counter()}
    goals = {}
    last = -1
    for i, e in enumerate(events, 1):
        assert e['sequence'] == i and e['start_ms'] <= e['end_ms'] == e['available_at_ms'] >= last
        last = e['available_at_ms']
        assert 0 <= last <= duration_ms
        for f in ('player_id', 'recipient_id', 'actual_receiver_id', 'target_player_id'):
            if e.get(f) is not None:
                assert e[f] in ids, (f, e)
        for r in e.get('related_event_ids', []):
            assert event_by_id[r]['available_at_ms'] <= e['available_at_ms']
        team = e.get('team_id')
        t = e['type']
        if t == 'pass':
            assert teams[e['player_id']] == teams[e['recipient_id']] == team
            o = e['outcome']
            assert o in ('complete', 'intercepted', 'out', 'offside')
            ar = e['actual_receiver_id']
            if o in ('complete', 'offside'):
                assert ar == e['recipient_id']
            elif o == 'intercepted':
                assert ar is not None and teams[ar] != team
            else:
                assert ar is None
            counts[team]['passes'] += 1
            counts[team]['completed_passes'] += int(o == 'complete')
        elif t == 'shot':
            counts[team]['shots'] += 1
            counts[team]['shots_on_target'] += int(e['outcome'] != 'off_target')
            if e['outcome'] == 'goal':
                goals[e['end_ms']] = team
        elif t in ('interception', 'pressure'):
            counts[team]['interceptions' if t == 'interception' else 'pressure_events'] += 1
        elif t == 'offside':
            counts[team]['offsides'] += 1
            assert teams[e['player_id']] == team
        elif t == 'ball_out':
            counts[team]['ball_out'] += 1
        elif t == 'decision_point':
            opts = e['options']
            assert 0 <= e['chosen_index'] < len(opts) and opts[e['chosen_index']]['option_id'] == e['chosen_option_id']
            for o in opts:
                assert o['type'] in ('pass', 'carry', 'shot') and 0 <= o['success_prob'] <= 1
                if o['type'] == 'pass':
                    assert teams[o['target_player_id']] == team and o['target_player_id'] != e['player_id']
            assert sum(o['type'] == 'pass' for o in opts) >= 1 and len(opts) >= 2

    # decision_point -> the action that follows it
    dp_checked = 0
    for e in events:
        if e['type'] in ('pass', 'carry', 'shot') and e.get('decision_event_id'):
            dp = event_by_id[e['decision_event_id']]
            ch = dp['options'][dp['chosen_index']]
            assert dp['type'] == 'decision_point' and dp['player_id'] == e['player_id'] and ch['type'] == e['type'], (dp, e)
            assert dp['available_at_ms'] == e['start_ms']
            if e['type'] == 'pass':
                assert ch['target_player_id'] == e['recipient_id']
            dp_checked += 1
    cancelled = sum(1 for e in events if e['type'] == 'action_cancelled' and e.get('decision_event_id'))
    assert dp_checked + cancelled == sum(1 for e in events if e['type'] == 'decision_point')

    # ---- tracking pass ------------------------------------------------
    need_frames = {}   # t_ms -> list of checks needing that frame
    for e in events:
        if e['type'] == 'pass' and e['outcome'] in ('complete', 'offside'):
            need_frames.setdefault(e['start_ms'], []).append(('offside', e))
        if e['type'] == 'decision_point':
            need_frames.setdefault(e['available_at_ms'], []).append(('dp_offside', e))
        if e['type'] == 'ball_out':
            need_frames.setdefault(e['available_at_ms'], []).append(('ball_out', e))
    offside_events = {e['pass_event_id']: e for e in events if e['type'] == 'offside'}
    restarts = [e for e in events if e['type'] == 'restart']
    snapshots = {s['t_ms']: s for s in load_lines(root / 'states.jsonl')}
    stats = Counter()
    prev = None
    score = [0, 0]
    mx = Counter()
    count = 0
    records = 0
    max_turn = 0.
    for f in load_lines(root / 'tracking.jsonl'):
        count += 1
        k = f['frame_id']
        assert k == count - 1 and f['t_ms'] == int(round(k * 1000 / hz))
        assert f['period'] == (1 if f['t_ms'] < half_ms else 2)
        assert f['period_ms'] == f['t_ms'] - (f['period'] - 1) * half_ms
        assert f['attack_dir'] == (1 if f['period'] == 1 else -1)
        assert len(f['players']) == 22 and {p[0] for p in f['players']} == ids
        records += 22
        if f['ball_owner_id'] is not None:
            assert teams[f['ball_owner_id']] == f['possession_team_id']
        if f['t_ms'] in goals:
            score[0 if goals[f['t_ms']] == 'HOME' else 1] += 1
        assert f['score'] == score
        if f['t_ms'] in snapshots:
            assert snapshots[f['t_ms']]['score'] == score
        pv = {p[0]: p for p in prev['players']} if prev else {}
        for p in f['players']:
            pid, x, y, vx, vy, fa = p
            assert all(math.isfinite(v) for v in p[1:])
            assert -HL <= x <= HL and -HW <= y <= HW
            assert -math.pi - 1e-4 <= fa <= math.pi + 1e-4
            sp = math.hypot(vx, vy)
            assert sp <= 7.21, (pid, sp, f['t_ms'])
            mx['player_speed'] = max(mx['player_speed'], sp)
            if prev:
                q = pv[pid]
                assert abs((x - q[1]) / dt - vx) <= .0011 / dt + .001 and abs((y - q[2]) / dt - vy) <= .0011 / dt + .001
                acc = math.hypot(vx - q[3], vy - q[4]) / dt
                assert acc <= 3.5 + .0011 / dt / dt * 0 + .0011 / dt + .05, (pid, acc)
                mx['player_acc'] = max(mx['player_acc'], acc)
                turn = abs((fa - q[5] + math.pi) % (2 * math.pi) - math.pi) / dt
                max_turn = max(max_turn, turn)
                assert turn <= 3 * math.pi + .01, (pid, turn)
        bx, by, bz, bvx, bvy, bvz = f['ball']
        assert bz >= 0 and abs(bx) <= HL + 3 and abs(by) <= HW + 3
        if f['in_play']:
            assert abs(bx) <= HL + TOL_POS and abs(by) <= HW + TOL_POS, ('ball out but in_play', f['t_ms'])
        bs = math.sqrt(bvx * bvx + bvy * bvy + bvz * bvz)
        assert bs <= 40, (bs, f['t_ms'])
        mx['ball_speed'] = max(mx['ball_speed'], bs)
        if prev:
            for j in range(3):
                assert abs((f['ball'][j] - prev['ball'][j]) / dt - f['ball'][j + 3]) <= .0011 / dt + .001
        if f['ball_owner_id'] is not None:
            p = next(p for p in f['players'] if p[0] == f['ball_owner_id'])
            assert math.hypot(bx - p[1], by - p[2]) <= .6
        for kind, e in need_frames.get(f['t_ms'], []):
            if kind == 'offside':
                m = offside_margin(f, e['recipient_id'], e['team_id'], teams)
                if abs(m) > TOL_POS:
                    assert (m > 0) == (e['outcome'] == 'offside'), ('offside mismatch', e['event_id'], m)
                    stats['offside_crosschecks'] += 1
                if e['outcome'] == 'offside':
                    assert e['event_id'] in offside_events
            elif kind == 'dp_offside':
                for o in e['options']:
                    if o['type'] == 'pass':
                        m = offside_margin(f, o['target_player_id'], e['team_id'], teams)
                        if abs(m) > TOL_POS:
                            assert (m > 0) == o['offside'], ('dp offside flag mismatch', e['event_id'], o)
                            stats['dp_option_offside_crosschecks'] += 1
            else:  # ball_out
                if e['line'] == 'touchline':
                    assert abs(by) >= HW - TOL_POS, ('ball_out touchline but ball inside', e['event_id'], f['ball'])
                    exp = 'throw_in'
                else:
                    assert abs(bx) >= HL - TOL_POS, ('ball_out goal_line but ball inside', e['event_id'], f['ball'])
                    home_own_goal_sign = -f['attack_dir']
                    defending = 'HOME' if (1 if bx > 0 else -1) == home_own_goal_sign else 'AWAY'
                    exp = 'corner' if e['last_touch_team_id'] == defending else 'goal_kick'
                nxt = next((r for r in restarts if r['sequence'] > e['sequence']), None)
                if nxt is None:   # clip ended before the restart was taken
                    assert duration_ms - e['available_at_ms'] <= 40000
                    stats['ball_out_crosschecks'] += 1
                    continue
                assert nxt['restart_type'] == exp == e['next_restart'], (e, nxt)
                assert nxt['team_id'] != e['last_touch_team_id']
                stats['ball_out_crosschecks'] += 1
        prev = f
    assert count == n_frames == summary['tracking_frames']
    assert records == summary['player_position_records']
    assert len(snapshots) == duration_ms // 1000 + 1
    assert score == summary['final_score'] and len(events) == summary['event_count']
    final = snapshots[duration_ms]
    for team in ('HOME', 'AWAY'):
        for key, value in counts[team].items():
            assert final['stats'][team][key] == value, (team, key, value)
    assert all(e['pass_event_id'] in event_by_id for e in offside_events.values())
    assert sum(1 for e in events if e['type'] == 'pass' and e['outcome'] == 'out') + \
        sum(1 for e in events if e['type'] == 'shot' and e['outcome'] == 'off_target') == \
        sum(1 for e in events if e['type'] == 'ball_out')
    scan_files = sorted(str(p) for p in root.iterdir() if p.suffix in ('.json', '.jsonl')) + list(extra_scan)
    forbidden = scan_forbidden(scan_files, terms_file)
    report = {'status': 'PASS', 'frame_hz': hz, 'tracking_frames': count, 'events': len(events),
              'event_counts': dict(Counter(e['type'] for e in events)),
              'restart_counts': dict(Counter(e['restart_type'] for e in restarts)),
              'final_score': score,
              'max_player_speed_mps': round(mx['player_speed'], 3),
              'max_player_acceleration_mps2': round(mx['player_acc'], 3),
              'max_turn_rate_radps': round(max_turn, 3),
              'max_ball_speed_mps': round(mx['ball_speed'], 3),
              'decision_points_linked': dp_checked,
              'offside_crosschecks': stats['offside_crosschecks'],
              'decision_option_offside_crosschecks': stats['dp_option_offside_crosschecks'],
              'ball_out_crosschecks': stats['ball_out_crosschecks'],
              'forbidden_scan': forbidden,
              'scope': 'Internal consistency + rule cross-checks; not validation against real football distributions.'}
    (root / 'validation_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('data', nargs='?', type=Path, default=Path(__file__).parent / 'data')
    ap.add_argument('--forbidden', default=str(Path(__file__).parent / 'forbidden_terms.txt'))
    ap.add_argument('--scan', nargs='*', default=[], help='extra files to scan for forbidden terms')
    a = ap.parse_args()
    validate(a.data, a.forbidden, a.scan)
