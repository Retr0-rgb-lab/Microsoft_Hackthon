import * as THREE from "three";
import { applyPose, createActors } from "../actors";
import { sampleAt, toScene, type Frame } from "../coords";
import { createStage } from "../pitch";
import { buildArrows, disposeArrows, setArrowEmphasis, type ArrowLayer } from "./arrows";
import { createMockClient, type DecisionFlowClient } from "./client";
import { pointAlong } from "./geometry";
import { phaseName } from "./i18n";
import { initialFlowState, reduce, type FlowEvent, type FlowState } from "./machine";
import { decideFromSample, forwardShirtId, mockExplanation, type ExplainRequest } from "./mock";
import { paintClock, paintDiagram, renderFlow, type RenderContext } from "./render";
import {
  frameForTime,
  parseDecisionPoints,
  snapshotIdFor,
  type DecisionPoint,
  type RosterPlayer,
} from "./sample";
import { actionByClass, type ActionClass, type Language, type QuestionId } from "./types";

type Meta = {
  frame_hz: number;
  teams: { team_id: string; name: string }[];
  players: { player_id: string; team_id: string; jersey_number: number }[];
};

const client: DecisionFlowClient = createMockClient();
let state: FlowState = initialFlowState();
let rendering = false;
let previewT = 0;
let previewSeen = false;
let decisions: DecisionPoint[] = [];
let frames: Frame[] = [];
let roster: RosterPlayer[] = [];
let hz = 25;
let span = 30000;
let homeName = "";
let awayName = "";

const canvas = must<HTMLCanvasElement>("view");
const statusEl = must<HTMLElement>("status");

function dispatch(event: FlowEvent): void {
  rendering = true;
  state = reduce(state, event);
  if (event.type !== "tick") {
    renderFlow(state, context());
    syncArrows();
  }
  rendering = false;
}

function context(): RenderContext {
  return {
    decisions,
    roster,
    frame: frameAt(state.tMs),
    previewT,
    homeName,
    awayName,
    shirt,
  };
}

function shirt(playerId: string | null): string {
  if (!playerId) return "#?";
  const player = roster.find((item) => item.player_id === playerId);
  return player ? `#${player.jersey_number}` : playerId;
}

function frameAt(tMs: number): Frame | null {
  if (!frames.length) return null;
  const { i0 } = sampleAt(tMs, hz, frames.length);
  return frames[i0] ?? null;
}

function explainBody(
  decide: NonNullable<FlowState["decide"]>,
  questionId: QuestionId,
  mode: FlowState["mode"],
  language: Language,
  userPick: ActionClass | null,
): ExplainRequest {
  const event = decisions.find((item) => item.event_id === decide.event_id);
  const pass = actionByClass(decide, "pass");
  return {
    decide,
    questionId,
    mode,
    language,
    userPick,
    shirts: {
      actor: shirt(decide.actor_id),
      passTarget: shirt(pass?.geometry?.target_id ?? null),
      forward: shirt(event ? forwardShirtId(event) : null),
    },
  };
}

function jump(event: DecisionPoint): void {
  const frame = frameForTime(frames, event.available_at_ms, hz);
  dispatch({
    type: "jump",
    tMs: event.available_at_ms,
    snapshotId: snapshotIdFor(frame.frame_id, event.event_id),
    eventId: event.event_id,
    actorId: event.player_id,
  });
}

function jumpTime(tMs: number): void {
  const near = decisions.find((event) => Math.abs(event.available_at_ms - tMs) <= 40);
  if (near) {
    jump(near);
    return;
  }
  dispatch({ type: "jump", tMs, snapshotId: null, eventId: null, actorId: null });
}

async function analyze(): Promise<void> {
  const event = decisions.find((item) => item.event_id === state.eventId);
  if (!event) return;
  const questionId = (state.questionId ?? "why_actual") as QuestionId;
  if (state.questionId !== questionId) dispatch({ type: "select_question", questionId });
  const frame = frameForTime(frames, event.available_at_ms, hz);
  dispatch({ type: "request" });
  const requestId = state.requestId;
  try {
    const decide = await client.decide({ frame, event, roster });
    if (state.requestId !== requestId) return;
    const agent = await client.explain(explainBody(decide, questionId, state.mode, state.language, null));
    if (state.requestId !== requestId) return;
    dispatch({ type: "resolve", requestId, decide, agent });
  } catch (error) {
    if (state.requestId !== requestId) return;
    dispatch({ type: "select_question", questionId });
    statusEl.textContent = error instanceof Error ? error.message : "Could not read the frame.";
  }
}

