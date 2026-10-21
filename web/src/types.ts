export const ACTIONS = ["pass", "shoot", "dribble", "hold"] as const;

export type Action = (typeof ACTIONS)[number];

export type Point = {
  x: number;
  y: number;
};

export type TeamId = "home" | "away";

export type PlayerMark = {
  id: string;
  team: TeamId;
  possessor: boolean;
  /** Normalized video frame. Origin is the top-left. Both axes are 0–1. */
  frame: Point;
  /** Pitch meters. x is 0–105 toward the goal home attacks. y is 0–68. */
  pitch: Point;
};

export type ArrowMark = {
  kind: Action;
  primary: boolean;
  from_frame: Point;
  to_frame: Point;
  from_pitch: Point;
  to_pitch: Point;
};

export type Moment = {
  id: string;
  t_seconds: number;
  recommended: Action;
  distribution: Record<Action, number>;
  primary_explain: string;
  secondary_explain: string;
  system2_rationale: string;
  players: PlayerMark[];
  arrows: ArrowMark[];
};

export type Fixture = {
  schema_version: 1;
  title: string;
  scheme: string;
  duration_seconds: number;
  initial_moment_id: string;
  disclaimer: string;
  moments: Moment[];
};
