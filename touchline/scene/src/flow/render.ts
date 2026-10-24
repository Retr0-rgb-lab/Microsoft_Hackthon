import type { Frame } from "../coords";
import { diagramMarkup } from "./diagram";
import { actionName, applyI18n, phaseName, roleName, text } from "./i18n";
import type { FlowState } from "./machine";
import type { DecisionPoint, RosterPlayer } from "./sample";
import { momentLabel, questionSet } from "./sample";
import { ACTION_CLASSES, ranked, type ActionClass } from "./types";

export type RenderContext = {
  decisions: readonly DecisionPoint[];
  roster: readonly RosterPlayer[];
  frame: Frame | null;
  previewT: number;
  homeName: string;
  awayName: string;
  shirt: (playerId: string | null) => string;
};

export function renderFlow(state: FlowState, ctx: RenderContext): void {
  const root = document.getElementById("app");
  if (!root) return;
  applyI18n(root, state.language);
  document.documentElement.lang = state.language === "zh" ? "zh" : "en";
  document.documentElement.dataset.phase = state.phase;
  document.documentElement.dataset.mode = state.mode;
  document.documentElement.dataset.revealed = String(state.revealed);

  const phase = textEl("phase-pill");
  phase.textContent = phaseName(state.phase, state.language);
  textEl("match-label").textContent = ctx.homeName && ctx.awayName ? `${ctx.homeName}  ·  ${ctx.awayName}` : "";
  paintClock(state.tMs);

  const play = must<HTMLButtonElement>("play-toggle");
  play.textContent = state.phase === "playing" ? text(state.language, "pause") : text(state.language, "play");
  press("mode-fan", state.mode === "fan");
  press("mode-coach", state.mode === "coach");
  pressGroup("#lang-toggle [data-lang]", "lang", state.language);
  pressGroup("#speed-toggle [data-speed]", "speed", String(state.speed));
  const viewCamera = state.phase === "preview" ? "top" : state.camera;
  press("cam-broadcast", viewCamera === "broadcast");
  press("cam-top", viewCamera === "top");
  must<HTMLElement>("inset").hidden = !(
    state.decide &&
    state.revealed &&
    state.phase !== "preview" &&
    viewCamera === "broadcast"
  );

  const scrub = must<HTMLInputElement>("scrub");
  if (document.activeElement !== scrub) scrub.value = String(Math.round(state.tMs));

  const gate = must<HTMLElement>("gate");
  gate.hidden = state.phase !== "enter";
  const hypo = must<HTMLElement>("hypo");
  hypo.hidden = state.phase !== "preview";
  hypo.textContent = text(state.language, "hypo");

  textEl("hint").textContent = hintFor(state);
  const event = ctx.decisions.find((item) => item.event_id === state.eventId) ?? null;
  textEl("carrier").textContent = event ? `${ctx.shirt(event.player_id)} · ${event.team_id}` : "";
  const asked = askedLabel(state, ctx, event);
  const bubble = textEl("user-bubble");
  bubble.hidden = asked.length === 0;
  bubble.textContent = asked;
  const askInput = must<HTMLInputElement>("ask-input");
  askInput.placeholder = text(state.language, "askPlaceholder");
  askInput.setAttribute("aria-label", text(state.language, "askPlaceholder"));
  must<HTMLButtonElement>("ask-send").disabled = !event;

  fillCases(state, ctx);
  fillQuestions(state, ctx, event);
  const analyze = must<HTMLButtonElement>("analyze");
  analyze.disabled = !event || state.phase === "loading";

  must<HTMLElement>("loading").hidden = state.phase !== "loading";
  const showCards = Boolean(state.decide) && (state.revealed || state.mode === "coach");
  must<HTMLElement>("distribution").hidden = !showCards;
  must<HTMLElement>("coach-prompt").hidden = !(state.mode === "coach" && state.decide && !state.revealed);
  must<HTMLElement>("distribution-note").hidden = !state.revealed;
  must<HTMLElement>("legend").hidden = !state.revealed;
  fillActions(state);

  must<HTMLButtonElement>("preview-btn").hidden = !(state.revealed && (state.phase === "deciding" || state.phase === "explaining"));
  must<HTMLButtonElement>("reset-btn").hidden = state.phase !== "preview";
  must<HTMLButtonElement>("explain-btn").hidden = !(state.mode === "fan" && state.revealed && state.phase !== "explaining");
  must<HTMLButtonElement>("reveal-btn").hidden = !(state.mode === "coach" && state.decide && state.userPick && !state.revealed);
  must<HTMLButtonElement>("back-btn").hidden = state.phase !== "explaining";

  const explain = must<HTMLElement>("explain-block");
  const showText = Boolean(state.agent && state.revealed);
  explain.hidden = !showText;
  textEl("explanation").textContent = showText ? state.agent?.text ?? "" : "";

  const banner = must<HTMLElement>("banner");
  banner.hidden = !state.agentDropped;
  banner.textContent = state.agentDropped ? text(state.language, "dropped") : "";

  const traceWrap = must<HTMLDetailsElement>("trace-wrap");
  const showTrace = Boolean(state.agent && state.revealed && !state.agentDropped);
  traceWrap.hidden = !showTrace;
  if (traceWrap.open !== state.traceOpen) traceWrap.open = state.traceOpen;
  fillTrace(state);

  const limits = must<HTMLElement>("limitations");
  limits.replaceChildren();
  const lines = state.revealed ? (state.agent?.limitations ?? state.decide?.limitations ?? []) : [];
  must<HTMLElement>("limits-block").hidden = lines.length === 0;
  for (const line of lines) {
    const item = document.createElement("li");
    item.textContent = line;
    limits.append(item);
  }

  paintDiagram(state, ctx);
}

