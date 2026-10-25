import { describe, expect, it } from "vitest";
import type { Route } from "./ghost";
import { commitGhost, curvePass, withPassCurve, type PassInk } from "./ink";

const owner = { id: "H10", teamId: "HOME" as const, x: 4, y: -2 };

describe("commitGhost", () => {
  it("writes a hold marker at the owner's feet and no path", () => {
    const ink = commitGhost({
      action: "hold",
      route: {
        kind: "pass",
        teamId: "HOME",
        fromId: "H10",
        targetId: "H09",
        path: [
          [1, 1],
          [2, 2],
        ],
        end: [2, 2],
        score: 1,
      },
      owner,
      frameId: 12,
      tMs: 480,
      inkId: "ink-7",
    });
    expect(ink).toEqual({
      ink_id: "ink-7",
      kind: "hold",
      frame_id: 12,
      t_ms: 480,
      team_id: "HOME",
      player_id: "H10",
      at: [4, -2],
      source: "ghost_commit",
      visible_ms: 4000,
    });
    expect(ink).not.toHaveProperty("path");
  });

  it("accepts a pass as ground and straight", () => {
    const route: Route = {
      kind: "pass",
      teamId: "HOME",
      fromId: "H10",
      targetId: "H09",
      path: [
        [1, 2],
        [8, 4],
      ],
      end: [8, 4],
      score: 0.4,
    };
    const ink = commitGhost({
      action: "pass",
      route,
      owner,
      frameId: 3,
      tMs: 120,
      inkId: "ink-1",
    });
    expect(ink).toMatchObject({
      kind: "pass",
      style: "ground",
      curve: "straight",
      control: null,
      from_player_id: "H10",
      to_player_id: "H09",
      path: route.path,
    });
  });

  it("accepts a shot with style unset", () => {
    const ink = commitGhost({
      action: "shoot",
      route: {
        kind: "shot",
        teamId: "HOME",
        fromId: "H10",
        targetId: "H10",
        path: [
          [10, 4],
          [52.5, 0],
        ],
        end: [52.5, 0],
        score: null,
      },
      owner,
      frameId: 4,
      tMs: 160,
      inkId: "ink-2",
    });
    expect(ink).toMatchObject({
      kind: "shot",
      style: "unset",
      path: [
        [10, 4],
        [52.5, 0],
      ],
    });
  });
});

describe("curvePass", () => {
  it("bows the midpoint 4 m to the left of the direction of play", () => {
    const straight = curvePass([0, 0], [10, 0], "straight");
    expect(straight.control).toBeNull();
    expect(straight.path).toEqual([
      [0, 0],
      [10, 0],
    ]);

    const along = curvePass([0, 0], [10, 0], "curved");
    expect(along.control).toEqual([5, 8]);
    expect(along.path).toHaveLength(9);
    expect(along.path[0]).toEqual([0, 0]);
    expect(along.path[8]).toEqual([10, 0]);
    expect(along.path[4]?.[0]).toBeCloseTo(5);
    expect(along.path[4]?.[1]).toBeCloseTo(4);

    const up = curvePass([0, 0], [0, 10], "curved");
    expect(up.control).toEqual([-8, 5]);
  });

  it("rebuilds a pass from its endpoints when the curve changes", () => {
    const ink: PassInk = {
      ink_id: "ink-3",
      kind: "pass",
      frame_id: 1,
      t_ms: 0,
      team_id: "HOME",
      from_player_id: "H10",
      to_player_id: "H09",
      start: [0, 0],
      end: [10, 0],
      path: [
        [0, 0],
        [10, 0],
      ],
      style: "ground",
      curve: "straight",
      control: null,
      source: "coach",
      visible_ms: 4000,
    };
    const curved = withPassCurve(ink, "curved");
    expect(curved.curve).toBe("curved");
    expect(curved.control).toEqual([5, 8]);
    expect(curved.style).toBe("ground");
    expect(withPassCurve(curved, "straight").path).toEqual([
      [0, 0],
      [10, 0],
    ]);
  });
});
