import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  PRIMARY_ARROW,
  SIDEBAR_HIGHLIGHT,
  argmaxAction,
  arrowsForDisplay,
  formatClock,
  formatPercent,
  isSecondaryPassCopy,
  momentAt,
  parseFixture,
} from "./display";
import { ACTIONS } from "./types";

const fixturePath = join(dirname(fileURLToPath(import.meta.url)), "../public/scheme-a.json");
const raw = readFileSync(fixturePath, "utf8");
const fixture = parseFixture(JSON.parse(raw) as unknown);

describe("scheme A fixture", () => {
  it("parses the shipped sidebar contract", () => {
    expect(fixture.title).toBe("Inside the Game");
    expect(fixture.scheme).toBe("Scheme A");
    expect(fixture.initial_moment_id).toBe("m6322");
    expect(fixture.disclaimer.toLowerCase()).toContain("decision aid");
    expect(fixture.disclaimer.toLowerCase()).toContain("full distribution");
    expect(fixture.disclaimer.toLowerCase()).toContain("not a single optimal action");
    expect(fixture.moments.map((moment) => moment.id)).toEqual(["m1234", "m2507", "m3741", "m5018", "m6322"]);
  });

  it("shows a percent for every softmax bar and the shares sum to 100", () => {
    for (const moment of fixture.moments) {
      const labels = ACTIONS.map((action) => formatPercent(moment.distribution[action]));
      expect(labels.every((label) => /^\d+%$/.test(label))).toBe(true);
      const total = ACTIONS.reduce((sum, action) => sum + Math.round(moment.distribution[action] * 100), 0);
      expect(total).toBe(100);
      expect(moment.recommended).toBe(argmaxAction(moment.distribution));
    }
    const hero = fixture.moments.find((moment) => moment.id === "m6322");
    expect(hero && formatPercent(hero.distribution.pass)).toBe("43%");
    expect(hero && formatPercent(hero.distribution.shoot)).toBe("16%");
    expect(hero && formatPercent(hero.distribution.dribble)).toBe("27%");
    expect(hero && formatPercent(hero.distribution.hold)).toBe("14%");
  });

  it("keeps secondary explain as pass copy", () => {
    for (const moment of fixture.moments) {
      expect(isSecondaryPassCopy(moment.secondary_explain)).toBe(true);
    }
    expect(isSecondaryPassCopy("Hold maintains shape if pressure is high")).toBe(false);
    expect(isSecondaryPassCopy("Stay here and reset the shape")).toBe(false);
  });

  it("draws the accepted arrow set and drops extras", () => {
    const byId = Object.fromEntries(fixture.moments.map((moment) => [moment.id, moment]));
    expect(byId.m6322.arrows.length).toBeGreaterThan(3);
    const hero = arrowsForDisplay(byId.m6322.recommended, byId.m6322.arrows);
    expect(hero.map((arrow) => `${arrow.primary ? "primary" : "secondary"}:${arrow.kind}`)).toEqual([
      "primary:pass",
      "secondary:pass",
      "secondary:pass",
    ]);

    expect(byId.m3741.arrows.filter((arrow) => arrow.kind === "dribble").length).toBeGreaterThan(1);
    const dribble = arrowsForDisplay(byId.m3741.recommended, byId.m3741.arrows);
    expect(dribble.map((arrow) => `${arrow.primary ? "primary" : "secondary"}:${arrow.kind}`)).toEqual([
      "primary:dribble",
      "secondary:pass",
    ]);

    expect(byId.m5018.arrows.some((arrow) => arrow.kind === "shoot")).toBe(true);
    expect(arrowsForDisplay(byId.m5018.recommended, byId.m5018.arrows)).toEqual([]);
    expect(byId.m1234.arrows.some((arrow) => arrow.kind === "pass")).toBe(true);
    expect(arrowsForDisplay(byId.m1234.recommended, byId.m1234.arrows)).toEqual([]);
  });

  it("keeps the primary arrow yellow distinct from the sidebar green", () => {
    expect(PRIMARY_ARROW).toBe("#FFE500");
    expect(SIDEBAR_HIGHLIGHT).toBe("#00FF85");
  });

  it("steps the timeline by possession moment", () => {
    expect(momentAt(fixture.moments, 0).id).toBe("m1234");
    expect(momentAt(fixture.moments, 1506).id).toBe("m1234");
    expect(momentAt(fixture.moments, 1507).id).toBe("m2507");
    expect(momentAt(fixture.moments, 2261).id).toBe("m3741");
    expect(momentAt(fixture.moments, 3018).id).toBe("m5018");
    expect(momentAt(fixture.moments, 3802).id).toBe("m6322");
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(754)).toBe("12:34");
    expect(formatClock(3802)).toBe("63:22");
    expect(formatClock(5400)).toBe("90:00");
  });

  it("rejects hold copy in the secondary slot and a short distribution", () => {
    const held = structuredClone(JSON.parse(raw) as unknown) as {
      moments: Array<{ secondary_explain: string; distribution: Record<string, number> }>;
    };
    held.moments[0].secondary_explain = "Hold maintains shape if pressure is high";
    expect(() => parseFixture(held)).toThrow(/secondary pass/i);

    const missing = structuredClone(JSON.parse(raw) as unknown) as {
      moments: Array<{ distribution: Record<string, number> }>;
    };
    delete missing.moments[0].distribution.hold;
    expect(() => parseFixture(missing)).toThrow(/distribution/i);
  });
});