export function paintClock(tMs: number): void {
  const clock = document.getElementById("clock");
  if (!clock) return;
  const sec = Math.max(0, tMs) / 1000;
  const mm = Math.floor(sec / 60);
  const ss = sec - mm * 60;
  clock.textContent = `${String(mm).padStart(2, "0")}:${ss.toFixed(1).padStart(4, "0")}`;
}

export function paintDiagram(state: FlowState, ctx: RenderContext): void {
  const svg = document.getElementById("diagram");
  if (!svg || !ctx.frame) return;
  const players = ctx.frame.players.map((row) => {
    const team = ctx.roster.find((player) => player.player_id === row[0])?.team_id ?? "HOME";
    return { team, x: row[1], y: row[2], carrier: row[0] === state.actorId };
  });
  const emphasize = state.phase === "preview" ? state.previewAction : state.focusedAction;
  svg.innerHTML = diagramMarkup({
    players,
    ball: { x: ctx.frame.ball[0], y: ctx.frame.ball[1] },
    decide: state.decide,
    showArrows: Boolean(state.decide && state.revealed),
    emphasize,
    preview:
      state.phase === "preview" && state.previewAction
        ? { action: state.previewAction, t: ctx.previewT }
        : null,
  });
}

function askedLabel(state: FlowState, ctx: RenderContext, event: DecisionPoint | null): string {
  if (state.questionId === "free_text") return state.questionText ?? "";
  if (!event || !state.questionId) return "";
  return questionSet(event, ctx.shirt, state.language).find((item) => item.id === state.questionId)?.label ?? "";
}

function fillCases(state: FlowState, ctx: RenderContext): void {
  const root = must<HTMLElement>("cases");
  root.replaceChildren();
  ctx.decisions.forEach((event, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.eventId = event.event_id;
    button.textContent = momentLabel(index, event, (id) => ctx.shirt(id), state.language);
    button.setAttribute("aria-pressed", String(event.event_id === state.eventId));
    root.append(button);
  });
}

function fillQuestions(state: FlowState, ctx: RenderContext, event: DecisionPoint | null): void {
  const root = must<HTMLElement>("questions");
  root.replaceChildren();
  if (!event) return;
  for (const question of questionSet(event, ctx.shirt, state.language)) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.question = question.id;
    button.textContent = question.label;
    button.setAttribute("aria-pressed", String(question.id === state.questionId));
    root.append(button);
  }
}

