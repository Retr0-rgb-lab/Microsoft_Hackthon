#!/usr/bin/env python3
"""Synthetic football single-match generator -- data format v0.1 (draft).

All clubs, players and venues are fictional.  Only the Python standard library
is required (Python 3.9+).

Output coordinate system (see FORMAT.md):
  origin = centre spot, metres, pitch 105 x 68,
  x along the long axis (-52.5..52.5), y along the short axis (-34..34),
  z up; facing in radians, 0 = +x, counter-clockwise positive, range (-pi, pi].
Internally the simulation keeps a 0..105 / 0..68 frame (y down) and converts
only on output.

Examples
    python3 generate.py --hz 25 --minutes 10 --output sample
    python3 generate.py --hz 10                      # full 100-minute match
"""
import argparse
import json
import math
import random
from collections import Counter
from pathlib import Path

FORMAT_VERSION = '0.1.0'
VERSION = '3.0.0-draft'
HZ = 25
DT = 1 / HZ
HALF = 3000            # seconds per period (45 + 5)
DURATION = 6000        # seconds simulated
MIN_HZ = 10
DEFAULT_MATCH = 'SYN-SINGLE-0001'  # checked-in seed-8 slice only; new matches use SYN-SINGLE-<seed>
SHOT_GAIN_M = 20
# Miss split kept from the old [.12, .43, .45] weights, now conditional on a miss.
SHOT_MISS_SAVED = 0.43
SHOT_MISS_WIDE = 0.45
BASE = [(6, 34), (24, 9), (27, 25), (27, 43), (24, 59),
        (43, 18), (40, 34), (43, 50), (62, 10), (65, 34), (62, 58)]
POSITIONS = ['GK', 'LB', 'LCB', 'RCB', 'RB', 'LCM', 'DM', 'RCM', 'LW', 'ST', 'RW']
MAX_TURN_RATE = 3 * math.pi   # rad/s

HOME = {'team_id': 'HOME', 'club_id': 'HBR', 'name': 'Harbor FC', 'short_name': 'Harbor',
        'venue': 'Harbor Park', 'colors': {'primary': '#0B6E4F', 'secondary': '#FFFFFF'},
        'formation': '4-3-3'}
AWAY = {'team_id': 'AWAY', 'club_id': 'MTN', 'name': 'Mountain FC', 'short_name': 'Mountain',
        'venue': 'Mountain Ground', 'colors': {'primary': '#6B4C9A', 'secondary': '#FFFFFF'},
        'formation': '4-3-3'}
# Invented name parts; validate.py scans the output against a list of real names.
FIRST = ['Aren', 'Bastian', 'Cael', 'Dorin', 'Elio', 'Faris', 'Galen', 'Hollis', 'Ivo',
         'Jory', 'Kael', 'Lucan', 'Mirek', 'Niall', 'Oren', 'Pell', 'Quill', 'Rafe',
         'Soren', 'Tavi', 'Ulric', 'Vero', 'Wren', 'Yanis', 'Zev']
LAST = ['Ashgrove', 'Brindle', 'Coldmere', 'Dunmore', 'Elderby', 'Fallowe', 'Greyholt',
        'Harrowell', 'Inglebrook', 'Juniperr', 'Kestrell', 'Larkspur', 'Marrowby',
        'Northcote', 'Oakhurst', 'Pemberth', 'Quarrie', 'Rookwood', 'Saltmarsh', 'Thornby',
        'Underhill', 'Vantress', 'Whitlow', 'Yarrowby', 'Zellmer']


def clamp(x, low, high):
    return max(low, min(high, x))


def norm(x, y):
    return math.hypot(x, y)


def wrap(a):
    a = (a + math.pi) % (2 * math.pi) - math.pi
    return math.pi if a <= -math.pi else a


def out_xy(x, y):
    """Internal (0..105, 0..68, y down) -> output (centre origin, y up)."""
    return [round(x - 52.5, 3), round(34 - y, 3)]


def in_xy(x, y):
    """Centre-spot metres -> internal, clamped 0.5 m inside the pitch."""
    return clamp(x + 52.5, 0.5, 104.5), clamp(34 - y, 0.5, 67.5)


ROSTER = [f'H{n:02d}' for n in range(1, 12)] + [f'A{n:02d}' for n in range(1, 12)]


def parse_formation(path):
    """22 slots in centre-spot metres. Returns (ordered xy, ball_owner_id or None)."""
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    ball_owner_id = None
    if isinstance(raw, dict):
        slots = raw.get('slots')
        ball_owner_id = raw.get('ball_owner_id')
    else:
        slots = raw
    if not isinstance(slots, list) or len(slots) != 22:
        raise ValueError('formation needs 22 slots in centre-spot metres')
    by_id = {}
    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError('each formation slot must be an object with player_id, x, y')
        pid = slot.get('player_id')
        if pid not in ROSTER or pid in by_id:
            raise ValueError(f'formation player_id must be a unique roster id, got {pid!r}')
        team_name = 'HOME' if pid[0] == 'H' else 'AWAY'
        if slot.get('team_id', team_name) != team_name:
            raise ValueError(f'{pid} team_id does not match the roster')
        try:
            by_id[pid] = (float(slot['x']), float(slot['y']))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f'{pid} needs numeric x and y in centre-spot metres') from exc
    if ball_owner_id is not None and ball_owner_id not in by_id:
        raise ValueError(f'ball_owner_id {ball_owner_id!r} is not one of the 22 slots')
    return [by_id[pid] for pid in ROSTER], ball_owner_id


