import { describe, expect, it } from "vitest";
import { decisionAt, topAction, type Decision, type DecisionSet } from "./decisions";

function makeDecision(eventId: string, tMs: number): Decision {
  return {
    event_id: eventId,
    t_ms: tMs,
    frame_id: Math.round((tMs * 25) / 1000),
    team_id: "HOME",
    player_id: "H10",
    probabilities: { pass: 0.4, shoot: 0.1, dribble: 0.3, hold: 0.2 },
    primary_pass: null,
    secondary_pass: null,
    carry: null,
    completion: {},
  };
}

const set: DecisionSet = {
  schema_version: 1,
  match_id: "TEST",
  frame_hz: 25,
  origin: "centre_spot",
  decision_count: 3,
  decisions: [makeDecision("a", 1000), makeDecision("b", 5000), makeDecision("c", 9000)],
};

describe("decisionAt", () => {
  it("returns nothing before the first decision", () => {
    expect(decisionAt(set, 0)).toBeNull();
    expect(decisionAt(set, 999)).toBeNull();
  });

  it("returns the decision in force at that instant", () => {
    expect(decisionAt(set, 1000)?.event_id).toBe("a");
    expect(decisionAt(set, 4999)?.event_id).toBe("a");
  });

  it("moves to the next decision once it is available", () => {
    expect(decisionAt(set, 5000)?.event_id).toBe("b");
    expect(decisionAt(set, 8999)?.event_id).toBe("b");
    expect(decisionAt(set, 9000)?.event_id).toBe("c");
  });

  it("drops a decision that is no longer recent", () => {
    // The last decision is "c" at 9000, so the window is measured from there.
    expect(decisionAt(set, 9000 + 8001)).toBeNull();
    expect(decisionAt(set, 9000 + 8000)).not.toBeNull();
  });

  it("honours a custom window", () => {
    expect(decisionAt(set, 3000, 1000)).toBeNull();
    expect(decisionAt(set, 3000, 2000)?.event_id).toBe("a");
  });
});

describe("topAction", () => {
  it("picks the largest share", () => {
    expect(topAction({ pass: 0.4, shoot: 0.1, dribble: 0.3, hold: 0.2 })).toBe("pass");
    expect(topAction({ pass: 0.1, shoot: 0.6, dribble: 0.2, hold: 0.1 })).toBe("shoot");
    expect(topAction({ pass: 0.1, shoot: 0.2, dribble: 0.5, hold: 0.2 })).toBe("dribble");
    expect(topAction({ pass: 0.1, shoot: 0.2, dribble: 0.3, hold: 0.4 })).toBe("hold");
  });
});
