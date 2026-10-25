import type { ActionName } from "@scene/decisions";
import { type Route, type Spot, type TeamId, type XY } from "./ghost";

export const ROLES = ["GK", "LB", "LCB", "RCB", "RB", "LCM", "DM", "RCM", "LW", "ST", "RW"] as const;
export type Role = (typeof ROLES)[number];
export const VISIBLE_MS = 4000;

const ROLE_SET = new Set<string>(ROLES);

export function isRole(value: string): value is Role {
  return ROLE_SET.has(value);
}

function requireTeam(value: string, playerId: string): TeamId {
  if (value === "HOME" || value === "AWAY") return value;
  throw new Error(`Unknown team for ${playerId}.`);
}

export type Slot = {
  player_id: string;
  team_id: TeamId;
  role: Role;
  x: number;
  y: number;
  facing: number;
};

export type Formation = {
  label: string;
  attack_dir: 1 | -1;
  slots: Slot[];
};

type InkBase = {
  ink_id: string;
  frame_id: number;
  t_ms: number;
  team_id: TeamId;
  source: "coach" | "ghost_commit";
  visible_ms: number;
};

export type PassInk = InkBase & {
  kind: "pass";
  from_player_id: string;
  to_player_id: string;
  start: XY;
  end: XY;
  path: XY[];
  style: "ground" | "loft";
  curve: "straight" | "curved";
  control: XY | null;
};

export type CarryInk = InkBase & {
  kind: "carry";
  from_player_id: string;
  start: XY;
  end: XY;
  path: XY[];
  direction_rad: number;
};

export type ShotInk = InkBase & {
  kind: "shot";
  from_player_id: string;
  start: XY;
  end: XY;
  path: XY[];
  direction_rad: number;
  angle_rad: number;
  style: "unset" | "driven" | "placed" | "chip";
};

export type HoldInk = InkBase & {
  kind: "hold";
  player_id: string;
  at: XY;
};

export type Ink = PassInk | CarryInk | ShotInk | HoldInk;

export type BoardFile = {
  schema: "coach-board/1";
  source: "clip" | "setup";
  clip_dir: string | null;
  camera: "broadcast" | "top";
  formation: Formation;
  ink: Ink[];
};

export function directionRad(start: XY, end: XY): number {
  const angle = Math.atan2(end[1] - start[1], end[0] - start[0]);
  if (angle <= -Math.PI) return Math.PI;
  return Object.is(angle, -0) ? 0 : angle;
}

/**
 * A curved pass bows the midpoint 4 m to the left of the direction of play.
 * On a quadratic that means the control point is 8 m left, so t = 0.5 lands on the 4 m bow.
 * The path is nine points: start, seven samples, end.
 */
export function curvePass(start: XY, end: XY, curve: "straight" | "curved"): { path: XY[]; control: XY | null } {
  if (curve === "straight") return { path: [start, end], control: null };
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const len = Math.hypot(dx, dy);
  if (len < 1e-6) return { path: [start, end], control: null };
  const control: XY = [(start[0] + end[0]) / 2 + (-dy / len) * 8, (start[1] + end[1]) / 2 + (dx / len) * 8];
  const path: XY[] = [];
  for (let i = 0; i <= 8; i += 1) {
    const t = i / 8;
    const u = 1 - t;
    path.push([
      u * u * start[0] + 2 * u * t * control[0] + t * t * end[0],
      u * u * start[1] + 2 * u * t * control[1] + t * t * end[1],
    ]);
  }
  return { path, control };
}

export function withPassCurve(ink: PassInk, curve: "straight" | "curved"): PassInk {
  const curved = curvePass(ink.start, ink.end, curve);
  return { ...ink, curve, path: curved.path, control: curved.control };
}

type Stamp = {
  inkId: string;
  frameId: number;
  tMs: number;
  teamId: TeamId;
  source: "coach" | "ghost_commit";
};

function stampOf(stamp: Stamp): InkBase {
  return {
    ink_id: stamp.inkId,
    frame_id: stamp.frameId,
    t_ms: stamp.tMs,
    team_id: stamp.teamId,
    source: stamp.source,
    visible_ms: VISIBLE_MS,
  };
}