async function reveal(): Promise<void> {
  if (!state.decide || !state.userPick || state.mode !== "coach") return;
  const questionId = (state.questionId ?? "why_actual") as QuestionId;
  const agent = await client.explain(explainBody(state.decide, questionId, "coach", state.language, state.userPick));
  if (!state.decide || state.revealed || state.userPick == null) return;
  dispatch({ type: "reveal", agent });
}

async function retryAgent(): Promise<void> {
  if (!state.decide || !state.revealed) return;
  const questionId = (state.questionId ?? "why_actual") as QuestionId;
  const agent = await client.explain(
    explainBody(state.decide, questionId, state.mode, state.language, state.userPick),
  );
  dispatch({ type: "retry_agent", agent });
}

async function setLanguage(language: Language): Promise<void> {
  if (!state.decide || !state.revealed) {
    dispatch({ type: "set_language", language });
    return;
  }
  const questionId = (state.questionId ?? "why_actual") as QuestionId;
  const agent = await client.explain(explainBody(state.decide, questionId, state.mode, language, state.userPick));
  dispatch({ type: "set_language", language, agent });
}

function bindUi(): void {
  document.body.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;
    if (target.closest("#start")) dispatch({ type: "start" });
    if (target.closest("#play-toggle")) {
      if (state.phase === "playing") dispatch({ type: "pause" });
      else if (state.phase === "enter") dispatch({ type: "start" });
      else dispatch({ type: "resume" });
    }
    if (target.closest("#analyze")) void analyze();
    if (target.closest("#reveal-btn")) void reveal();
    if (target.closest("#banner")) void retryAgent();
    if (target.closest("#preview-btn")) {
      const action = state.focusedAction ?? state.decide?.primary.action;
      if (action) dispatch({ type: "preview", action });
    }
    if (target.closest("#reset-btn")) dispatch({ type: "preview_done" });
    if (target.closest("#explain-btn")) dispatch({ type: "explain" });
    if (target.closest("#back-btn")) dispatch({ type: "show_distribution" });
    if (target.closest("#cam-broadcast")) dispatch({ type: "set_camera", camera: "broadcast" });
    if (target.closest("#cam-top")) dispatch({ type: "set_camera", camera: "top" });
    if (target.closest("#mode-fan")) dispatch({ type: "set_mode", mode: "fan" });
    if (target.closest("#mode-coach")) dispatch({ type: "set_mode", mode: "coach" });
    const lang = target.closest<HTMLElement>("[data-lang]")?.dataset.lang;
    if (lang === "en" || lang === "zh") void setLanguage(lang);
    const speed = target.closest<HTMLElement>("[data-speed]")?.dataset.speed;
    if (speed === "1" || speed === "4") dispatch({ type: "set_speed", speed: Number(speed) as 1 | 4 });
    const moment = target.closest<HTMLElement>("[data-event-id]")?.dataset.eventId;
    const chosen = decisions.find((item) => item.event_id === moment);
    if (chosen) jump(chosen);
    const question = target.closest<HTMLElement>("[data-question]")?.dataset.question;
    if (question) dispatch({ type: "select_question", questionId: question });
    const action = target.closest<HTMLElement>("[data-action]")?.dataset.action as ActionClass | undefined;
    if (action) {
      if (state.mode === "coach" && state.decide && !state.revealed) dispatch({ type: "pick", action });
      else dispatch({ type: "focus", action });
    }
  });

  must<HTMLDetailsElement>("trace-wrap").addEventListener("toggle", () => {
    if (rendering) return;
    const open = must<HTMLDetailsElement>("trace-wrap").open;
    if (open !== state.traceOpen) dispatch({ type: "toggle_trace" });
  });

  must<HTMLInputElement>("scrub").addEventListener("input", () => {
    jumpTime(Number(must<HTMLInputElement>("scrub").value));
  });

  window.addEventListener("keydown", (event) => {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
    if (event.key === " ") {
      event.preventDefault();
      if (state.phase === "playing") dispatch({ type: "pause" });
      else if (state.phase === "enter") dispatch({ type: "start" });
      else if (state.phase === "paused" || state.phase === "selecting") dispatch({ type: "resume" });
    }
    if (event.key === "1" || event.key === "b") dispatch({ type: "set_camera", camera: "broadcast" });
    if (event.key === "2" || event.key === "t") dispatch({ type: "set_camera", camera: "top" });
  });
}

