export type DecisionPath = {
  target_id: string;
  path: [number, number][];
  score: number;
};

export type Probabilities = {
  pass: number;
  shoot: number;
  dribble: number;
  hold: number;
};

export type Decision = {
  event_id: string;
  t_ms: number;
  frame_id: number;
  team_id: string;
  player_id: string;
  probabilities: Probabilities;
  primary_pass: DecisionPath | null;
  secondary_pass: DecisionPath | null;
  carry: DecisionPath | null;
  completion: Record<string, unknown>;
};

export type DecisionSet = {
  schema_version: number;
  match_id: string;
  frame_hz: number;
  origin: string;
  decision_count: number;
  decisions: Decision[];
};

export const ACTION_ORDER = ["pass", "shoot", "dribble", "hold"] as const;
export type ActionName = (typeof ACTION_ORDER)[number];

export const DEFAULT_MAX_AGE_MS = 8000;

export async function loadDecisions(url = "/decisions.json"): Promise<DecisionSet> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`decisions.json HTTP ${res.status}`);
  const set = (await res.json()) as DecisionSet;
  if (!Array.isArray(set.decisions) || set.decisions.length === 0) {
    throw new Error("Decision set is empty.");
  }
  return set;
}

/**
 * The decision in force at `tMs`: the last one at or before this instant.
 *
 * A decision is only shown while it is still recent. Past `maxAgeMs` the
 * options on screen describe a moment that has moved on, so the overlay
 * clears instead of drawing a stale answer.
 */
export function decisionAt(
  set: DecisionSet,
  tMs: number,
  maxAgeMs: number = DEFAULT_MAX_AGE_MS,
): Decision | null {
  const list = set.decisions;
  let lo = 0;
  let hi = list.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (list[mid].t_ms <= tMs) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  if (found < 0) return null;
  const decision = list[found];
  return tMs - decision.t_ms > maxAgeMs ? null : decision;
}

export function topAction(probabilities: Probabilities): ActionName {
  let best: ActionName = "pass";
  for (const action of ACTION_ORDER) {
    if (probabilities[action] > probabilities[best]) best = action;
  }
  return best;
}
