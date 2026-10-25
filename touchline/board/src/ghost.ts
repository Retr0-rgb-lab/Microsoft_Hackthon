import { PITCH } from "@scene/coords";
import { topAction, type ActionName, type Decision } from "@scene/decisions";

export type XY = [number, number];
export type TeamId = "HOME" | "AWAY";

export type Spot = {
  id: string;
  teamId: TeamId;
  x: number;
  y: number;
};

export type Route = {
  kind: "pass" | "carry" | "shot";
  teamId: TeamId;
  fromId: string;
  targetId: string;
  path: XY[];
  end: XY;
  score: number | null;
};

export const FALLBACK_CARRY_M = 6;

/** Latest checked-in decision stays in force; the scene's 8 second window does not apply. */
export const GHOST_MAX_AGE_MS = Number.POSITIVE_INFINITY;

export function attackSign(teamId: TeamId, attackDir: number): number {
  const dir = attackDir < 0 ? -1 : 1;
  return teamId === "HOME" ? dir : -dir;
}

export function goalCenter(teamId: TeamId, attackDir: number): XY {
  return [PITCH.halfLength * attackSign(teamId, attackDir), 0];
}

export function clampToPitch(x: number, y: number): XY {
  return [
    Math.min(PITCH.halfLength, Math.max(-PITCH.halfLength, x)),
    Math.min(PITCH.halfWidth, Math.max(-PITCH.halfWidth, y)),
  ];
}

/**
 * Simplified Law 11. A receiver is offside only when all three are true:
 * in the opponent half, ahead of the ball, and ahead of the second-last opponent.
 * Attack coordinates increase toward the goal that `sign` is attacking.
 */
export function isOffside(
  receiverX: number,
  ballX: number,
  opponentXs: readonly number[],
  sign: number,
): boolean {
  const rx = receiverX * sign;
  const defenders = opponentXs.map((x) => x * sign).sort((a, b) => b - a);
  const secondLast = defenders.length > 1 ? defenders[1]! : -PITCH.halfLength;
  const line = Math.max(secondLast, ballX * sign, 0);
  return rx > line;
}

export function nearestOnsideTeammate(
  owner: Spot,
  spots: readonly Spot[],
  ballX: number,
  attackDir: number,
): Spot | null {
  const sign = attackSign(owner.teamId, attackDir);
  const opponentXs = spots.filter((spot) => spot.teamId !== owner.teamId).map((spot) => spot.x);
  const legal = spots.filter(
    (spot) =>
      spot.teamId === owner.teamId &&
      spot.id !== owner.id &&
      !isOffside(spot.x, ballX, opponentXs, sign),
  );
  legal.sort((a, b) => {
    const da = (a.x - owner.x) ** 2 + (a.y - owner.y) ** 2;
    const db = (b.x - owner.x) ** 2 + (b.y - owner.y) ** 2;
    if (da < db) return -1;
    if (da > db) return 1;
    return a.id < b.id ? -1 : 1;
  });
  return legal[0] ?? null;
}

export function carryFallback(origin: XY, teamId: TeamId, attackDir: number): { path: XY[]; end: XY } {
  const sign = attackSign(teamId, attackDir);
  const end = clampToPitch(origin[0] + FALLBACK_CARRY_M * sign, origin[1]);
  return { path: [[origin[0], origin[1]], end], end };
}

function clonePath(path: readonly [number, number][] | null | undefined): XY[] | null {
  if (!path || path.length < 2) return null;
  return path.map((point) => [Number(point[0]), Number(point[1])]);
}

function teamOf(value: string, fallback: TeamId): TeamId {
  return value === "HOME" || value === "AWAY" ? value : fallback;
}

function lineRoute(
  kind: Route["kind"],
  teamId: TeamId,
  fromId: string,
  targetId: string,
  start: XY,
  end: XY,
  score: number | null,
): Route {
  return { kind, teamId, fromId, targetId, path: [start, end], end, score };
}

function passTo(owner: Spot, mate: Spot): Route {
  const start: XY = [owner.x, owner.y];
  const end: XY = [mate.x, mate.y];
  return lineRoute("pass", owner.teamId, owner.id, mate.id, start, end, null);
}

export function routeForDecision(input: {
  decision: Decision;
  owner: Spot;
  spots: readonly Spot[];
  ball: XY;
  attackDir: number;
}): { action: ActionName; route: Route | null } {
  const { decision, owner, spots, ball, attackDir } = input;
  const action = topAction(decision.probabilities);
  const teamId = teamOf(decision.team_id, owner.teamId);

  if (action === "hold") return { action, route: null };

  if (action === "pass") {
    const primary = decision.primary_pass;
    const path = primary ? clonePath(primary.path) : null;
    if (primary && path && primary.target_id) {
      const end = path[path.length - 1]!;
      return {
        action,
        route: {
          kind: "pass",
          teamId,
          fromId: decision.player_id,
          targetId: primary.target_id,
          path,
          end,
          score: primary.score,
        },
      };
    }
    const mate = nearestOnsideTeammate(owner, spots, ball[0], attackDir);
    return { action, route: mate ? passTo(owner, mate) : null };
  }

  if (action === "dribble") {
    const carry = decision.carry;
    const path = carry ? clonePath(carry.path) : null;
    if (carry && path) {
      const end = path[path.length - 1]!;
      return {
        action,
        route: {
          kind: "carry",
          teamId,
          fromId: decision.player_id,
          targetId: carry.target_id || decision.player_id,
          path,
          end,
          score: carry.score,
        },
      };
    }
    const fallback = carryFallback([owner.x, owner.y], owner.teamId, attackDir);
    return {
      action,
      route: {
        kind: "carry",
        teamId: owner.teamId,
        fromId: owner.id,
        targetId: owner.id,
        path: fallback.path,
        end: fallback.end,
        score: null,
      },
    };
  }

  const end = goalCenter(owner.teamId, attackDir);
  const start: XY = [ball[0], ball[1]];
  return { action, route: lineRoute("shot", owner.teamId, owner.id, owner.id, start, end, null) };
}

/** Deterministic geometry when this pause has a ball owner and no checked-in decision. */
export function fallbackRoute(input: {
  owner: Spot;
  spots: readonly Spot[];
  ball: XY;
  attackDir: number;
}): { action: "pass" | "dribble"; route: Route } {
  const mate = nearestOnsideTeammate(input.owner, input.spots, input.ball[0], input.attackDir);
  if (mate) return { action: "pass", route: passTo(input.owner, mate) };
  const carry = carryFallback([input.owner.x, input.owner.y], input.owner.teamId, input.attackDir);
  return {
    action: "dribble",
    route: {
      kind: "carry",
      teamId: input.owner.teamId,
      fromId: input.owner.id,
      targetId: input.owner.id,
      path: carry.path,
      end: carry.end,
      score: null,
    },
  };
}
