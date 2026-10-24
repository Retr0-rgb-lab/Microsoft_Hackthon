import { describe, expect, it } from "vitest";
import { pointAlong, toPitchSvg } from "./geometry";

describe("pitch diagram geometry", () => {
  it("maps centre-origin metres onto a 105 by 68 svg", () => {
    expect(toPitchSvg(0, 0)).toEqual([52.5, 34]);
    expect(toPitchSvg(-52.5, 34)).toEqual([0, 0]);
    expect(toPitchSvg(52.5, -34)).toEqual([105, 68]);
  });

  it("walks a path by length", () => {
    expect(pointAlong([[0, 0], [10, 0]], 0)).toEqual([0, 0]);
    expect(pointAlong([[0, 0], [10, 0]], 0.5)).toEqual([5, 0]);
    expect(pointAlong([[0, 0], [0, 8], [6, 8]], 1)).toEqual([6, 8]);
    const mid = pointAlong([[0, 0], [0, 10], [10, 10]], 0.5);
    expect(mid[0]).toBeCloseTo(0);
    expect(mid[1]).toBeCloseTo(10);
  });
});