function fillActions(state: FlowState): void {
  const root = must<HTMLElement>("actions");
  root.replaceChildren();
  if (!state.decide) return;
  const items = state.revealed
    ? ranked(state.decide)
    : ACTION_CLASSES.map((action) => ({ action, prob: 0, role: "secondary" as const }));
  items.forEach((item, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "action";
    button.dataset.action = item.action;
    if (state.revealed) {
      button.dataset.role = item.role;
      button.dataset.line = item.action === state.decide?.actual_action ? "solid" : "dashed";
    }
    if (state.userPick === item.action) button.dataset.pick = "true";
    if (state.focusedAction === item.action || state.previewAction === item.action) button.dataset.focus = "true";

    const mark = document.createElement("span");
    mark.className = "mark";
    const name = document.createElement("span");
    name.className = "action-name";
    const rank = state.revealed ? `${index + 1}  ` : "";
    name.textContent = `${rank}${actionName(item.action, state.language)}`;
    const meta = document.createElement("span");
    meta.className = "action-meta";
    meta.textContent = metaFor(state, item.action, item.role, item.prob);
    button.append(mark, name, meta);
    if (state.revealed) {
      const bar = document.createElement("span");
      bar.className = "bar";
      const fill = document.createElement("span");
      fill.style.width = `${Math.max(4, item.prob * 100)}%`;
      bar.append(fill);
      button.append(bar);
    }
    root.append(button);
  });
}

function metaFor(state: FlowState, action: ActionClass, role: "primary" | "secondary", prob: number): string {
  if (!state.revealed) {
    return state.userPick === action ? text(state.language, "yourPick") : "";
  }
  const bits = [prob.toFixed(2), role === "primary" ? text(state.language, "primary") : text(state.language, "secondary")];
  if (action === state.decide?.actual_action) bits.push(text(state.language, "recorded"));
  return bits.join(" · ");
}

function fillTrace(state: FlowState): void {
  const root = must<HTMLElement>("trace");
  root.replaceChildren();
  if (!state.agent || !state.revealed) return;
  for (const step of state.agent.agent_trace) {
    const item = document.createElement("li");
    const who = document.createElement("span");
    who.textContent = roleName(step.agent, state.language);
    const tool = document.createElement("code");
    tool.textContent = step.tool;
    const time = document.createElement("span");
    time.textContent = step.ok ? `${step.ms} ms` : "—";
    item.append(who, tool, time);
    root.append(item);
  }
}

function hintFor(state: FlowState): string {
  if (state.hint === "not_carrier") return text(state.language, "notCarrier");
  if (state.hint === "wait") return text(state.language, "wait");
  if (state.phase === "playing") return text(state.language, "playingHint");
  if (state.phase === "paused") return text(state.language, "pausedHint");
  if (state.phase === "selecting") return text(state.language, "selectingHint");
  if (state.phase === "deciding") return text(state.language, "decidingHint");
  if (state.phase === "preview") return text(state.language, "previewHint");
  if (state.phase === "explaining") return text(state.language, "explainHint");
  if (state.phase === "enter") return text(state.language, "enterBody");
  if (state.phase === "loading") return text(state.language, "loading");
  if (!state.eventId) return text(state.language, "emptyAsk");
  return text(state.language, "distributionNote");
}

function press(id: string, on: boolean): void {
  must<HTMLButtonElement>(id).setAttribute("aria-pressed", String(on));
}

function pressGroup(selector: string, attr: string, value: string): void {
  document.querySelectorAll<HTMLButtonElement>(selector).forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset[attr] === value));
  });
}

function textEl(id: string): HTMLElement {
  return must<HTMLElement>(id);
}

function must<T extends HTMLElement>(id: string): T {
  const found = document.getElementById(id);
  if (!found) throw new Error(`missing #${id}`);
  return found as T;
}
