import type { Frame } from "../coords";
import type { DecisionPoint, RosterPlayer } from "./sample";
import { chosenOption, forwardPass } from "./sample";
import type {
  ActionClass,
  ActionGeometry,
  AgentExplanation,
  AgentTraceStep,
  DecideFromTracking,
  RankedAction,
} from "./types";
import { ACTION_CLASSES } from "./types";
import type { AudienceMode, Language, QuestionId } from "./types";

export type DecideRequest = {
  frame: Frame;
  event: DecisionPoint;
  roster: readonly RosterPlayer[];
};

export type ExplainRequest = {
  decide: DecideFromTracking;
  questionId: QuestionId;
  mode: AudienceMode;
  language: Language;
  userPick: ActionClass | null;
  shirts: {
    actor: string;
    passTarget: string;
    forward: string;
  };
};

const LIMIT_EN = [
  "Synthetic tracking from the checked-in sample. Squads are fictional.",
  "Softmax shares are a stub, not the fitted weight file.",
  "Pass and dribble scores stay in the payload and are not drawn. They are not completion percentages.",
  "Hold has no path. Shot is a segment to the goal mouth.",
];

const LIMIT_ZH = [
  "跟踪来自已入库的合成样本。球队为虚构。",
  "Softmax 份额是桩数据，不是已拟合的权重。",
  "传球和带球的 score 留在数据里，不画出来，也不是完成百分比。",
  "等待没有路径。射门是指向球门的线段。",
];

/**
 * Deterministic stub for `decide_from_tracking`.
 * Geometry comes from the sample `decision_point`. Shares are a local softmax,
 * not `weights.json`. One path per action class. The recorded class is solid
 * in the UI; this function only labels `actual_action`.
 */
export function decideFromSample(request: DecideRequest): DecideFromTracking {
  const { frame, event } = request;
  const start = playerXY(frame, event.player_id);
  const actual = actualAction(event);
  const pass = passOption(event, actual);
  const carry = carryOption(event, actual);
  const shot = event.options.find((option) => option.type === "shot") ?? null;
  const shotDist = shot ? Math.hypot(shot.end_location[0] - start[0], shot.end_location[1] - start[1]) : 80;
  // Class share uses the best onside pass. The drawn pass line is still one arrow:
  // the recorded receiver when the touch was a pass, otherwise that forward pass.
  const passProgress = forwardPass(event)?.progress_m ?? pass?.progress_m ?? -10;
  const logits: Record<ActionClass, number> = {
    pass: 1.1 + clamp(passProgress, -25, 35) / 40,
    shoot: shot ? Math.max(-1.2, 1.4 - shotDist / 22) : -1.6,
    dribble: 1.0 + clamp(carry?.progress_m ?? 0, -8, 22) / 18,
    hold: 0.55,
  };
  const probs = softmax(logits);
  const order = [...ACTION_CLASSES].sort((a, b) => probs[b] - probs[a] || ACTION_CLASSES.indexOf(a) - ACTION_CLASSES.indexOf(b));
  const geometries: Record<ActionClass, ActionGeometry | null> = {
    pass: pass
      ? withScore(pass.target_player_id, segment(start, pass.end_location, 2), pass.progress_m)
      : null,
    dribble: carry
      ? withScore(event.player_id, segment(start, carry.end_location, 5), carry.progress_m)
      : null,
    shoot: shot ? { target_id: null, path: segment(start, shot.end_location, 2) } : null,
    hold: null,
  };
  const ranked: RankedAction[] = order.map((action, index) => ({
    action,
    prob: probs[action],
    role: index === 0 ? "primary" : "secondary",
    geometry: geometries[action],
  }));
  const primary = ranked[0];
  if (!primary) throw new Error("empty distribution");
  const frameId = frame.frame_id;
  return {
    status: "ready",
    event_id: event.event_id,
    snapshot_id: `f${frameId}:${event.event_id}`,
    candidate_set_id: `stub:${event.event_id}:${event.chosen_option_id}`,
    t_ms: event.available_at_ms,
    actor_id: event.player_id,
    team_id: event.team_id,
    actual_action: actual,
    probs,
    primary,
    secondaries: ranked.slice(1),
    limitations: LIMIT_EN,
  };
}

export function mockExplanation(request: ExplainRequest): AgentExplanation {
  const { decide, language, mode, questionId } = request;
  const text = language === "zh" ? zhText(request) : enText(request);
  return {
    candidate_set_id: decide.candidate_set_id,
    mode,
    language,
    question_id: questionId,
    text,
    agent_trace: traceFor(decide.event_id),
    limitations: language === "zh" ? LIMIT_ZH : LIMIT_EN,
  };
}

export function forwardShirtId(event: DecisionPoint): string | null {
  return forwardPass(event)?.target_player_id ?? null;
}