function bootQuery(params: URLSearchParams): void {
  const language = params.get("lang") === "zh" ? "zh" : "en";
  const mode = params.get("mode") === "coach" ? "coach" : "fan";
  if (language !== "en") dispatch({ type: "set_language", language });
  if (mode === "coach") dispatch({ type: "set_mode", mode });
  const demo = params.get("demo");
  const event =
    decisions.find((item) => item.event_id === params.get("at")) ?? (demo ? decisions[0] : undefined);
  if (!event) return;
  jump(event);
  if (!demo) return;
  const questionId = (params.get("q") ?? "why_not_pass") as QuestionId;
  dispatch({ type: "select_question", questionId });
  dispatch({ type: "request" });
  if (demo === "loading") return;
  const decide = decideFromSample({ frame: frameForTime(frames, event.available_at_ms, hz), event, roster });
  const agent = mockExplanation(explainBody(decide, questionId, state.mode, state.language, null));
  dispatch({ type: "resolve", requestId: state.requestId, decide, agent });
  if (mode === "coach" && demo !== "deciding") {
    dispatch({ type: "pick", action: "pass" });
    if (!state.decide) return;
    const coachAgent = mockExplanation(explainBody(state.decide, questionId, "coach", state.language, "pass"));
    dispatch({ type: "reveal", agent: coachAgent });
  }
  if (demo === "explain" || demo === "trace") {
    if (state.mode === "fan") dispatch({ type: "explain" });
    if (demo === "trace") dispatch({ type: "toggle_trace" });
  }
  if (demo === "preview" && state.decide) {
    dispatch({ type: "preview", action: state.focusedAction ?? state.decide.primary.action });
  }
}

const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
  alpha: false,
  preserveDrawingBuffer: true,
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
createStage(scene, renderer);
scene.background = new THREE.Color(0xe7e0f6);

const broadcast = new THREE.PerspectiveCamera(28, 1, 0.1, 500);
broadcast.position.set(-6, 9.5, 46);
broadcast.lookAt(14, 1.2, 0);
const top = new THREE.OrthographicCamera(-60, 60, 40, -40, 0.1, 400);
top.position.set(0, 150, 0);
top.up.set(0, 0, -1);
top.lookAt(0, 0, 0);

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const carrierRing = new THREE.Mesh(
  new THREE.RingGeometry(1.05, 1.28, 48),
  new THREE.MeshBasicMaterial({ color: 0x7c3aed, side: THREE.DoubleSide, transparent: true, opacity: 0.95 }),
);
carrierRing.rotation.x = -Math.PI / 2;
carrierRing.visible = false;
const ghost = new THREE.Mesh(
  new THREE.SphereGeometry(0.34, 20, 14),
  new THREE.MeshBasicMaterial({ color: 0xc4b5fd, transparent: true, opacity: 0.92 }),
);
ghost.visible = false;
scene.add(carrierRing, ghost);

let actors: ReturnType<typeof createActors> | null = null;
let arrows: ArrowLayer | null = null;
let arrowKey = "";

function activeCamera(): THREE.Camera {
  return (state.phase === "preview" ? "top" : state.camera) === "top" ? top : broadcast;
}

function resize(): void {
  const width = canvas.clientWidth || 1;
  const height = canvas.clientHeight || 1;
  renderer.setSize(width, height, false);
  broadcast.aspect = width / height;
  broadcast.updateProjectionMatrix();
  const aspect = width / height;
  const pad = 1.12;
  let halfH = (68 / 2) * pad;
  let halfW = halfH * aspect;
  if (halfW < (105 / 2) * pad) {
    halfW = (105 / 2) * pad;
    halfH = halfW / aspect;
  }
  top.left = -halfW;
  top.right = halfW;
  top.top = halfH;
  top.bottom = -halfH;
  top.updateProjectionMatrix();
}

function syncArrows(): void {
  const key = state.revealed && state.decide ? state.decide.candidate_set_id : "";
  if (key !== arrowKey) {
    if (arrows) {
      scene.remove(arrows.group);
      disposeArrows(arrows);
      arrows = null;
    }
    arrowKey = key;
    if (key && state.decide) {
      arrows = buildArrows(state.decide);
      scene.add(arrows.group);
    }
  }
  if (arrows) {
    const emphasize = state.phase === "preview" ? state.previewAction : state.focusedAction;
    setArrowEmphasis(arrows, emphasize);
  }
}

canvas.addEventListener("pointerdown", (event) => {
  if (!actors) return;
  const rect = canvas.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, activeCamera());
  const hits = raycaster.intersectObject(actors.group, true);
  for (const hit of hits) {
    let node: THREE.Object3D | null = hit.object;
    while (node) {
      const playerId = node.userData.playerId;
      if (typeof playerId === "string") {
        dispatch({ type: "select_actor", actorId: playerId });
        return;
      }
      node = node.parent;
    }
  }
});

