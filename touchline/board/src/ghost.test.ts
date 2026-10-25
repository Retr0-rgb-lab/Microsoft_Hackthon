import { describe, expect, it } from "vitest";
import { decisionAt, type Decision, type DecisionSet } from "@scene/decisions";
import {
  carryFallback,
  fallbackRoute,
  GHOST_MAX_AGE_MS,
  isOffside,
  nearestOnsideTeammate,
  routeForDecision,
  type Spot,
} from "./ghost";

function spot(id: string, teamId: Spot["teamId"], x: number, y = 0): Spot {
  return { id, teamId, x, y };
}

function decision(patch: Partial<Decision> = {}): Decision {
  return {
    event_id: "e1",
    t_ms: 1000,
    frame_id: 25,
    team_id: "HOME",
    player_id: "H10",
    probabilities: { pass: 0.7, shoot: 0.1, dribble: 0.1, hold: 0.1 },
    primary_pass: { target_id: "H09", path: [[1, 2], [8, 4]], score: 0.4 },
    secondary_pass: { target_id: "H11", path: [[1, 2], [30, 20]], score: 0.99 },
    carry: { target_id: "H10", path: [[1, 2], [4, 2], [7, 3]], score: 0.2 },
    completion: {},
    ...patch,
  };
}

const owner = spot("H10", "HOME", 0, 0);

describe("routeForDecision", () => {
  it("uses primary_pass for a pass and ignores secondary_pass", () => {
    const routed = routeForDecision({
      decision: decision(),
      owner,
      spots: [owner, spot("H09", "HOME", 8, 4), spot("H11", "HOME", 30, 20)],
      ball: [0, 0],
      attackDir: 1,
    });
    expect(routed.action).toBe("pass");
    expect(routed.route?.kind).toBe("pass");
    expect(routed.route?.targetId).toBe("H09");
    expect(routed.route?.path).toEqual([
      [1, 2],
      [8, 4],
    ]);
  });

  it("uses the carry path for a dribble", () => {
    const routed = routeForDecision({
      decision: decision({
        probabilities: { pass: 0.1, shoot: 0.1, dribble: 0.7, hold: 0.1 },
      }),
      owner,
      spots: [owner],
      ball: [0, 0],
      attackDir: 1,
    });
    expect(routed.action).toBe("dribble");
    expect(routed.route?.kind).toBe("carry");
    expect(routed.route?.path).toEqual([
      [1, 2],
      [4, 2],
      [7, 3],
    ]);
  });

  it("draws a shot from the ball to the goal that team is attacking", () => {
    const routed = routeForDecision({
      decision: decision({
        probabilities: { pass: 0.1, shoot: 0.7, dribble: 0.1, hold: 0.1 },
      }),
      owner: spot("H10", "HOME", 0, 0),
      spots: [owner],
      ball: [10, 4],
      attackDir: 1,
    });
    expect(routed.route).toMatchObject({
      kind: "shot",
      path: [
        [10, 4],
        [52.5, 0],
      ],
    });

    const away = routeForDecision({
      decision: decision({
        team_id: "AWAY",
        player_id: "A10",
        probabilities: { pass: 0.1, shoot: 0.7, dribble: 0.1, hold: 0.1 },
      }),
      owner: spot("A10", "AWAY", 0, 0),
      spots: [spot("A10", "AWAY", 0, 0)],
      ball: [-3, 1],
      attackDir: 1,
    });
    expect(away.route?.path[1]).toEqual([-52.5, 0]);

    const switched = routeForDecision({
      decision: decision({
        probabilities: { pass: 0.1, shoot: 0.7, dribble: 0.1, hold: 0.1 },
      }),
      owner: spot("H10", "HOME", 0, 0),
      spots: [owner],
      ball: [2, 0],
      attackDir: -1,
    });
    expect(switched.route?.path[1]).toEqual([-52.5, 0]);
  });

  it("draws no route for hold", () => {
    const routed = routeForDecision({
      decision: decision({
        probabilities: { pass: 0.1, shoot: 0.1, dribble: 0.1, hold: 0.7 },
      }),
      owner,
      spots: [owner, spot("H09", "HOME", 5, 0)],
      ball: [0, 0],
      attackDir: 1,
    });
    expect(routed.action).toBe("hold");
    expect(routed.route).toBeNull();
  });

  it("uses a 6 m carry when a dribble has no path", () => {
    const routed = routeForDecision({
      decision: decision({
        probabilities: { pass: 0.1, shoot: 0.1, dribble: 0.7, hold: 0.1 },
        carry: null,
      }),
      owner: spot("H10", "HOME", 10, 3),
      spots: [spot("H10", "HOME", 10, 3)],
      ball: [10, 3],
      attackDir: 1,
    });
    expect(routed.route?.path).toEqual([
      [10, 3],
      [16, 3],
    ]);
  });
});