function enText(request: ExplainRequest): string {
  const { decide, questionId, mode, userPick, shirts } = request;
  const actual = decide.actual_action;
  const primary = decide.primary.action;
  const passTarget = shirts.passTarget;
  const lead =
    mode === "coach" && userPick
      ? `You picked ${userPick} before the reveal. `
      : "";
  const recorded = `The recorded action is ${actual}. The largest share is ${primary}. The solid mark is what happened. Dashed marks are the other classes.`;
  const paths = `The pass line ends at ${passTarget}. The dribble line stays with ${shirts.actor}. The shot line aims at the goal mouth. Hold is a ring, not a path.`;
  let question = "Compare the solid mark with the dashed ones. This is not a grade.";
  if (questionId === "why_not_pass") {
    question =
      shirts.forward === passTarget
        ? `You asked about a pass to ${shirts.forward}. That teammate is the pass line.`
        : `You asked about a pass to ${shirts.forward}. The single pass line is ${passTarget}, because that is the recorded pass. ${shirts.forward} stays on the option list without a second pass arrow.`;
  } else if (questionId === "why_forward") {
    question = `Forward shape is the pass to ${shirts.forward} when that pass is the pass line, otherwise the dribble line. Hold does not advance the ball.`;
  }
  if (mode === "fan") {
    return `${lead}${shirts.actor} is on the ball. ${recorded} ${question}`;
  }
  return `${lead}${recorded} ${paths} ${question} Fan mode stops at the shares. This review names each line so you can talk through the choice.`;
}

function zhText(request: ExplainRequest): string {
  const { decide, questionId, mode, userPick, shirts } = request;
  const actual = zhAction(decide.actual_action);
  const primary = zhAction(decide.primary.action);
  const pick = userPick ? `你在揭示前选择了${zhAction(userPick)}。` : "";
  const recorded = `实际发生的是${actual}。份额最大的是${primary}。实线是已经发生的动作，虚线是其他类别。`;
  const paths = `传球线终点是 ${shirts.passTarget}。带球线留在 ${shirts.actor}。射门线指向球门。等待只是一个环，没有路径。`;
  let question = "把实线和虚线放在一起看。这不是评分。";
  if (questionId === "why_not_pass") {
    question =
      shirts.forward === shirts.passTarget
        ? `你问的是传给 ${shirts.forward}。那名队友就是这条传球线。`
        : `你问的是传给 ${shirts.forward}。唯一的传球线是 ${shirts.passTarget}，因为那是实际传球。${shirts.forward} 仍在选项里，但不会再画第二条传球线。`;
  } else if (questionId === "why_forward") {
    question = `向前的形状：若传球线就是传给 ${shirts.forward}，看那条线；否则看带球线。等待不会把球向前送。`;
  }
  if (mode === "fan") return `${pick}${shirts.actor} 持球。${recorded}${question}`;
  return `${pick}${recorded}${paths}${question}球迷模式只讲份额。训练复盘会点名每一条线，方便你先讲自己的判断。`;
}

function zhAction(action: ActionClass): string {
  if (action === "pass") return "传球";
  if (action === "shoot") return "射门";
  if (action === "dribble") return "带球";
  return "等待";
}

function traceFor(eventId: string): AgentTraceStep[] {
  const seed = eventId.charCodeAt(eventId.length - 1) || 1;
  return [
    { agent: "coordinator", tool: "read_frame", ms: 18 + (seed % 7), ok: true },
    { agent: "attack", tool: "decide_from_tracking", ms: 36 + (seed % 11), ok: true },
    { agent: "defense", tool: "simulate_action", ms: 22 + (seed % 9), ok: true },
    { agent: "review", tool: "check_candidate_set", ms: 8 + (seed % 5), ok: true },
  ];
}

function actualAction(event: DecisionPoint): ActionClass {
  const chosen = chosenOption(event);
  if (chosen.type === "pass") return "pass";
  if (chosen.type === "shot") return "shoot";
  return "dribble";
}

function passOption(event: DecisionPoint, actual: ActionClass) {
  if (actual === "pass") {
    return event.options.find((option) => option.option_id === event.chosen_option_id && option.type === "pass") ?? null;
  }
  return forwardPass(event);
}

function carryOption(event: DecisionPoint, actual: ActionClass) {
  const carries = event.options.filter((option) => option.type === "carry");
  if (!carries.length) return null;
  if (actual === "dribble") {
    return carries.find((option) => option.option_id === event.chosen_option_id) ?? carries[0] ?? null;
  }
  return [...carries].sort((a, b) => b.progress_m - a.progress_m || a.option_id.localeCompare(b.option_id))[0] ?? null;
}

function withScore(targetId: string | null, path: [number, number][], progress: number): ActionGeometry {
  return { target_id: targetId, path, score: Math.round(progress * 1000) / 1000 };
}

function segment(start: [number, number], end: [number, number], steps: number): [number, number][] {
  const points: [number, number][] = [];
  for (let i = 0; i < steps; i += 1) {
    const t = steps === 1 ? 0 : i / (steps - 1);
    points.push([
      Math.round((start[0] + (end[0] - start[0]) * t) * 1000) / 1000,
      Math.round((start[1] + (end[1] - start[1]) * t) * 1000) / 1000,
    ]);
  }
  return points;
}

function playerXY(frame: Frame, playerId: string): [number, number] {
  const row = frame.players.find((player) => player[0] === playerId);
  if (!row) throw new Error(`Player ${playerId} is not on the frame`);
  return [row[1], row[2]];
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function softmax(logits: Record<ActionClass, number>): Record<ActionClass, number> {
  const peak = Math.max(...ACTION_CLASSES.map((label) => logits[label]));
  const exps = ACTION_CLASSES.map((label) => Math.exp(logits[label] - peak));
  const total = exps.reduce((sum, value) => sum + value, 0);
  const probs = {} as Record<ActionClass, number>;
  ACTION_CLASSES.forEach((label, index) => {
    probs[label] = (exps[index] ?? 0) / total;
  });
  return probs;
}
