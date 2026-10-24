import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { Frame } from "../coords";
import { decideFromSample, mockExplanation } from "./mock";
import { bindAgent } from "./machine";
import { frameForTime, forwardPass, parseDecisionPoints, type RosterPlayer } from "./sample";
import { ACTION_CLASSES, ranked } from "./types";

const sampleDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../data/samples/sample_25hz_10min",
);

function load() {
  const meta = JSON.parse(readFileSync(path.join(sampleDir, "metadata.json"), "utf8")) as {
    frame_hz: number;
    players: { player_id: string; team_id: "HOME" | "AWAY"; jersey_number: number; name: string }[];
  };
  const events = readFileSync(path.join(sampleDir, "events.jsonl"), "utf8")
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line) as unknown);
  const frames = readFileSync(path.join(sampleDir, "clip.jsonl"), "utf8")
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line) as Frame);
  const decisions = parseDecisionPoints(events, 30000);
  const roster: RosterPlayer[] = meta.players.map((player) => ({
    player_id: player.player_id,
    team_id: player.team_id,
    jersey_number: player.jersey_number,
  }));
  return { meta, decisions, frames, roster };
}

describe("sample decision stub", () => {
  const { meta, decisions, frames, roster } = load();

  it("keeps the four decision points inside the 30 second clip", () => {
    expect(decisions.map((event) => event.event_id)).toEqual(["e000005", "e000009", "e000015", "e000018"]);
    for (const event of decisions) {
      const frame = frameForTime(frames, event.available_at_ms, meta.frame_hz);
      expect(frame.t_ms).toBe(event.available_at_ms);
      const encoded = JSON.stringify(event);
      expect(encoded).not.toContain("success_prob");
      expect(encoded).not.toContain("value_gain");
      expect(encoded).not.toContain("xt_gain");
    }
  });

  it("returns a four-way softmax with one path per class", () => {
    const primaries: string[] = [];
    for (const event of decisions) {
      const frame = frameForTime(frames, event.available_at_ms, meta.frame_hz);
      const result = decideFromSample({ frame, event, roster });
      const actions = ranked(result);
      expect(result.status).toBe("ready");
      expect(actions.map((item) => item.action).sort()).toEqual([...ACTION_CLASSES].sort());
      expect(result.secondaries).toHaveLength(3);
      expect(result.primary.role).toBe("primary");
      const sum = ACTION_CLASSES.reduce((total, label) => total + result.probs[label], 0);
      expect(sum).toBeCloseTo(1, 6);
      expect(result.primary.prob).toBeGreaterThanOrEqual(Math.max(...result.secondaries.map((item) => item.prob)));
      const pass = actions.find((item) => item.action === "pass");
      const dribble = actions.find((item) => item.action === "dribble");
      const shoot = actions.find((item) => item.action === "shoot");
      const hold = actions.find((item) => item.action === "hold");
      expect(pass?.geometry?.path.length).toBe(2);
      expect(dribble?.geometry?.path.length).toBe(5);
      expect(typeof pass?.geometry?.score).toBe("number");
      expect(typeof dribble?.geometry?.score).toBe("number");
      expect(shoot?.geometry?.path.length).toBe(2);
      expect(shoot?.geometry?.score).toBeUndefined();
      expect(hold?.geometry).toBeNull();
      for (const item of actions) {
        for (const [x, y] of item.geometry?.path ?? []) {
          expect(Math.abs(x)).toBeLessThanOrEqual(52.5 + 0.05);
          expect(Math.abs(y)).toBeLessThanOrEqual(34 + 0.05);
        }
      }
      const blob = JSON.stringify(result);
      expect(blob).not.toContain("success_prob");
      expect(blob).not.toContain("value_gain");
      primaries.push(`${event.event_id}:${result.primary.action}:${result.actual_action}`);
    }
    expect(primaries).toEqual([
      "e000005:dribble:dribble",
      "e000009:dribble:pass",
      "e000015:pass:pass",
      "e000018:pass:pass",
    ]);
  });

  it("points the single pass arrow at the recorded receiver or the forward teammate", () => {
    const first = decisions[0];
    const second = decisions[1];
    if (!first || !second) throw new Error("missing decisions");
    const a = decideFromSample({
      frame: frameForTime(frames, first.available_at_ms, meta.frame_hz),
      event: first,
      roster,
    });
    const b = decideFromSample({
      frame: frameForTime(frames, second.available_at_ms, meta.frame_hz),
      event: second,
      roster,
    });
    expect(a.actual_action).toBe("dribble");
    expect(ranked(a).find((item) => item.action === "pass")?.geometry?.target_id).toBe(forwardPass(first)?.target_player_id);
    expect(b.actual_action).toBe("pass");
    expect(ranked(b).find((item) => item.action === "pass")?.geometry?.target_id).toBe("H08");
  });

  it("binds agent text only when the candidate set matches", () => {
    const event = decisions[0];
    if (!event) throw new Error("missing decision");
    const result = decideFromSample({
      frame: frameForTime(frames, event.available_at_ms, meta.frame_hz),
      event,
      roster,
    });
    const explanation = mockExplanation({
      decide: result,
      questionId: "why_not_pass",
      mode: "fan",
      language: "en",
      userPick: null,
      shirts: { actor: "#10", passTarget: "#9", forward: "#9" },
    });
    expect(explanation.agent_trace.map((step) => step.agent)).toEqual([
      "coordinator",
      "attack",
      "defense",
      "review",
    ]);
    expect(explanation.text).not.toMatch(/%|success_prob|value_gain/);
    expect(bindAgent(result, explanation).dropped).toBe(false);
    expect(bindAgent(result, { ...explanation, candidate_set_id: "other" }).agent).toBeNull();
    const coach = mockExplanation({
      decide: result,
      questionId: "why_actual",
      mode: "coach",
      language: "en",
      userPick: "pass",
      shirts: { actor: "#10", passTarget: "#9", forward: "#9" },
    });
    expect(coach.text).toContain("You picked pass");
    expect(coach.text.length).toBeGreaterThan(explanation.text.length);
    const zh = mockExplanation({
      decide: result,
      questionId: "why_actual",
      mode: "coach",
      language: "zh",
      userPick: "pass",
      shirts: { actor: "#10", passTarget: "#9", forward: "#9" },
    });
    expect(zh.text).toContain("揭示前");
    expect(zh.text).not.toMatch(/%|success_prob|value_gain/);
  });
});
