import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { bindAgent, initialFlowState, PHASES, reduce, type FlowState } from "./machine";
import type { AgentExplanation, DecideFromTracking } from "./types";

const flowDoc = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../FLOW.md");

function decide(over: Partial<DecideFromTracking> = {}): DecideFromTracking {
  return {
    status: "ready",
    event_id: "e1",
    snapshot_id: "f1:e1",
    candidate_set_id: "stub:e1:o1",
    t_ms: 1000,
    actor_id: "H10",
    team_id: "HOME",
    actual_action: "dribble",
    probs: { pass: 0.2, shoot: 0.1, dribble: 0.5, hold: 0.2 },
    primary: { action: "dribble", prob: 0.5, role: "primary", geometry: null },
    secondaries: [
      { action: "pass", prob: 0.2, role: "secondary", geometry: null },
      { action: "hold", prob: 0.2, role: "secondary", geometry: null },
      { action: "shoot", prob: 0.1, role: "secondary", geometry: null },
    ],
    limitations: ["stub"],
    ...over,
  };
}

function agent(id = "stub:e1:o1"): AgentExplanation {
  return {
    candidate_set_id: id,
    mode: "fan",
    language: "en",
    question_id: "why_actual",
    text: "fan text",
    agent_trace: [{ agent: "attack", tool: "decide_from_tracking", ms: 12, ok: true }],
    limitations: ["stub"],
  };
}

function paused(): FlowState {
  return reduce(initialFlowState(), {
    type: "jump",
    tMs: 1000,
    snapshotId: "f1:e1",
    eventId: "e1",
    actorId: "H10",
  });
}

