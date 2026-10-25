import test from 'node:test';
import assert from 'node:assert/strict';
import { playerStats, heatmapSVG } from '../player-analysis.js';

test('Player totals distinguish attempted/completed passes and shots on target', () => {
  const events = [
    { player_id: 'H01', type: 'pass', outcome: 'complete' },
    { player_id: 'H01', type: 'pass', outcome: 'intercepted' },
    ...['goal', 'saved', 'off_target'].map(outcome => ({ player_id: 'H01', type: 'shot', outcome })),
    { player_id: 'A01', type: 'shot', outcome: 'goal' },
    { player_id: 'H01', type: 'action_cancelled', outcome: 'goal' },
  ];
  assert.deepEqual(playerStats('H01', events, { distance_m: { H01: 10500 } }), {
    distance: 10500, passes: 2, completed: 1, shots: 3, onTarget: 2, goals: 1, interceptions: 0, saves: 0,
  });
  assert.equal(playerStats('H12', events, {}).distance, null);
  assert.equal(playerStats('H12', events, {}).shots, 0);
});

test('Heatmaps handle unused players and reject invalid occupancy data', () => {
  const pitch = { length_m: 105, width_m: 68 };
  assert.equal(heatmapSVG({ cols: 2, rows: 1, players: { H01: [0, 0] } }, 'H01', pitch), null);
  assert.equal(heatmapSVG({ cols: 2, rows: 1, players: { H01: [-1, 2] } }, 'H01', pitch), null);
  const svg = heatmapSVG({ cols: 2, rows: 1, players: { H01: [0, 2] } }, 'H01', pitch);
  assert.match(svg, /x="52.5"/);
  assert.match(svg, /role="img"/);
  assert.ok(!svg.includes('NaN'));
});