function tick(now: number): void {
  const dt = Math.min(48, Math.max(0, now - last));
  last = now;
  if (state.phase === "playing" && frames.length) {
    const prev = state.tMs;
    const next = prev + dt * state.speed;
    const hit = decisions.find((event) => event.available_at_ms > prev + 0.5 && event.available_at_ms <= next);
    if (hit) jump(hit);
    else if (next >= span) {
      dispatch({ type: "tick", tMs: span });
      dispatch({ type: "pause" });
    } else dispatch({ type: "tick", tMs: next });
  }
  if (state.phase === "preview") {
    if (!previewSeen) previewT = 0;
    previewSeen = true;
    previewT = Math.min(1, previewT + dt / 1800);
    if (previewT >= 1) {
      previewSeen = false;
      previewT = 0;
      dispatch({ type: "preview_done" });
    }
  } else {
    previewSeen = false;
    previewT = 0;
  }

  const sampled = frames.length ? sampleAt(state.tMs, hz, frames.length) : null;
  const frame = sampled ? frames[sampled.i0] : null;
  const nextFrame = sampled ? frames[sampled.i1] : null;
  if (actors && frame && nextFrame && sampled) applyPose(actors, frame, nextFrame, sampled.a);
  if (actors && state.actorId && state.phase !== "playing" && state.phase !== "enter") {
    const mesh = actors.meshes.get(state.actorId);
    carrierRing.visible = Boolean(mesh);
    if (mesh) carrierRing.position.set(mesh.position.x, 0.06, mesh.position.z);
  } else carrierRing.visible = false;

  ghost.visible = false;
  if (state.phase === "preview" && state.decide && state.previewAction) {
    const path = actionByClass(state.decide, state.previewAction)?.geometry?.path;
    if (path && path.length > 1) {
      const [x, y] = pointAlong(path, previewT);
      const at = toScene(x, y, 0.5);
      ghost.position.set(at.x, at.y, at.z);
      ghost.visible = true;
    }
  }
  if (state.phase === "preview") syncArrows();
  paintClock(state.tMs);
  const scrub = document.getElementById("scrub");
  if (scrub instanceof HTMLInputElement && document.activeElement !== scrub) {
    scrub.value = String(Math.round(state.tMs));
  }
  if (state.phase === "playing" || state.phase === "preview") paintDiagram(state, context());
  const shown = frame;
  statusEl.textContent = shown
    ? `${phaseName(state.phase, state.language)} · frame ${shown.frame_id} · ${hz} Hz`
    : statusEl.textContent;
  renderer.render(scene, activeCamera());
  document.documentElement.dataset.ready = actors ? "true" : "loading";
  requestAnimationFrame(tick);
}

let last = performance.now();

async function loadClip(): Promise<void> {
  const [metaRes, clipRes, eventRes] = await Promise.all([
    fetch("/sample/metadata.json"),
    fetch("/sample/clip.jsonl"),
    fetch("/sample/events.jsonl"),
  ]);
  if (!metaRes.ok || !clipRes.ok || !eventRes.ok) throw new Error("Sample clip failed to load.");
  const meta = (await metaRes.json()) as Meta;
  hz = meta.frame_hz;
  const textBody = (await clipRes.text()).trim();
  frames = textBody.split("\n").filter(Boolean).map((line) => JSON.parse(line) as Frame);
  const events = (await eventRes.text())
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as unknown);
  span = frames[frames.length - 1]?.t_ms ?? 30000;
  must<HTMLInputElement>("scrub").max = String(span);
  decisions = parseDecisionPoints(events, span);
  roster = meta.players.flatMap((player) =>
    player.team_id === "HOME" || player.team_id === "AWAY"
      ? [{ player_id: player.player_id, team_id: player.team_id, jersey_number: player.jersey_number }]
      : [],
  );
  homeName = meta.teams.find((team) => team.team_id === "HOME")?.name ?? "HOME";
  awayName = meta.teams.find((team) => team.team_id === "AWAY")?.name ?? "AWAY";
  actors = createActors(meta.players);
  for (const [playerId, mesh] of actors.meshes) mesh.userData.playerId = playerId;
  scene.add(actors.group);
}

function must<T extends HTMLElement>(id: string): T {
  const found = document.getElementById(id);
  if (!found) throw new Error(`missing #${id}`);
  return found as T;
}

bindUi();
renderFlow(state, context());
new ResizeObserver(() => resize()).observe(canvas);
resize();

void loadClip()
  .then(() => {
    bootQuery(new URLSearchParams(window.location.search));
    renderFlow(state, context());
    syncArrows();
    last = performance.now();
    requestAnimationFrame(tick);
  })
  .catch((error: unknown) => {
    statusEl.textContent = error instanceof Error ? error.message : "Could not load the sample.";
    document.documentElement.dataset.ready = "error";
  });
