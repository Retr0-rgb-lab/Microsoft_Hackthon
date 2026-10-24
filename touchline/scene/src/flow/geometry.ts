import type { PitchPoint } from "./types";

export function toPitchSvg(x: number, y: number): [number, number] {
  return [round3(x + 52.5), round3(34 - y)];
}

/** Distance-weighted point along a metre path. `t` is 0 at the start and 1 at the end. */
export function pointAlong(path: readonly PitchPoint[], t: number): PitchPoint {
  if (path.length === 0) throw new Error("empty path");
  const first = path[0];
  if (!first) throw new Error("empty path");
  if (path.length === 1 || t <= 0) return [first[0], first[1]];
  const last = path[path.length - 1];
  if (!last) return [first[0], first[1]];
  if (t >= 1) return [last[0], last[1]];
  const lengths: number[] = [];
  let total = 0;
  for (let i = 0; i < path.length - 1; i += 1) {
    const a = path[i];
    const b = path[i + 1];
    if (!a || !b) continue;
    const step = Math.hypot(b[0] - a[0], b[1] - a[1]);
    lengths.push(step);
    total += step;
  }
  if (total <= 1e-6) return [first[0], first[1]];
  let remain = t * total;
  for (let i = 0; i < lengths.length; i += 1) {
    const step = lengths[i] ?? 0;
    const a = path[i];
    const b = path[i + 1];
    if (!a || !b) continue;
    if (remain <= step || i === lengths.length - 1) {
      const local = step <= 1e-6 ? 0 : remain / step;
      return [a[0] + (b[0] - a[0]) * local, a[1] + (b[1] - a[1]) * local];
    }
    remain -= step;
  }
  return [last[0], last[1]];
}

function round3(value: number): number {
  return Math.round(value * 1000) / 1000;
}