describe("offside filter", () => {
  const opponents = [spot("A01", "AWAY", 30), spot("A02", "AWAY", 20), spot("A03", "AWAY", 5)];

  it("requires the opponent half, ahead of the ball, and ahead of the second-last opponent", () => {
    const sign = 1;
    expect(isOffside(25, 10, [30, 20, 5], sign)).toBe(true);
    expect(isOffside(15, 10, [30, 20, 5], sign)).toBe(false);
    expect(isOffside(-5, 10, [30, 20, 5], sign)).toBe(false);
    expect(isOffside(12, 15, [30, 8, 0], sign)).toBe(false);
  });

  it("keeps the nearest onside teammate and drops a closer offside one", () => {
    const passer = spot("H10", "HOME", 19, 0);
    const mates = [passer, spot("H11", "HOME", 22, 0), spot("H08", "HOME", 12, 0), ...opponents];
    expect(nearestOnsideTeammate(passer, mates, 10, 1)?.id).toBe("H08");
  });

  it("breaks an equal distance by player id and ignores a further advanced teammate", () => {
    const mates = [owner, spot("H09", "HOME", 4, 0), spot("H06", "HOME", 0, 4), spot("H07", "HOME", 30, 0), spot("A01", "AWAY", 40), spot("A02", "AWAY", 35)];
    expect(nearestOnsideTeammate(owner, mates, 0, 1)?.id).toBe("H06");
  });

  it("measures the away line toward the goal that team is attacking", () => {
    const away = spot("A10", "AWAY", -10, 0);
    const mates = [away, spot("A09", "AWAY", -22, 0), spot("A08", "AWAY", -12, 0), spot("H01", "HOME", -30), spot("H02", "HOME", -18)];
    expect(isOffside(-22, -8, [-30, -18], -1)).toBe(true);
    expect(nearestOnsideTeammate(away, mates, -8, 1)?.id).toBe("A08");
  });

  it("falls back to a 6 m carry when every teammate is offside", () => {
    const mates = [owner, spot("H09", "HOME", 40, 0), spot("A01", "AWAY", 10), spot("A02", "AWAY", 5)];
    const routed = fallbackRoute({ owner, spots: mates, ball: [0, 0], attackDir: 1 });
    expect(routed.action).toBe("dribble");
    expect(routed.route.path).toEqual([
      [0, 0],
      [6, 0],
    ]);
  });
});

describe("carryFallback", () => {
  it("runs 6 m along the attack and stays inside the pitch", () => {
    expect(carryFallback([0, 1], "AWAY", 1).end).toEqual([-6, 1]);
    expect(carryFallback([50, 40], "HOME", 1).end).toEqual([52.5, 34]);
  });
});

describe("checked-in decision age", () => {
  const set: DecisionSet = {
    schema_version: 1,
    match_id: "TEST",
    frame_hz: 25,
    origin: "centre_spot",
    decision_count: 1,
    decisions: [decision({ t_ms: 1000 })],
  };

  it("keeps the latest decision when the window is infinite", () => {
    expect(GHOST_MAX_AGE_MS).toBe(Number.POSITIVE_INFINITY);
    expect(decisionAt(set, 1000 + 8001, GHOST_MAX_AGE_MS)?.event_id).toBe("e1");
  });
});
