"""Compact full-match occupancy maps, in fixed physical pitch coordinates."""
import json
from pathlib import Path

COLS, ROWS = 35, 23

class Heatmaps:
    def __init__(self, metadata):
        self.metadata = metadata
        self.players = {p['player_id']: [0] * (COLS * ROWS) for p in metadata['players']}
        self.frames = 0

    def add(self, frame):
        # Final whistle is an endpoint, not an additional tracking interval.
        if frame['t_ms'] >= self.metadata['duration_ms']:
            return
        self.frames += 1
        for pid, x, y, *_ in frame['players']:
            col = min(COLS - 1, max(0, int(x / self.metadata['pitch']['length_m'] * COLS)))
            row = min(ROWS - 1, max(0, int(y / self.metadata['pitch']['width_m'] * ROWS)))
            self.players[pid][row * COLS + col] += 1

    def write(self, directory):
        expected = round(self.metadata['duration_ms'] * self.metadata['tracking_hz'] / 1000)
        if self.frames != expected:
            raise ValueError('Full-match tracking is required for heatmaps')
        result = dict(schema_version='1.0.0', match_id=self.metadata['match_id'],
                      cols=COLS, rows=ROWS, sample_ms=1000 / self.metadata['tracking_hz'],
                      frames=self.frames, coordinate_system='fixed_pitch', players=self.players)
        (Path(directory) / 'heatmaps.json').write_text(json.dumps(result, separators=(',', ':')) + '\n')


def backfill(directory):
    from generate import Match, CLUB_BY_ID, RATINGS, DURATION, HZ, build_summary
    directory = Path(directory)
    metadata = json.loads((directory / 'metadata.json').read_text())
    maps = Heatmaps(metadata)
    tracking = directory / 'tracking.jsonl'
    if tracking.exists():
        with tracking.open() as stream:
            for line in stream:
                maps.add(json.loads(line))
    else:
        home, away = [CLUB_BY_ID[t['club_id']] for t in metadata['teams']]
        sim = Match(metadata['seed'], metadata['match_id'], home, away,
                    [RATINGS[home['club_id']], RATINGS[away['club_id']]], metadata['competition'])
        preview = json.loads((directory / 'preview-60s.json').read_text())
        reference = {frame['t_ms']: frame for frame in preview['frames']}
        for index in range(DURATION * HZ + 1):
            if index:
                sim.step(index)
            frame = sim.tracking(index)
            if frame['t_ms'] in reference and frame != reference[frame['t_ms']]:
                raise ValueError(f'Tracking mismatch in {directory.name}')
            maps.add(frame)
        original = json.loads((directory / 'summary.json').read_text())
        rebuilt = build_summary(sim)
        for key in ('final_score', 'distance_m', 'event_count', 'final_stats'):
            if rebuilt[key] != original[key]:
                raise ValueError(f'{key} mismatch in {directory.name}')
    maps.write(directory)
    print(directory.name, 'full-match heatmaps ready', flush=True)

if __name__ == '__main__':
    import sys
    for directory in sorted(Path(sys.argv[1] if len(sys.argv) > 1 else 'data/league/matches').glob('*')):
        if (directory / 'metadata.json').exists():
            backfill(directory)