export function commitGhost(input: {
  action: ActionName;
  route: Route | null;
  owner: { id: string; teamId: TeamId; x: number; y: number };
  frameId: number;
  tMs: number;
  inkId: string;
}): Ink | null {
  const { action, route, owner, frameId, tMs, inkId } = input;
  if (action === "hold") {
    return {
      ...stampOf({ inkId, frameId, tMs, teamId: owner.teamId, source: "ghost_commit" }),
      kind: "hold",
      player_id: owner.id,
      at: [owner.x, owner.y],
    };
  }
  if (!route || route.path.length < 2) return null;
  const start = route.path[0]!;
  const end = route.path[route.path.length - 1]!;
  const base = stampOf({ inkId, frameId, tMs, teamId: route.teamId, source: "ghost_commit" });
  if (action === "pass" && route.kind === "pass") {
    return {
      ...base,
      kind: "pass",
      from_player_id: route.fromId,
      to_player_id: route.targetId,
      start,
      end,
      path: route.path.map((point) => [point[0], point[1]]),
      style: "ground",
      curve: "straight",
      control: null,
    };
  }
  if (action === "dribble" && route.kind === "carry") {
    return {
      ...base,
      kind: "carry",
      from_player_id: route.fromId,
      start,
      end,
      path: route.path.map((point) => [point[0], point[1]]),
      direction_rad: directionRad(start, end),
    };
  }
  if (action === "shoot" && route.kind === "shot") {
    const facing = directionRad(start, end);
    return {
      ...base,
      kind: "shot",
      from_player_id: route.fromId,
      start,
      end,
      path: route.path.map((point) => [point[0], point[1]]),
      direction_rad: facing,
      angle_rad: facing,
      style: "unset",
    };
  }
  return null;
}

export function coachPass(input: {
  inkId: string;
  frameId: number;
  tMs: number;
  from: Spot;
  to: Spot;
}): PassInk {
  const start: XY = [input.from.x, input.from.y];
  const end: XY = [input.to.x, input.to.y];
  const geometry = curvePass(start, end, "straight");
  return {
    ...stampOf({
      inkId: input.inkId,
      frameId: input.frameId,
      tMs: input.tMs,
      teamId: input.from.teamId,
      source: "coach",
    }),
    kind: "pass",
    from_player_id: input.from.id,
    to_player_id: input.to.id,
    start,
    end,
    path: geometry.path,
    style: "ground",
    curve: "straight",
    control: null,
  };
}

export function coachCarry(input: {
  inkId: string;
  frameId: number;
  tMs: number;
  from: Spot;
  end: XY;
}): CarryInk {
  const start: XY = [input.from.x, input.from.y];
  return {
    ...stampOf({
      inkId: input.inkId,
      frameId: input.frameId,
      tMs: input.tMs,
      teamId: input.from.teamId,
      source: "coach",
    }),
    kind: "carry",
    from_player_id: input.from.id,
    start,
    end: input.end,
    path: [start, input.end],
    direction_rad: directionRad(start, input.end),
  };
}

export function coachShot(input: {
  inkId: string;
  frameId: number;
  tMs: number;
  from: Spot;
  end: XY;
}): ShotInk {
  const start: XY = [input.from.x, input.from.y];
  const facing = directionRad(start, input.end);
  return {
    ...stampOf({
      inkId: input.inkId,
      frameId: input.frameId,
      tMs: input.tMs,
      teamId: input.from.teamId,
      source: "coach",
    }),
    kind: "shot",
    from_player_id: input.from.id,
    start,
    end: input.end,
    path: [start, input.end],
    direction_rad: facing,
    angle_rad: facing,
    style: "unset",
  };
}

export function formationFromFrame(
  framePlayers: readonly { id: string; x: number; y: number; facing: number }[],
  roster: readonly { player_id: string; team_id: string; position: string }[],
  attackDir: number,
): { attack_dir: 1 | -1; slots: Slot[] } {
  if (roster.length !== 22) throw new Error("Roster must list 22 players.");
  const byId = new Map(framePlayers.map((player) => [player.id, player]));
  const slots = roster.map((player) => {
    const at = byId.get(player.player_id);
    if (!at) throw new Error(`Frame is missing ${player.player_id}.`);
    const teamId = requireTeam(player.team_id, player.player_id);
    if (!isRole(player.position)) throw new Error(`Unknown role ${player.position}.`);
    return {
      player_id: player.player_id,
      team_id: teamId,
      role: player.position,
      x: at.x,
      y: at.y,
      facing: at.facing,
    };
  });
  return { attack_dir: attackDir < 0 ? -1 : 1, slots };
}

export function boardDocument(input: {
  clipDir: string | null;
  camera: "broadcast" | "top";
  formation: Formation;
  ink: Ink[];
}): BoardFile {
  return {
    schema: "coach-board/1",
    source: input.clipDir ? "clip" : "setup",
    clip_dir: input.clipDir,
    camera: input.camera,
    formation: input.formation,
    ink: input.ink,
  };
}
