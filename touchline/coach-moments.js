export function canAnalyze(frame) {
  return !!(frame?.in_play && frame.ball_owner_id && frame.players?.some(p => p[0] === frame.ball_owner_id));
}
export function nextMoment(frames, from, direction) {
  for (let i = from + direction; i >= 0 && i < frames.length; i += direction) {
    if (canAnalyze(frames[i])) return i;
  }
  return -1;
}
export function unavailableReason(frame) {
  if (!frame) return 'No tracking snapshot loaded.';
  if (!frame.in_play) return 'Play is stopped. Jump to a moment when a player controls the ball.';
  if (frame.phase === 'pass' || frame.phase === 'shot') return 'The ball is in flight. Pass-choice analysis requires a player in control; jump to the next controlled moment.';
  return 'Ball control is not recorded in this frame. Jump to another controlled moment; no owner is inferred.';
}
