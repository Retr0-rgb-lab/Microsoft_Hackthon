/** Softmax decision stub. Geometry is centre-origin metres, matching SynthData FORMAT. */

export const ACTION_CLASSES = ["pass", "shoot", "dribble", "hold"] as const;

export type ActionClass = (typeof ACTION_CLASSES)[number];

export type AudienceMode = "fan" | "coach";

export type Language = "en" | "zh";

export type PitchPoint = [number, number];

/** Pass and dribble carry `score`. Shoot is a segment only. Hold has no geometry. */
export type ActionGeometry = {
  target_id: string | null;
  path: PitchPoint[];
  score?: number;
};

export type RankedAction = {
  action: ActionClass;
  prob: number;
  role: "primary" | "secondary";
  geometry: ActionGeometry | null;
};

export type DecideStatus = "ready" | "partial" | "unknown" | "model_unavailable" | "error";

/**
 * Frontend shape for `decide_from_tracking`.
 * `probs` is the four-way softmax. One geometry per action class.
 * `score` is a stub field for pass/dribble and is not a completion percentage.
 */
export type DecideFromTracking = {
  status: DecideStatus;
  event_id: string;
  snapshot_id: string;
  candidate_set_id: string;
  t_ms: number;
  actor_id: string;
  team_id: "HOME" | "AWAY";
  actual_action: ActionClass;
  probs: Record<ActionClass, number>;
  primary: RankedAction;
  secondaries: RankedAction[];
  limitations: string[];
};

export type AgentRole = "coordinator" | "attack" | "defense" | "review";

export type AgentTraceStep = {
  agent: AgentRole;
  tool: string;
  ms: number;
  ok: boolean;
};

/** Optional agent layer. Drop the text when `candidate_set_id` does not match. */
export type AgentExplanation = {
  candidate_set_id: string;
  mode: AudienceMode;
  language: Language;
  question_id: string;
  text: string;
  agent_trace: AgentTraceStep[];
  limitations: string[];
};

export type QuestionId = "why_actual" | "why_not_pass" | "why_forward";

export function ranked(decide: DecideFromTracking): RankedAction[] {
  return [decide.primary, ...decide.secondaries];
}

export function actionByClass(decide: DecideFromTracking, action: ActionClass): RankedAction | null {
  return ranked(decide).find((item) => item.action === action) ?? null;
}