describe("decision flow state machine", () => {
  it("names every phase in the flow note", () => {
    const doc = readFileSync(flowDoc, "utf8");
    for (const phase of PHASES) expect(doc).toContain(phase);
    expect(doc).toContain("traceOpen");
    expect(doc).toContain("decide_from_tracking");
  });

  it("walks enter, play, decision pause, question, load, distribution", () => {
    let state = reduce(initialFlowState(), { type: "start" });
    expect(state.phase).toBe("playing");
    state = reduce(state, { type: "tick", tMs: 400 });
    state = reduce(state, { type: "arrive", tMs: 1000, snapshotId: "f1:e1", eventId: "e1", actorId: "H10" });
    expect(state.phase).toBe("paused");
    expect(state.tMs).toBe(1000);
    state = reduce(state, { type: "select_question", questionId: "why_not_pass" });
    expect(state.phase).toBe("selecting");
    state = reduce(state, { type: "request" });
    expect(state.phase).toBe("loading");
    expect(state.decide).toBeNull();
    const requestId = state.requestId;
    state = reduce(state, { type: "resolve", requestId, decide: decide(), agent: agent() });
    expect(state.phase).toBe("deciding");
    expect(state.revealed).toBe(true);
    expect(state.agent?.text).toBe("fan text");
    expect(state.decide?.primary.action).toBe("dribble");
  });

  it("drops a stale response and a mismatched candidate set", () => {
    let state = reduce(paused(), { type: "request" });
    const requestId = state.requestId;
    state = reduce(state, { type: "select_question", questionId: "why_forward" });
    expect(state.phase).toBe("selecting");
    const ignored = reduce(state, { type: "resolve", requestId, decide: decide(), agent: agent() });
    expect(ignored.decide).toBeNull();
    state = reduce(state, { type: "request" });
    const fresh = state.requestId;
    const dropped = reduce(state, {
      type: "resolve",
      requestId: fresh,
      decide: decide(),
      agent: agent("other-set"),
    });
    expect(dropped.decide?.primary.action).toBe("dribble");
    expect(dropped.agent).toBeNull();
    expect(dropped.agentDropped).toBe(true);
    expect(bindAgent(decide(), agent("other-set")).dropped).toBe(true);
  });

  it("clears the previous result when mode, question, or snapshot changes", () => {
    let state = reduce(paused(), { type: "select_question", questionId: "why_actual" });
    state = reduce(state, { type: "request" });
    state = reduce(state, { type: "resolve", requestId: state.requestId, decide: decide(), agent: agent() });
    state = reduce(state, { type: "explain" });
    expect(state.phase).toBe("explaining");
    const mode = reduce(state, { type: "set_mode", mode: "coach" });
    expect(mode.mode).toBe("coach");
    expect(mode.decide).toBeNull();
    expect(mode.agent).toBeNull();
    expect(mode.revealed).toBe(false);
    expect(mode.phase).toBe("selecting");

    state = reduce(paused(), { type: "request" });
    state = reduce(state, { type: "resolve", requestId: state.requestId, decide: decide(), agent: agent() });
    const question = reduce(state, { type: "select_question", questionId: "why_not_pass" });
    expect(question.decide).toBeNull();
    expect(question.agent).toBeNull();
    expect(question.questionId).toBe("why_not_pass");

    const jumped = reduce(state, {
      type: "jump",
      tMs: 2000,
      snapshotId: "f2:e2",
      eventId: "e2",
      actorId: "H08",
    });
    expect(jumped.decide).toBeNull();
    expect(jumped.snapshotId).toBe("f2:e2");

    const typed = reduce(paused(), { type: "select_question", questionId: "free_text", text: "Why hold?" });
    expect(typed.questionText).toBe("Why hold?");
    expect(typed.phase).toBe("selecting");
    const cleared = reduce(typed, {
      type: "jump",
      tMs: 2000,
      snapshotId: "f2:e2",
      eventId: "e2",
      actorId: "H08",
    });
    expect(cleared.questionText).toBeNull();
    expect(cleared.questionId).toBeNull();
  });

  it("hides the coach distribution until a pick is revealed", () => {
    let state = reduce(paused(), { type: "set_mode", mode: "coach" });
    state = reduce(state, { type: "request" });
    state = reduce(state, { type: "resolve", requestId: state.requestId, decide: decide(), agent: agent() });
    expect(state.phase).toBe("deciding");
    expect(state.revealed).toBe(false);
    expect(state.agent).toBeNull();
    expect(reduce(state, { type: "reveal", agent: agent() }).revealed).toBe(false);
    state = reduce(state, { type: "pick", action: "pass" });
    expect(state.userPick).toBe("pass");
    expect(state.revealed).toBe(false);
    state = reduce(state, { type: "reveal", agent: agent() });
    expect(state.phase).toBe("explaining");
    expect(state.revealed).toBe(true);
    expect(state.agent?.text).toBe("fan text");
    const changed = reduce(state, { type: "pick", action: "hold" });
    expect(changed.revealed).toBe(false);
    expect(changed.agent).toBeNull();
    expect(changed.userPick).toBe("hold");
    expect(changed.decide).not.toBeNull();
  });

  it("previews a path and returns to the same snapshot", () => {
    let state = reduce(paused(), { type: "request" });
    state = reduce(state, { type: "resolve", requestId: state.requestId, decide: decide(), agent: agent() });
    state = reduce(state, { type: "explain" });
    const preview = reduce(state, { type: "preview", action: "pass" });
    expect(preview.phase).toBe("preview");
    expect(preview.previewAction).toBe("pass");
    expect(preview.snapshotId).toBe("f1:e1");
    const back = reduce(preview, { type: "preview_done" });
    expect(back.phase).toBe("explaining");
    expect(back.tMs).toBe(1000);
    expect(back.decide?.snapshot_id).toBe("f1:e1");
  });

  it("toggles the agent trace only when agent text is bound", () => {
    let state = reduce(paused(), { type: "request" });
    expect(reduce(state, { type: "toggle_trace" }).traceOpen).toBe(false);
    state = reduce(state, { type: "resolve", requestId: state.requestId, decide: decide(), agent: agent() });
    state = reduce(state, { type: "toggle_trace" });
    expect(state.traceOpen).toBe(true);
    state = reduce(state, { type: "set_language", language: "zh" });
    expect(state.language).toBe("zh");
    expect(state.traceOpen).toBe(true);
    expect(state.agent?.text).toBe("fan text");
  });
});
