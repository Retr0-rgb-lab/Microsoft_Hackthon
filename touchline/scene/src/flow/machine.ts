import type {
  ActionClass,
  AgentExplanation,
  AudienceMode,
  DecideFromTracking,
  Language,
} from "./types";

/**
 * Main-flow phases. Agent process is `traceOpen`, not its own phase.
 * Diagram and invalidation rules: `touchline/scene/FLOW.md`.
 *
 * enter → playing → paused (decision_point) → selecting → loading →
 * deciding → preview (top-down path) → explaining
 */
export const PHASES = [
  "enter",
  "playing",
  "paused",
  "selecting",
  "loading",
  "deciding",
  "preview",
  "explaining",
] as const;

export type Phase = (typeof PHASES)[number];

export type CameraMode = "broadcast" | "top";

export type FlowHint = "not_carrier" | "wait";

export type FlowState = {
  phase: Phase;
  language: Language;
  mode: AudienceMode;
  speed: 1 | 4;
  camera: CameraMode;
  tMs: number;
  snapshotId: string | null;
  eventId: string | null;
  actorId: string | null;
  questionId: string | null;
  questionText: string | null;
  requestId: number;
  decide: DecideFromTracking | null;
  agent: AgentExplanation | null;
  agentDropped: boolean;
  userPick: ActionClass | null;
  revealed: boolean;
  traceOpen: boolean;
  focusedAction: ActionClass | null;
  previewAction: ActionClass | null;
  previewReturn: "deciding" | "explaining";
  hint: FlowHint | null;
};

export type FlowEvent =
  | { type: "start" }
  | { type: "tick"; tMs: number }
  | { type: "pause" }
  | { type: "resume" }
  | {
      type: "jump";
      tMs: number;
      snapshotId: string | null;
      eventId: string | null;
      actorId: string | null;
    }
  | { type: "arrive"; tMs: number; snapshotId: string; eventId: string; actorId: string }
  | { type: "select_actor"; actorId: string }
  | { type: "select_question"; questionId: string; text?: string | null }
  | { type: "request" }
  | { type: "resolve"; requestId: number; decide: DecideFromTracking; agent: AgentExplanation }
  | { type: "preview"; action: ActionClass }
  | { type: "preview_done" }
  | { type: "explain" }
  | { type: "show_distribution" }
  | { type: "pick"; action: ActionClass }
  | { type: "reveal"; agent: AgentExplanation }
  | { type: "focus"; action: ActionClass }
  | { type: "set_mode"; mode: AudienceMode }
  | { type: "set_language"; language: Language; agent?: AgentExplanation | null }
  | { type: "toggle_trace" }
  | { type: "set_camera"; camera: CameraMode }
  | { type: "set_speed"; speed: 1 | 4 }
  | { type: "retry_agent"; agent: AgentExplanation };

export function initialFlowState(): FlowState {
  return {
    phase: "enter",
    language: "en",
    mode: "fan",
    speed: 1,
    camera: "broadcast",
    tMs: 0,
    snapshotId: null,
    eventId: null,
    actorId: null,
    questionId: null,
    questionText: null,
    requestId: 0,
    decide: null,
    agent: null,
    agentDropped: false,
    userPick: null,
    revealed: false,
    traceOpen: false,
    focusedAction: null,
    previewAction: null,
    previewReturn: "deciding",
    hint: null,
  };
}

export function bindAgent(
  decide: DecideFromTracking,
  agent: AgentExplanation,
): { agent: AgentExplanation | null; dropped: boolean } {
  if (agent.candidate_set_id !== decide.candidate_set_id) {
    return { agent: null, dropped: true };
  }
  return { agent, dropped: false };
}