def encode(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def total_frames():
    return int(round(DURATION * HZ))


def frame_ms(frame):
    return int(round(frame * 1000 / HZ))


class Match:
    def __init__(self, seed, match_id=None, formation=None):
        self.rng = random.Random(seed)
        self.seed = seed
        self.match_id = f'SYN-SINGLE-{seed}' if match_id is None else match_id
        self.home, self.away = HOME, AWAY
        self.t = 0.
        self.period = 1
        names = random.Random(seed + 77)
        pool = [f'{a} {b}' for a in FIRST for b in LAST]
        names.shuffle(pool)
        self.players = []
        # Local anchors in "our attack is +x" coordinates. Away is mirrored once here
        # from BASE; a coach formation is already in centre-spot metres and must not be mirrored again.
        self.anchors = [BASE[i % 11] for i in range(22)]
        self.custom_formation = False
        self.opening_owner = None
        for team in range(2):
            for number, (x, y) in enumerate(BASE, 1):
                self.players.append({
                    'id': f'{"H" if team == 0 else "A"}{number:02}', 'team': team,
                    'number': number, 'x': x if team == 0 else 105 - x, 'y': y,
                    'vx': 0., 'vy': 0., 'facing': 0. if team == 0 else math.pi,
                    'active': True, 'position': POSITIONS[number - 1], 'starter': True,
                    'name': pool.pop(), 'shirt_number': number})
        if formation is not None:
            self._install_formation(*formation)
        self.player_by_id = {p['id']: p for p in self.players}
        self.distances = {p['id']: 0. for p in self.players}
        self.position_records = 0
        self.ball = [52.5, 34., 0.]
        self.last_ball = self.ball[:]
        self.ball_v = [0., 0., 0.]
        self.owner = None
        self.possession_team = None
        self.possession = 0
        self.score = [0, 0]
        self.stats = [{'passes': 0, 'completed_passes': 0, 'shots': 0, 'shots_on_target': 0,
                       'interceptions': 0, 'pressure_events': 0, 'offsides': 0,
                       'ball_out': 0, 'possession_seconds': 0.} for _ in range(2)]
        self.events = []
        self.event_seq = 0
        self.action_seq = 0
        self.pressure_last = {}
        self.action = None
        self.emit('period_start', period=1)
        if self.opening_owner is None:
            self.start_restart(0, (52.5, 34), 'kick_off', minimum=12)
        else:
            self.owner = self.opening_owner
            self.ball = self.foot(self.owner)
            self.last_ball = self.ball[:]
            self.set_possession(self.players[self.owner]['team'], 'drill_start')
            self.start_carry_after_restart()

    def _install_formation(self, slots, ball_owner_id):
        """Replace BASE anchors. `slots` are centre-spot (x, y) in roster order."""
        for i, (x, y) in enumerate(slots):
            ix, iy = in_xy(x, y)
            p = self.players[i]
            p['x'], p['y'] = ix, iy
            p['vx'] = p['vy'] = 0.
            p['facing'] = 0. if p['team'] == 0 else math.pi
            # Home local == internal. Away local_x folds once so direction == -1 lands on ix.
            self.anchors[i] = (ix, iy) if p['team'] == 0 else (105 - ix, iy)
        self.custom_formation = any(
            abs(self.anchors[i][0] - BASE[i % 11][0]) > 1e-3 or
            abs(self.anchors[i][1] - BASE[i % 11][1]) > 1e-3
            for i in range(22))
        if ball_owner_id is not None:
            self.opening_owner = next(i for i, p in enumerate(self.players) if p['id'] == ball_owner_id)

    # ---- helpers -------------------------------------------------------
    def direction(self, team):
        return 1 if (team == 0) == (self.period == 1) else -1

    def progress(self, x, team):
        return x if self.direction(team) == 1 else 105 - x

    @staticmethod
    def team_id(team):
        return None if team is None else ['HOME', 'AWAY'][team]

    def opponents(self, team, outfield=False):
        lo = (1 - team) * 11 + (1 if outfield else 0)
        return [i for i in range(lo, (1 - team) * 11 + 11) if self.players[i]['active']]

    def emit(self, kind, start=None, **kwargs):
        self.event_seq += 1
        ms = int(round(self.t * 1000))
        ev = {'event_id': f'e{self.event_seq:06}', 'sequence': self.event_seq,
              'match_id': self.match_id, 'type': kind, 'period': self.period,
              'period_ms': ms - (self.period - 1) * HALF * 1000,
              'start_ms': ms if start is None else int(round(start * 1000)),
              'end_ms': ms, 'available_at_ms': ms, 'possession_id': self.possession}
        ev.update(kwargs)
        self.events.append(ev)
        return ev['event_id']

    def new_action(self, kind, duration, **kwargs):
        self.action_seq += 1
        self.action = {'id': f'a{self.action_seq:06}', 'kind': kind, 'start': self.t,
                       'end': round(self.t + max(1, math.ceil(duration / DT - 1e-9)) * DT, 6),
                       'start_ball': self.ball[:], **kwargs}

    def set_possession(self, team, reason, cause=None):
        if team != self.possession_team:
            old = self.possession_team
            self.possession += 1
            self.possession_team = team
            self.emit('possession_change', from_team_id=self.team_id(old),
                      to_team_id=self.team_id(team), reason=reason,
                      related_event_ids=[cause] if cause else [])

    def start_restart(self, team, spot, reason, minimum=6):
        self.owner = None
        if reason == 'kick_off':
            candidates = [team * 11 + 9]
        elif reason in ('goal_kick', 'keeper_restart'):
            candidates = [team * 11]
        else:
            candidates = [i for i in range(team * 11 + 1, team * 11 + 11) if self.players[i]['active']]
        taker = min(candidates, key=lambda i: norm(self.players[i]['x'] - spot[0],
                                                  self.players[i]['y'] - spot[1]))
        distance = norm(self.players[taker]['x'] - spot[0], self.players[taker]['y'] - spot[1])
        ball_distance = norm(self.ball[0] - spot[0], self.ball[1] - spot[1])
        duration = max(minimum, distance / 3 + 3, ball_distance / 6 + 1)
        self.new_action('restart_setup', duration, team=team, receiver=taker,
                        target=list(spot), reason=reason)

    # ---- movement ------------------------------------------------------
    def target_position(self, index):
        p = self.players[index]
        team, slot = p['team'], index % 11
        direction = self.direction(team)
        bx, by = self.ball[:2]
        local_ball = self.progress(bx, team)
        own = self.possession_team == team
        base_x, base_y = self.anchors[index]
        if slot == 0 and not self.custom_formation:
            x = clamp(5 + .05 * (local_ball - 45), 2.5, 11)
            y = clamp(34 + .15 * (by - 34), 26, 42)
        elif slot == 0:
            x = clamp(base_x + .05 * (local_ball - 45), 1, 104)
            y = clamp(base_y + .15 * (by - 34), 1, 67)
        else:
            x = clamp(base_x + .35 * (local_ball - 52.5) + (7 if own else -3), 7, 97)
            y = clamp(base_y + .18 * (by - 34) + 1.5 * math.sin(self.t * .18 + index * 1.4), 2, 66)
            x += 1.4 * math.sin(self.t * .13 + index * .9)
        # Forwards time runs onto the opponents' second-last line when their side has the ball.
        if own and slot in (8, 9, 10) and math.sin(self.t * .11 + index * 2.1) > .55:
            x = clamp(self.line_cache[team] + 1.5, 55, 100)
        target = [x if direction == 1 else 105 - x, y]
        a = self.action
        if a['kind'] in ('restart_setup', 'pass') and index == a.get('receiver'):
            return a['target'][:2]
        if a['kind'] == 'carry' and index == self.owner:
            return a['target'][:]
        if a['kind'] == 'shot' and index == a['actor']:
            return [p['x'], p['y']]
        if self.owner is not None and p['team'] != self.players[self.owner]['team'] and slot != 0:
            carrier = self.players[self.owner]
            near = sorted(self.opponents(carrier['team'], True),
                          key=lambda i: norm(self.players[i]['x'] - carrier['x'],
                                             self.players[i]['y'] - carrier['y']))[:2]
            if index in near:
                rank = near.index(index)
                target = [carrier['x'] + direction * (1.0 + rank * 1.4),
                          clamp(carrier['y'] + (1 if rank else -1) * 1.2, 1, 67)]
        return target

    def move_players(self):
        self.line_cache = {}
        for team in range(2):
            ds = sorted((self.progress(self.players[j]['x'], team) for j in self.opponents(team)), reverse=True)
            self.line_cache[team] = ds[1] if len(ds) > 1 else 52.5
        targets = [self.target_position(i) for i in range(22)]
        for i, p in enumerate(self.players):
            if not p['active']:
                continue
            tx, ty = targets[i]
            dx, dy = tx - p['x'], ty - p['y']
            dist = norm(dx, dy)
            cap = 6.5 if i == self.owner else 7.2
            desired_speed = min(cap, dist * 1.4)
            dvx = dx / max(dist, 1e-9) * desired_speed
            dvy = dy / max(dist, 1e-9) * desired_speed
            dvx = clamp(dvx, -math.sqrt(4 * max(0, p['x'] - 1.5)), math.sqrt(4 * max(0, 103.5 - p['x'])))
            dvy = clamp(dvy, -math.sqrt(4 * max(0, p['y'] - 1.5)), math.sqrt(4 * max(0, 66.5 - p['y'])))
            speed_now = norm(p['vx'], p['vy'])
            stop_x = abs(p['vx']) * speed_now / 7 + abs(p['vx']) * DT + .8
            stop_y = abs(p['vy']) * speed_now / 7 + abs(p['vy']) * DT + .8
            if ((p['vx'] < 0 and p['x'] - .5 < stop_x) or (p['vx'] > 0 and 104.5 - p['x'] < stop_x) or
                    (p['vy'] < 0 and p['y'] - .5 < stop_y) or (p['vy'] > 0 and 67.5 - p['y'] < stop_y)):
                dvx = dvy = 0.
            ax, ay = dvx - p['vx'], dvy - p['vy']
            factor = min(1., 3.5 * DT / max(norm(ax, ay), 1e-9))
            vx, vy = p['vx'] + ax * factor, p['vy'] + ay * factor
            x, y = clamp(p['x'] + vx * DT, .5, 104.5), clamp(p['y'] + vy * DT, .5, 67.5)
            p['vx'], p['vy'] = (x - p['x']) / DT, (y - p['y']) / DT
            self.distances[p['id']] += norm(x - p['x'], y - p['y'])
            p['x'], p['y'] = x, y
            # Facing (output convention: y up, CCW positive): run direction when
            # moving, otherwise look at the ball; turn rate limited.
            if norm(p['vx'], p['vy']) > 1.0:
                want = math.atan2(-p['vy'], p['vx'])
            else:
                want = math.atan2(-(self.ball[1] - p['y']), self.ball[0] - p['x'])
            diff = wrap(want - p['facing'])
            step = MAX_TURN_RATE * DT
            p['facing'] = wrap(p['facing'] + clamp(diff, -step, step))

    def foot(self, owner):
        p = self.players[owner]
        return [p['x'] + .35 * self.direction(p['team']), p['y'], 0.]

    # ---- decision model ------------------------------------------------
    def xt(self, x, y, team):
        px = self.progress(x, team)
        return 0.02 + 0.40 * math.exp(-norm(105 - px, y - 34) / 12)

    def offside_info(self, i, team):
        """Law 11 simplified: in opponent half, ahead of ball and of the second-last opponent."""
        q = self.players[i]
        px = self.progress(q['x'], team)
        ds = sorted((self.progress(self.players[j]['x'], team) for j in self.opponents(team)), reverse=True)
        second_last = ds[1] if len(ds) > 1 else 0.
        line = max(second_last, self.progress(self.ball[0], team), 52.5)
        margin = px - line
        return margin > 0, margin

    def pass_prob(self, target, team):
        sx, sy = self.ball[:2]
        tx, ty = target
        length = norm(tx - sx, ty - sy)
        risk = 0.
        for j in self.opponents(team):
            o = self.players[j]
            t = clamp(((o['x'] - sx) * (tx - sx) + (o['y'] - sy) * (ty - sy)) / max(length ** 2, 1e-9), 0, 1)
            d = norm(sx + t * (tx - sx) - o['x'], sy + t * (ty - sy) - o['y'])
            risk += math.exp(-d * d / 8) * (.35 + .4 * t)
        return clamp(.95 - risk - .006 * max(0, length - 15), .05, .97)

    def xg(self, x, y, team):
        px = self.progress(x, team)
        d = norm(105 - px, y - 34)
        angle = abs(math.atan2(7.32 * (105 - px), (105 - px) ** 2 + (y - 34) ** 2 - 3.66 ** 2))
        return clamp(1 / (1 + math.exp(-(-1.1 + 1.6 * angle - .09 * d))), .01, .7)

    def _nearest_opponent(self, team, x, y):
        opps = self.opponents(team)
        if not opps:
            return float('inf')
        return min(norm(self.players[j]['x'] - x, self.players[j]['y'] - y) for j in opps)

    def _shot_option(self, direction, x, y, team):
        """Goal-line aim is fixed on the option. A goal uses xG; misses stay 0.43:0.45."""
        goal_x = 105. if direction == 1 else 0.
        xg = round(self.xg(x, y, team), 4)
        if self.rng.random() < xg:
            outcome = 'goal'
        elif self.rng.random() < SHOT_MISS_SAVED / (SHOT_MISS_SAVED + SHOT_MISS_WIDE):
            outcome = 'saved'
        else:
            outcome = 'off_target'
        if outcome == 'off_target':
            aim_y = 34 + self.rng.choice([-1, 1]) * self.rng.uniform(4.2, 8)
        else:
            aim_y = 34 + self.rng.uniform(-2.8, 2.8)
        return [goal_x, aim_y], xg, outcome

    @staticmethod
    def _option_value(opt):
        if opt['type'] == 'shot':
            return opt['success_prob'] * SHOT_GAIN_M
        return opt['success_prob'] * max(opt['progress_m'], 0)

    def choose_action(self):
        p = self.players[self.owner]
        team = p['team']
        d = self.direction(team)
        bx, by = self.ball[:2]
        xt0 = self.xt(bx, by, team)
        options = []
        for i in range(team * 11 + 1, team * 11 + 11):
            if i == self.owner or not self.players[i]['active']:
                continue
            q = self.players[i]
            target = [clamp(q['x'] + q['vx'] * .25, 1, 104), clamp(q['y'] + q['vy'] * .25, 1, 67)]
            off, margin = self.offside_info(i, team)
            options.append({'type': 'pass', 'idx': i, 'target': target,
                            'p': self.pass_prob(target, team), 'offside': off, 'margin': margin})
        if p['number'] != 1:
            target = [clamp(p['x'] + d * self.rng.uniform(3, 12), 3, 102),
                      clamp(p['y'] + self.rng.uniform(-7, 7), 3, 65)]
            press = sum(1 for j in self.opponents(team) if norm(self.players[j]['x'] - p['x'], self.players[j]['y'] - p['y']) < 5)
            options.append({'type': 'carry', 'idx': None, 'target': target,
                            'p': clamp(.95 - .12 * press, .4, .95), 'offside': False, 'margin': None})
            shot_target, shot_p, shot_outcome = self._shot_option(d, p['x'], p['y'], team)
            options.append({'type': 'shot', 'idx': None, 'target': shot_target,
                            'p': shot_p, 'offside': False, 'margin': None,
                            'shot_outcome': shot_outcome})
        progress0 = self.progress(bx, team)
        listed = []
        for k, o in enumerate(options):
            tx, ty = o['target']
            listed.append({'option_id': f'o{k + 1}', 'type': o['type'],
                           'target_player_id': self.players[o['idx']]['id'] if o['idx'] is not None else None,
                           'end_location': out_xy(tx, ty),
                           'success_prob': round(o['p'], 4),
                           'progress_m': round(self.progress(tx, team) - progress0, 3),
                           'xt_end': round(self.xt(tx, ty, team), 4),
                           'xt_gain': round(self.xt(tx, ty, team) - xt0, 4),
                           'offside': o['offside'],
                           'offside_margin_m': None if o['margin'] is None else round(o['margin'], 3)})
        # Offside passes stay in options[] but do not compete. Ties: higher success_prob, then smaller option_id.
        eligible = [k for k, o in enumerate(listed) if not o['offside']]
        pool = eligible or list(range(len(listed)))
        winner = min(pool, key=lambda k: (
            -self._option_value(listed[k]), -listed[k]['success_prob'], listed[k]['option_id']))
        chosen = options[winner]
        row = listed[winner]
        label_value = self._option_value(row)
        nearest = self._nearest_opponent(team, p['x'], p['y'])
        all_zero = not eligible or all(self._option_value(listed[k]) == 0 for k in eligible)
        if all_zero or (row['type'] == 'carry' and row['progress_m'] < 4 and nearest <= 3):
            label_class, route_kind, route_target_id, route_end = 'hold', '', None, None
        elif row['type'] == 'pass':
            label_class, route_kind = 'pass', 'pass'
            route_target_id, route_end = row['target_player_id'], row['end_location']
        elif row['type'] == 'shot':
            label_class, route_kind = 'shoot', 'shoot'
            route_target_id, route_end = None, row['end_location']
        else:
            label_class, route_kind = 'dribble', 'dribble'
            route_target_id, route_end = p['id'], row['end_location']
        dp = self.emit('decision_point', team_id=self.team_id(team), player_id=p['id'],
                       location=out_xy(bx, by), xt_start=round(xt0, 4), options=listed,
                       chosen_index=winner, chosen_option_id=row['option_id'],
                       policy='value_v1', label_class=label_class,
                       label_value=round(label_value, 6), shot_gain_m=SHOT_GAIN_M,
                       route_kind=route_kind, route_target_id=route_target_id, route_end=route_end)
        if chosen['type'] == 'shot':
            self.start_shot(chosen, dp)
        elif chosen['type'] == 'carry':
            self.new_action('carry', self.rng.uniform(1.6, 4.8), actor=self.owner, team=team,
                            target=chosen['target'], decision=dp, success_prob=row['success_prob'])
        else:
            self.start_pass(chosen, dp)

    def exit_point(self, sx, sy, tx, ty):
        dx, dy = tx - sx, ty - sy
        L = norm(dx, dy)
        if L < 1e-6:
            dx, dy, L = 0., 1., 1.
        dx, dy = dx / L, dy / L
        ts = []
        if dx > 1e-9: ts.append(((105 - sx) / dx, 'goal_line'))
        if dx < -1e-9: ts.append(((0 - sx) / dx, 'goal_line'))
        if dy > 1e-9: ts.append(((68 - sy) / dy, 'touchline'))
        if dy < -1e-9: ts.append(((0 - sy) / dy, 'touchline'))
        t, line = min(ts)
        t += .3
        return [sx + dx * t, sy + dy * t], line

    def start_pass(self, o, dp):
        team = self.players[self.owner]['team']
        intended = o['idx']
        success = self.rng.random() < o['p']
        out_line = None
        receiver = intended
        if not success:
            if self.rng.random() < .15:
                # Over-hit / mis-hit pass: extend the line of the pass until it leaves the pitch.
                spread = self.rng.uniform(-.35, .35)
                tx, ty = o['target']
                sx, sy = self.ball[:2]
                ang = math.atan2(ty - sy, tx - sx) + spread
                target, out_line = self.exit_point(sx, sy, sx + math.cos(ang), sy + math.sin(ang))
                receiver = None
            else:
                q = self.players[intended]
                receiver = min(self.opponents(team, True),
                               key=lambda i: norm(self.players[i]['x'] - q['x'], self.players[i]['y'] - q['y']))
        if receiver is not None:
            r = self.players[receiver]
            target = [clamp(r['x'] + r['vx'] * .25, 1, 104), clamp(r['y'] + r['vy'] * .25, 1, 67)]
        distance = norm(target[0] - self.ball[0], target[1] - self.ball[1])
        duration = max(.6, distance / self.rng.uniform(11, 18))
        p = self.players[self.owner]
        under_pressure = any(norm(self.players[j]['x'] - p['x'], self.players[j]['y'] - p['y']) < 3
                             for j in self.opponents(team))
        q = self.players[intended]
        self.new_action('pass', duration, actor=self.owner, team=team, intended=intended,
                        receiver=receiver, target=target, success=success, out_line=out_line,
                        offside=o['offside'] and success, offside_margin=o['margin'],
                        offside_spot=[q['x'], q['y']], under_pressure=under_pressure,
                        decision=dp, height=1.8 if distance > 25 and self.rng.random() < .3 else 0.)
        self.owner = None

    def start_shot(self, o, dp):
        """Fly to the goal-line point already stored on the shot option."""
        team = self.players[self.owner]['team']
        goal_x, aim_y = o['target']
        receiver = (1 - team) * 11
        target = [goal_x, aim_y, self.rng.uniform(.2, 1.7)]
        distance = norm(target[0] - self.ball[0], target[1] - self.ball[1])
        self.new_action('shot', max(.4, distance / self.rng.uniform(20, 30)), actor=self.owner, team=team,
                        receiver=receiver, target=target, outcome=o['shot_outcome'], decision=dp,
                        xg=round(o['p'], 4))
        self.owner = None

    def update_ball(self):
        a = self.action
        u = clamp((self.t - a['start']) / (a['end'] - a['start']), 0, 1)
        if a['kind'] == 'carry':
            self.ball = self.foot(self.owner)
        elif a['kind'] == 'pass':
            target = self.foot(a['receiver']) if a['receiver'] is not None else a['target'] + [0.]
            self.ball = [(1 - u) * a['start_ball'][j] + u * target[j] for j in range(3)]
            self.ball[2] = a['height'] * 4 * u * (1 - u)
        elif a['kind'] == 'shot':
            target = a['target']
            self.ball = [(1 - u) * a['start_ball'][j] + u * target[j] for j in range(3)]
            self.ball[2] += .8 * 4 * u * (1 - u)
        elif a['kind'] == 'restart_setup':
            b = min(1., u * 1.8)
            b = b * b * (3 - 2 * b)
            if u < .9 and not a.get('at_spot'):
                spot = a['target'] + [0.]
                self.ball = [(1 - b) * a['start_ball'][j] + b * spot[j] for j in range(3)]
            else:
                a['at_spot'] = True
                f = self.foot(a['receiver'])
                dx, dy = f[0] - self.ball[0], f[1] - self.ball[1]
                d = norm(dx, dy)
                k = min(1., 6 * DT / max(d, 1e-9))
                self.ball = [self.ball[0] + dx * k, self.ball[1] + dy * k, 0.]

    def start_carry_after_restart(self):
        p = self.players[self.owner]
        d = self.direction(p['team'])
        self.new_action('carry', self.rng.uniform(1.6, 4.8), actor=self.owner, team=p['team'], decision=None,
                        target=[clamp(p['x'] + d * self.rng.uniform(3, 12), 3, 102),
                                clamp(p['y'] + self.rng.uniform(-7, 7), 3, 65)])

    def handle_out(self, last_team, line, cause):
        x, y = self.ball[:2]
        if line == 'touchline':
            restart, team = 'throw_in', 1 - last_team
            spot = (clamp(x, 2, 103), 1.5 if y < 34 else 66.5)
        else:
            end_x = 0. if x < 52.5 else 105.
            defending = 0 if (self.direction(0) == 1) == (end_x == 0.) else 1
            if last_team == defending:
                restart, team = 'corner', 1 - defending
                spot = (1.5 if end_x == 0. else 103.5, 1.5 if y < 34 else 66.5)
            else:
                restart, team = 'goal_kick', defending
                spot = (5.5 if end_x == 0. else 99.5, 34.)
        self.stats[last_team]['ball_out'] += 1
        eid = self.emit('ball_out', team_id=self.team_id(last_team), last_touch_team_id=self.team_id(last_team),
                        line=line, location=out_xy(x, y), next_restart=restart,
                        restart_team_id=self.team_id(team), related_event_ids=[cause])
        self.emit('stoppage', reason='ball_out', related_event_ids=[eid])
        self.start_restart(team, spot, restart, minimum=6 if restart == 'throw_in' else 8)

    def finish_action(self):
        a = self.action
        common = {'action_id': a['id'], 'team_id': self.team_id(a['team']),
                  'start_location': out_xy(*a['start_ball'][:2]),
                  'end_location': out_xy(*self.ball[:2]),
                  'duration_ms': int(round((self.t - a['start']) * 1000))}
        if a.get('decision'):
            common['decision_event_id'] = a['decision']
        if a['kind'] == 'restart_setup':
            self.owner = a['receiver']
            self.set_possession(a['team'], a['reason'])
            self.emit('restart', start=a['start'], player_id=self.players[self.owner]['id'],
                      restart_type=a['reason'], **common)
            self.start_carry_after_restart()
        elif a['kind'] == 'carry':
            self.emit('carry', start=a['start'], player_id=self.players[a['actor']]['id'], **common)
            prob = a.get('success_prob')
            if prob is not None and self.rng.random() >= prob:
                carrier = self.players[a['actor']]
                nearest, nearest_d = None, None
                for j in self.opponents(a['team']):
                    q = self.players[j]
                    dist = norm(q['x'] - carrier['x'], q['y'] - carrier['y'])
                    if dist <= 5 and (nearest_d is None or dist < nearest_d):
                        nearest, nearest_d = j, dist
                if nearest is not None:
                    self.owner = nearest
                    self.ball = self.foot(nearest)
                    self.last_ball = self.ball[:]
                    self.set_possession(self.players[nearest]['team'], 'turnover')
                    self.start_carry_after_restart()
                    return
            self.choose_action()
        elif a['kind'] == 'pass':
            team = a['team']
            self.stats[team]['passes'] += 1
            if a['out_line']:
                outcome = 'out'
            elif not a['success']:
                outcome = 'intercepted'
            elif a['offside']:
                outcome = 'offside'
            else:
                outcome = 'complete'
            self.stats[team]['completed_passes'] += int(outcome == 'complete')
            eid = self.emit('pass', start=a['start'], player_id=self.players[a['actor']]['id'],
                            recipient_id=self.players[a['intended']]['id'],
                            actual_receiver_id=None if a['receiver'] is None else self.players[a['receiver']]['id'],
                            outcome=outcome, under_pressure=a['under_pressure'],
                            pass_height='high' if a['height'] else 'ground', **common)
            if outcome == 'out':
                self.handle_out(team, a['out_line'], eid)
                return
            self.owner = a['receiver']
            if outcome == 'offside':
                self.stats[team]['offsides'] += 1
                oid = self.emit('offside', team_id=self.team_id(team), player_id=self.players[a['intended']]['id'],
                                location=out_xy(*a['offside_spot']), offside_margin_m=round(a['offside_margin'], 3),
                                pass_event_id=eid, related_event_ids=[eid])
                self.emit('stoppage', reason='offside', related_event_ids=[oid])
                self.start_restart(1 - team, tuple(a['offside_spot']), 'indirect_free_kick', minimum=8)
                return
            if outcome == 'intercepted':
                other = 1 - team
                self.stats[other]['interceptions'] += 1
                self.emit('interception', team_id=self.team_id(other), player_id=self.players[self.owner]['id'],
                          location=out_xy(*self.ball[:2]), related_event_ids=[eid])
                self.set_possession(other, 'interception', eid)
            self.start_carry_after_restart()
        elif a['kind'] == 'shot':
            team = a['team']
            self.stats[team]['shots'] += 1
            self.stats[team]['shots_on_target'] += int(a['outcome'] != 'off_target')
            if a['outcome'] == 'goal':
                self.score[team] += 1
            eid = self.emit('shot', start=a['start'], player_id=self.players[a['actor']]['id'],
                            outcome=a['outcome'], xg=a['xg'], score=self.score[:], **common)
            if a['outcome'] == 'goal':
                self.emit('stoppage', reason='goal', related_event_ids=[eid])
                self.start_restart(1 - team, (52.5, 34), 'kick_off', minimum=20)
            elif a['outcome'] == 'saved':
                self.emit('save', team_id=self.team_id(1 - team), player_id=self.players[a['receiver']]['id'],
                          related_event_ids=[eid])
                q = self.players[a['receiver']]
                self.start_restart(1 - team, (q['x'], q['y']), 'keeper_restart', minimum=4)
            else:
                # 30 % of misses take a defender's deflection -> corner.
                last = 1 - team if self.rng.random() < .3 else team
                self.handle_out(last, 'goal_line', eid)

    def step(self, frame):
        self.t = frame / HZ
        if DURATION > HALF and frame == HALF * HZ:
            self.emit('action_cancelled', action_id=self.action['id'], reason='half_time',
                      decision_event_id=self.action.get('decision'))
            self.emit('period_end', period=1)
            self.period = 2
            self.emit('period_start', period=2)
            self.possession_team = None
            self.start_restart(1, (52.5, 34), 'kick_off', minimum=32)
        self.move_players()
        self.update_ball()
        self.ball_v = [(self.ball[j] - self.last_ball[j]) / DT for j in range(3)]
        self.last_ball = self.ball[:]
        if self.action['kind'] != 'restart_setup' and self.possession_team is not None:
            self.stats[self.possession_team]['possession_seconds'] += DT
        if self.owner is not None and self.action['kind'] == 'carry':
            carrier = self.players[self.owner]
            for j in self.opponents(carrier['team']):
                q = self.players[j]
                if norm(q['x'] - carrier['x'], q['y'] - carrier['y']) < 3:
                    pair = (q['id'], carrier['id'])
                    if self.t - self.pressure_last.get(pair, -100) > 6:
                        self.pressure_last[pair] = self.t
                        self.stats[q['team']]['pressure_events'] += 1
                        self.emit('pressure', team_id=self.team_id(q['team']), player_id=q['id'],
                                  target_player_id=carrier['id'], radius_m=3, location=out_xy(q['x'], q['y']),
                                  method='distance_threshold')
        a = self.action
        ready = True
        if a['kind'] == 'restart_setup':
            # Do not hand over the ball until the taker has actually reached it.
            tk = self.players[a['receiver']]
            f = self.foot(a['receiver'])
            ready = norm(f[0] - self.ball[0], f[1] - self.ball[1]) < .05 or self.t > a['end'] + 30
            if self.t >= a['end'] - 1e-6 and not ready:
                a['end'] = self.t + DT   # keep u < 1 path at the spot; re-test next frame
        if self.t >= self.action['end'] - 1e-6 and ready:
            self.finish_action()
        if frame == total_frames():
            self.emit('action_cancelled', action_id=self.action['id'], reason='full_time',
                      decision_event_id=self.action.get('decision'))
            self.emit('period_end', period=self.period)
            self.emit('match_end', score=self.score[:])

    def tracking(self, frame):
        a = self.action
        ms = frame_ms(frame)
        live = frame < total_frames()
        bx, by = out_xy(*self.ball[:2])
        bvx, bvy, bvz = self.ball_v
        return {'frame_id': frame, 't_ms': ms, 'period': self.period,
                'period_ms': ms - (self.period - 1) * HALF * 1000,
                'attack_dir': self.direction(0),
                'in_play': a['kind'] != 'restart_setup' and live,
                'phase': a['kind'] if live else 'ended', 'action_id': a['id'],
                'possession_team_id': self.team_id(self.possession_team),
                'ball_owner_id': None if self.owner is None else self.players[self.owner]['id'],
                'score': self.score[:],
                'players': [[p['id'], *out_xy(p['x'], p['y']), round(p['vx'], 3), round(-p['vy'], 3),
                             round(p['facing'], 4)] for p in self.players if p['active']],
                'ball': [bx, by, round(self.ball[2], 3), round(bvx, 3), round(-bvy, 3), round(bvz, 3)]}

    def snapshot(self, frame):
        total = sum(s['possession_seconds'] for s in self.stats)
        stats = {self.team_id(i): {**s, 'possession_seconds': round(s['possession_seconds'], 1),
                                   'possession_pct': round(s['possession_seconds'] / total * 100, 2) if total else None,
                                   'pass_accuracy_pct': round(s['completed_passes'] / s['passes'] * 100, 2) if s['passes'] else None}
                 for i, s in enumerate(self.stats)}
        return {'t_ms': frame_ms(frame), 'period': self.period, 'score': self.score[:],
                'in_play': self.action['kind'] != 'restart_setup' and frame < total_frames(),
                'last_event_sequence': self.event_seq, 'stats': stats}


def build_metadata(sim):
    periods = [{'period': 1, 'start_ms': 0, 'duration_ms': min(DURATION, HALF) * 1000,
                'home_attack_dir': 1}]
    if DURATION > HALF:
        periods.append({'period': 2, 'start_ms': HALF * 1000, 'duration_ms': (DURATION - HALF) * 1000,
                        'home_attack_dir': -1})
    return {
        'format_version': FORMAT_VERSION, 'schema_version': FORMAT_VERSION,
        'match_id': sim.match_id, 'synthetic': True, 'fictional_entities': True,
        'seed': sim.seed, 'generator': f'generate.py v{VERSION}',
        'frame_hz': HZ, 'min_frame_hz': MIN_HZ,
        'duration_ms': DURATION * 1000, 'frame_count': total_frames() + 1,
        'clip': DURATION < 2 * HALF,
        'coordinate_system': {
            'origin': 'centre_spot', 'units': 'm', 'pitch_length_m': 105, 'pitch_width_m': 68,
            'x': 'along the long axis (touchline direction), range [-52.5, 52.5]',
            'y': 'along the short axis (goal-line direction), range [-34, 34]; right-handed with x and z',
            'z': 'up, ground = 0',
            'facing': 'radians in (-pi, pi]; 0 = +x, counter-clockwise positive',
            'attack_dir': '+1 = HOME attacks towards +x in this frame, -1 = towards -x; AWAY is always the opposite',
            'goals': {'x_neg': [-52.5, 0], 'x_pos': [52.5, 0], 'goal_width_m': 7.32}},
        'periods': periods,
        'teams': [{**{k: t[k] for k in ('team_id', 'club_id', 'name', 'short_name', 'colors', 'formation')},
                   'formation': 'custom' if sim.custom_formation else t['formation']}
                  for t in (HOME, AWAY)],
        'venue': {'name': HOME['venue'], 'fictional': True},
        'players': [{'player_id': p['id'], 'team_id': sim.team_id(p['team']), 'jersey_number': p['shirt_number'],
                     'name': p['name'], 'position': p['position'], 'starter': True} for p in sim.players],
        'columns': {'tracking.players': ['player_id', 'x_m', 'y_m', 'vx_mps', 'vy_mps', 'facing_rad'],
                    'tracking.ball': ['x_m', 'y_m', 'z_m', 'vx_mps', 'vy_mps', 'vz_mps']},
        'limitations': ['Procedural motion, not a physics simulator; ball height is a parabolic arc, no bounce.',
                        ('Custom formation anchors.' if sim.custom_formation else 'Single formation (4-3-3).')
                        + ' No tackles, dribble duels, fouls or cards in v0.1.',
                        'Offside uses a simplified Law 11 test at pass time; no interfering-with-play nuance.',
                        'All teams, players and venues are fictional.',
                        'Outcomes exist only in resolved events at available_at_ms; do not expose future events during replay.']}


def build_summary(sim):
    return {'match_id': sim.match_id, 'seed': sim.seed, 'frame_hz': HZ, 'duration_seconds': DURATION,
            'tracking_frames': total_frames() + 1, 'player_position_records': sim.position_records,
            'state_snapshots': DURATION + 1, 'event_count': len(sim.events),
            'event_counts': dict(Counter(e['type'] for e in sim.events)),
            'restart_counts': dict(Counter(e['restart_type'] for e in sim.events if e['type'] == 'restart')),
            'final_score': sim.score, 'final_stats': sim.snapshot(total_frames())['stats'],
            'distance_m': {pid: round(d, 1) for pid, d in sim.distances.items()}}


def generate(out, seed, formation=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    sim = Match(seed, formation=formation)
    metadata = build_metadata(sim)
    (out / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    with (out / 'tracking.jsonl').open('w') as tr, (out / 'states.jsonl').open('w') as st:
        for frame in range(total_frames() + 1):
            if frame:
                sim.step(frame)
            data = sim.tracking(frame)
            sim.position_records += len(data['players'])
            tr.write(encode(data) + '\n')
            if frame % HZ == 0:
                st.write(encode(sim.snapshot(frame)) + '\n')
    with (out / 'events.jsonl').open('w') as ev:
        for e in sim.events:
            ev.write(encode(e) + '\n')
    summary = build_summary(sim)
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: summary[k] for k in ('match_id', 'frame_hz', 'duration_seconds', 'tracking_frames',
                                             'event_count', 'event_counts', 'restart_counts', 'final_score')},
                     ensure_ascii=False, indent=2))
    return summary


def main():
    global HZ, DT, DURATION
    ap = argparse.ArgumentParser(description='Synthetic football single-match generator (format v0.1)')
    ap.add_argument('--hz', type=int, default=25, help=f'tracking frame rate, integer >= {MIN_HZ} (default 25)')
    ap.add_argument('--minutes', type=int, default=100,
                    help='simulated minutes (default 100 = two 50-min periods; <=50 gives a period-1 clip)')
    ap.add_argument('--seed', type=int, default=20261019)
    ap.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'data')
    ap.add_argument('--formation', type=Path, default=None,
                    help='optional JSON: 22 slots in centre-spot metres (player_id, x, y); movement anchors')
    a = ap.parse_args()
    if a.hz < MIN_HZ:
        ap.error(f'--hz must be >= {MIN_HZ}')
    if not 1 <= a.minutes <= 100:
        ap.error('--minutes must be 1..100')
    formation = None
    if a.formation is not None:
        try:
            formation = parse_formation(a.formation)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            ap.error(str(exc))
    HZ, DT, DURATION = a.hz, 1 / a.hz, a.minutes * 60
    generate(a.output, a.seed, formation)


if __name__ == '__main__':
    main()
