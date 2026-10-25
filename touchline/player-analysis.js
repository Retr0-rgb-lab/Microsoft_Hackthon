export function playerStats(playerId, events, summary) {
  const stats = { distance: summary.distance_m?.[playerId] ?? null, passes: 0,
    completed: 0, shots: 0, onTarget: 0, goals: 0, interceptions: 0, saves: 0 };
  for (const event of events) {
    if (event.player_id !== playerId) continue;
    if (event.type === 'pass') { stats.passes++; stats.completed += Number(event.outcome === 'complete'); }
    if (event.type === 'shot') {
      stats.shots++; stats.onTarget += Number(['goal', 'saved'].includes(event.outcome));
      stats.goals += Number(event.outcome === 'goal');
    }
    if (event.type === 'interception') stats.interceptions++;
    if (event.type === 'save') stats.saves++;
  }
  return stats;
}

export function heatmapSVG(map, playerId, pitch) {
  const bins = map.players[playerId];
  if (!bins || !bins.some(value => value > 0)) return null;
  const { cols, rows } = map;
  if (bins.length !== cols * rows || !bins.every(value => Number.isFinite(value) && value >= 0)) return null;
  const max = Math.max(...bins), width = pitch.length_m, height = pitch.width_m;
  const cells = bins.map((count, i) => {
    if (!count) return '';
    const intensity = Math.sqrt(count / max);
    return `<rect x="${i % cols * width / cols}" y="${Math.floor(i / cols) * height / rows}" width="${width / cols}" height="${height / rows}" fill="hsl(${55 * (1 - intensity)} 95% 55%)" opacity="${0.2 + intensity * 0.7}"/>`;
  }).join('');
  return `<svg viewBox="-2 -2 ${width + 4} ${height + 4}" role="img" aria-label="Full-match player position heatmap"><rect x="-2" y="-2" width="${width + 4}" height="${height + 4}" rx="2" fill="#173f37"/>${cells}<g fill="none" stroke="#ffffff9c" stroke-width=".3"><rect width="${width}" height="${height}"/><path d="M${width / 2} 0v${height}"/><circle cx="${width / 2}" cy="${height / 2}" r="9.15"/><rect y="${height / 2 - 20.16}" width="16.5" height="40.32"/><rect x="${width - 16.5}" y="${height / 2 - 20.16}" width="16.5" height="40.32"/><rect y="${height / 2 - 9.16}" width="5.5" height="18.32"/><rect x="${width - 5.5}" y="${height / 2 - 9.16}" width="5.5" height="18.32"/></g></svg>`;
}