export function reduce(state: FlowState, event: FlowEvent): FlowState {
  switch (event.type) {
    case "start":
      if (state.phase !== "enter") return state;
      return { ...state, phase: "playing", hint: null };
    case "tick":
      if (state.phase !== "playing") return state;
      return { ...state, tMs: event.tMs };
    case "pause":
      if (state.phase !== "playing") return state;
      return { ...state, phase: "paused" };
    case "resume":
      if (state.phase === "enter") return { ...state, phase: "playing", hint: null };
      if (state.phase === "playing") return state;
      return {
        ...clearAnalysis(state, "playing"),
        snapshotId: null,
        eventId: null,
        actorId: null,
        questionId: null,
        questionText: null,
      };
    case "jump":
      return {
        ...clearAnalysis(state, "paused"),
        tMs: event.tMs,
        snapshotId: event.snapshotId,
        eventId: event.eventId,
        actorId: event.actorId,
        questionId: null,
        questionText: null,
      };
    case "arrive":
      if (state.phase !== "playing") return state;
      return {
        ...clearAnalysis(state, "paused"),
        tMs: event.tMs,
        snapshotId: event.snapshotId,
        eventId: event.eventId,
        actorId: event.actorId,
        questionId: null,
        questionText: null,
      };
    case "select_actor": {
      if (!state.eventId || state.actorId !== event.actorId) {
        return { ...state, hint: state.eventId ? "not_carrier" : "wait" };
      }
      if (hasAnalysis(state)) return { ...state, hint: null };
      return { ...state, phase: "selecting", hint: null };
    }
    case "select_question": {
      const nextPhase: Phase = state.eventId ? "selecting" : state.phase;
      const base = hasAnalysis(state) ? clearAnalysis(state, nextPhase) : { ...state, phase: nextPhase };
      return { ...base, questionId: event.questionId, questionText: event.text ?? null, hint: null };
    }
    case "request": {
      if (!state.eventId || !state.snapshotId) return state;
      return {
        ...clearAnalysis(state, "loading"),
        questionId: state.questionId ?? "why_actual",
        eventId: state.eventId,
        snapshotId: state.snapshotId,
        actorId: state.actorId,
        tMs: state.tMs,
      };
    }
    case "resolve": {
      if (event.requestId !== state.requestId) return state;
      if (state.phase !== "loading") return state;
      if (event.decide.snapshot_id !== state.snapshotId) return state;
      const showAgent = state.mode === "fan";
      const bound = showAgent ? bindAgent(event.decide, event.agent) : { agent: null, dropped: false };
      return {
        ...state,
        phase: "deciding",
        decide: event.decide,
        agent: bound.agent,
        agentDropped: bound.dropped,
        revealed: state.mode === "fan",
        userPick: null,
        focusedAction: null,
        hint: null,
      };
    }
    case "pick": {
      if (!state.decide || state.mode !== "coach") return state;
      if (!state.revealed) return { ...state, userPick: event.action, phase: "deciding" };
      if (state.userPick === event.action) return state;
      return {
        ...state,
        userPick: event.action,
        revealed: false,
        agent: null,
        agentDropped: false,
        traceOpen: false,
        phase: "deciding",
        previewAction: null,
        focusedAction: null,
      };
    }
    case "reveal": {
      if (state.mode !== "coach" || !state.decide || !state.userPick || state.revealed) return state;
      const bound = bindAgent(state.decide, event.agent);
      return {
        ...state,
        revealed: true,
        phase: "explaining",
        agent: bound.agent,
        agentDropped: bound.dropped,
        traceOpen: false,
      };
    }
    case "explain":
      if (!state.decide || !state.revealed) return state;
      if (state.phase !== "deciding" && state.phase !== "preview") return state;
      return { ...state, phase: "explaining" };
    case "show_distribution":
      if (state.phase !== "explaining" || !state.decide) return state;
      return { ...state, phase: "deciding" };
    case "focus":
      if (!state.revealed || !state.decide) return state;
      return { ...state, focusedAction: event.action };
    case "preview": {
      if (!state.revealed || !state.decide) return state;
      if (state.phase !== "deciding" && state.phase !== "explaining") return state;
      return {
        ...state,
        phase: "preview",
        previewReturn: state.phase,
        previewAction: event.action,
        focusedAction: event.action,
      };
    }
    case "preview_done":
      if (state.phase !== "preview") return state;
      return { ...state, phase: state.previewReturn, previewAction: null };
    case "set_mode": {
      if (state.mode === event.mode) return state;
      if (!hasAnalysis(state)) return { ...state, mode: event.mode };
      const phase: Phase = state.eventId ? "selecting" : state.phase === "playing" ? "playing" : "paused";
      return { ...clearAnalysis(state, phase), mode: event.mode };
    }
    case "set_language": {
      const next = { ...state, language: event.language };
      if (event.agent === undefined) return next;
      if (event.agent === null || !state.decide) {
        return { ...next, agent: null, agentDropped: false, traceOpen: false };
      }
      const bound = bindAgent(state.decide, event.agent);
      return {
        ...next,
        agent: bound.agent,
        agentDropped: bound.dropped,
        traceOpen: bound.dropped ? false : state.traceOpen,
      };
    }
    case "toggle_trace":
      if (!state.agent || state.agentDropped || !state.revealed) return state;
      return { ...state, traceOpen: !state.traceOpen };
    case "set_camera":
      return { ...state, camera: event.camera };
    case "set_speed":
      return { ...state, speed: event.speed };
    case "retry_agent": {
      if (!state.decide || !state.revealed) return state;
      const bound = bindAgent(state.decide, event.agent);
      return { ...state, agent: bound.agent, agentDropped: bound.dropped, traceOpen: false };
    }
    default: {
      const neverEvent: never = event;
      return neverEvent;
    }
  }
}

function hasAnalysis(state: FlowState): boolean {
  return Boolean(
    state.decide ||
      state.agent ||
      state.phase === "loading" ||
      state.phase === "deciding" ||
      state.phase === "preview" ||
      state.phase === "explaining",
  );
}

/** Drop decision, agent text, and preview immediately. Bumps `requestId` so an in-flight mock cannot land. */
function clearAnalysis(state: FlowState, phase: Phase): FlowState {
  return {
    ...state,
    phase,
    requestId: state.requestId + 1,
    decide: null,
    agent: null,
    agentDropped: false,
    userPick: null,
    revealed: false,
    traceOpen: false,
    focusedAction: null,
    previewAction: null,
    previewReturn: "deciding",
    hint: null,
  };
}
