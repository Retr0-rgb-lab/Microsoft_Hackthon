import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { applyPose, createActors, type ActorSet } from "@scene/actors";
import { AWAY_HEX, HOME_HEX } from "@scene/colors";
import { PITCH, sampleAt, toScene, type Frame } from "@scene/coords";
import {
  ACTION_ORDER,
  decisionAt,
  loadDecisions,
  type ActionName,
  type DecisionSet,
  type Probabilities,
} from "@scene/decisions";
import { clipNameFromQuery, statusLine, type CameraMode } from "@scene/hud";
import { createStage } from "@scene/pitch";
import { GHOST_OPACITY, INK_OPACITY, setStrokes, type Stroke } from "./draw";
import {
  clampToPitch,
  fallbackRoute,
  GHOST_MAX_AGE_MS,
  routeForDecision,
  type Route,
  type Spot,
  type TeamId,
  type XY,
} from "./ghost";
import {
  boardDocument,
  coachCarry,
  coachPass,
  coachShot,
  commitGhost,
  formationFromFrame,
  withPassCurve,
  type Formation,
  type Ink,
  type PassInk,
  type ShotInk,
  type Slot,
} from "./ink";

const CLIP_DIR = "touchline/data/samples/sample_25hz_10min";

const ACTION_LABEL: Record<ActionName, string> = {
  pass: "Pass",
  shoot: "Shot",
  dribble: "Dribble",
  hold: "Hold",
};

const KIND_LABEL = {
  pass: "Pass",
  carry: "Carry",
  shot: "Shot",
  hold: "Hold",
} as const;

type Tool = "pass" | "carry" | "shot" | "formation";
type Draft = { tool: "pass" | "carry" | "shot"; fromId: string } | null;
type Person = Spot & { facing: number };
type TrackingFrame = Frame & {
  ball_owner_id: string | null;
  attack_dir: number;
};

type Meta = {
  frame_hz: number;
  players: { player_id: string; team_id: string; position: string }[];
  teams?: { team_id: string; formation?: string }[];
  coordinate_system?: {
    origin?: string;
    pitch_length_m?: number;
    pitch_width_m?: number;
  };
};

type GhostView = {
  action: ActionName;
  route: Route | null;
  probabilities: Probabilities | null;
  note: string | null;
  markerAt: XY | null;
};

type Hit = { kind: "player" | "ghost" | "ink"; id: string; distance: number };

function required<T extends Element>(selector: string): T {
  const found = document.querySelector<T>(selector);
  if (!found) throw new Error(`Board markup missing: ${selector}`);
  return found;
}

function isTyping(target: EventTarget | null): boolean {
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
  return target instanceof HTMLInputElement && target.type !== "range";
}

function isPassStyle(value: string): value is PassInk["style"] {
  return value === "ground" || value === "loft";
}

function isCurve(value: string): value is PassInk["curve"] {
  return value === "straight" || value === "curved";
}

function isShotStyle(value: string): value is ShotInk["style"] {
  return value === "unset" || value === "driven" || value === "placed" || value === "chip";
}

const canvas = required<HTMLCanvasElement>("#view");
const statusEl = required<HTMLElement>("#status");
const clipEl = required<HTMLElement>("#clip-label");
const broadcastBtn = required<HTMLButtonElement>("#cam-broadcast");
const topBtn = required<HTMLButtonElement>("#cam-top");
const playBtn = required<HTMLButtonElement>("#play");
const scrub = required<HTMLInputElement>("#scrub");
const fillBtn = required<HTMLButtonElement>("#fill-formation");
const downloadBtn = required<HTMLButtonElement>("#download");
const labelInput = required<HTMLInputElement>("#formation-label");
const ghostPanel = required<HTMLElement>("#ghost-panel");
const ghostSource = required<HTMLElement>("#ghost-source");
const ghostTitle = required<HTMLElement>("#ghost-title");
const ghostBars = required<HTMLElement>("#ghost-bars");
const ghostNote = required<HTMLElement>("#ghost-note");
const ghostFoot = required<HTMLElement>("#ghost-foot");
const inkEdit = required<HTMLElement>("#ink-edit");
const inkTitle = required<HTMLElement>("#ink-edit-title");
const passFields = required<HTMLElement>("#pass-fields");
const shotFields = required<HTMLElement>("#shot-fields");
const passStyle = required<HTMLSelectElement>("#pass-style");
const passCurve = required<HTMLSelectElement>("#pass-curve");
const shotStyle = required<HTMLSelectElement>("#shot-style");
const inkDelete = required<HTMLButtonElement>("#ink-delete");
const toolButtons = [...document.querySelectorAll<HTMLButtonElement>(".tools button[data-tool]")];

document.documentElement.style.setProperty("--home", HOME_HEX);
document.documentElement.style.setProperty("--away", AWAY_HEX);

const barRows = new Map<ActionName, { row: HTMLLIElement; fill: HTMLElement; value: HTMLElement }>();
for (const action of ACTION_ORDER) {
  const row = document.createElement("li");
  row.className = "bar-row";
  const label = document.createElement("span");
  label.textContent = ACTION_LABEL[action];
  const track = document.createElement("span");
  track.className = "bar-track";
  const fill = document.createElement("span");
  fill.className = "bar-fill";
  track.append(fill);
  const value = document.createElement("span");
  value.className = "bar-value";
  row.append(label, track, value);
  ghostBars.append(row);
  barRows.set(action, { row, fill, value });
}

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
createStage(scene, renderer);

const broadcast = new THREE.PerspectiveCamera(28, 1, 0.1, 500);
broadcast.position.set(-6, 9.5, 46);
broadcast.lookAt(14, 1.2, 0);

const top = new THREE.OrthographicCamera(-60, 60, 40, -40, 0.1, 400);
top.position.set(0, 150, 0);
top.up.set(0, 0, -1);
top.lookAt(0, 0, 0);

const controls = new OrbitControls(broadcast, canvas);
controls.enableDamping = false;
controls.enablePan = false;
controls.minDistance = 12;
controls.maxDistance = 180;
controls.minPolarAngle = 0.15;
controls.maxPolarAngle = Math.PI / 2 - 0.08;
controls.enabled = false;

function resetBroadcast() {
  broadcast.position.set(-6, 9.5, 46);
  broadcast.up.set(0, 1, 0);
  broadcast.lookAt(14, 1.2, 0);
}

resetBroadcast();

const inkGroup = new THREE.Group();
const ghostGroup = new THREE.Group();
scene.add(inkGroup, ghostGroup);

const draftRing = new THREE.Mesh(
  new THREE.RingGeometry(0.75, 1.05, 40),
  new THREE.MeshBasicMaterial({ color: 0xffe500, transparent: true, opacity: 0.9, side: THREE.DoubleSide }),
);
draftRing.rotation.x = -Math.PI / 2;
draftRing.visible = false;
scene.add(draftRing);

const ground = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
const groundHit = new THREE.Vector3();
const pointer = new THREE.Vector2();
const raycaster = new THREE.Raycaster();

function frameTop() {
  const width = canvas.clientWidth || 1;
  const height = canvas.clientHeight || 1;
  const aspect = width / height;
  const pad = 1.12;
  let halfH = (PITCH.width / 2) * pad;
  let halfW = halfH * aspect;
  if (halfW < (PITCH.length / 2) * pad) {
    halfW = (PITCH.length / 2) * pad;
    halfH = halfW / aspect;
  }
  top.left = -halfW;
  top.right = halfW;
  top.top = halfH;
  top.bottom = -halfH;
  top.updateProjectionMatrix();
}

function resize() {
  const width = canvas.clientWidth || 1;
  const height = canvas.clientHeight || 1;
  renderer.setSize(width, height, false);
  broadcast.aspect = width / height;
  broadcast.updateProjectionMatrix();
  frameTop();
}

new ResizeObserver(() => resize()).observe(canvas);
resize();

function showError(message: string) {
  statusEl.textContent = message;
  document.documentElement.dataset.ready = "error";
}

function renderPanel(ghost: GhostView | null) {
  if (!ghost) {
    ghostPanel.hidden = true;
    return;
  }
  ghostPanel.hidden = false;
  ghostTitle.textContent = `Suggestion · ${ACTION_LABEL[ghost.action]}`;
  const modeled = ghost.probabilities !== null;
  ghostBars.hidden = !modeled;
  ghostFoot.hidden = !modeled;
  ghostSource.textContent = modeled ? "Uncalibrated · checked-in decision" : "Geometric fallback";
  ghostNote.textContent = ghost.note ?? "";
  if (!ghost.probabilities) return;
  for (const action of ACTION_ORDER) {
    const row = barRows.get(action);
    if (!row) continue;
    const share = ghost.probabilities[action];
    row.fill.style.width = `${Math.max(0, Math.min(100, share * 100))}%`;
    row.value.textContent = `${(share * 100).toFixed(1)}%`;
    row.row.classList.toggle("top", action === ghost.action);
  }
}

function tagActors(actors: ActorSet) {
  for (const [id, mesh] of actors.meshes) mesh.userData.playerId = id;
}

async function main() {
  const params = new URLSearchParams(window.location.search);
  let clipName: string;
  try {
    clipName = clipNameFromQuery(params.get("clip"));
  } catch (error) {
    showError(error instanceof Error ? error.message : "Invalid clip name.");
    return;
  }

  let meta: Meta;
  let frames: TrackingFrame[];
  let decisionSet: DecisionSet | null;
  try {
    [meta, frames, decisionSet] = await Promise.all([
      fetch("/sample/metadata.json").then(async (res) => {
        if (!res.ok) throw new Error(`metadata.json HTTP ${res.status}`);
        return (await res.json()) as Meta;
      }),
      fetch(`/sample/${encodeURIComponent(clipName)}`).then(async (res) => {
        if (!res.ok) throw new Error(`${clipName} HTTP ${res.status}`);
        const text = (await res.text()).trim();
        return text.split("\n").filter(Boolean).map((line) => JSON.parse(line) as TrackingFrame);
      }),
      loadDecisions("/decisions.json").catch((error: unknown) => {
        console.warn("checked-in decisions unavailable", error);
        return null;
      }),
    ]);
  } catch (error) {
    showError(error instanceof Error ? error.message : "The sample could not be read.");
    return;
  }

  const coords = meta.coordinate_system;
  if (!coords || coords.origin !== "centre_spot" || coords.pitch_length_m !== 105 || coords.pitch_width_m !== 68) {
    showError("The sample must start from the centre spot on a 105 × 68 m pitch.");
    return;
  }
  if (!Number.isFinite(meta.frame_hz) || meta.frame_hz < 10) {
    showError("frame_hz is missing.");
    return;
  }
  const first = frames[0];
  const endFrame = frames[frames.length - 1];
  if (!first || !endFrame || first.players.length !== 22 || first.ball.length !== 6) {
    showError("The clip needs 22 players and one ball.");
    return;
  }

  const teams = new Map<string, TeamId>();
  for (const player of meta.players) {
    if (player.team_id === "HOME" || player.team_id === "AWAY") teams.set(player.player_id, player.team_id);
  }

  const hz = meta.frame_hz;
  const span = Math.max(1, endFrame.t_ms);
  const requested = Number(params.get("t") ?? "0");
  let tMs = Number.isFinite(requested) ? Math.min(span, Math.max(0, requested * 1000)) : 0;
  let paused = params.get("pause") === "1";
  let mode: CameraMode = params.get("cam") === "top" ? "top" : "broadcast";
  let tool: Tool = "pass";
  let draft: Draft = null;
  let dragId: string | null = null;
  let scrubbing = false;
  let suppressedT: number | null = null;
  let selectedId: string | null = null;
  let inkCounter = 0;
  let fillingEditor = false;
  let formationOn = false;
  let orbitOn = false;
  let ghostStamp = "";
  let inkStamp = "";
  const inks: Ink[] = [];
  const history: Ink[][] = [];

  const home = meta.teams?.find((team) => team.team_id === "HOME");
  if (home?.formation) labelInput.value = home.formation;

  function peopleOf(frame: TrackingFrame): Person[] {
    const list: Person[] = [];
    for (const row of frame.players) {
      const teamId = teams.get(row[0]);
      if (!teamId) continue;
      list.push({ id: row[0], teamId, x: row[1], y: row[2], facing: row[5] });
    }
    return list;
  }

  function frameAt(t: number): TrackingFrame {
    const index = Math.max(0, Math.min(frames.length - 1, Math.round((t * hz) / 1000)));
    const frame = frames[index];
    if (!frame) throw new Error("Frame missing.");
    return frame;
  }

  let opened: { attack_dir: 1 | -1; slots: Slot[] };
  try {
    opened = formationFromFrame(peopleOf(first), meta.players, first.attack_dir);
  } catch (error) {
    showError(error instanceof Error ? error.message : "The formation cannot be filled from this frame.");
    return;
  }
  let slots = opened.slots;
  let formationAttack: 1 | -1 = opened.attack_dir;

  let clipActors: ActorSet;
  let formationActors: ActorSet;
  try {
    clipActors = createActors(meta.players);
    formationActors = createActors(meta.players);
  } catch (error) {
    showError(error instanceof Error ? error.message : "Cannot place 22 players.");
    return;
  }
  tagActors(clipActors);
  tagActors(formationActors);
  formationActors.ball.visible = false;
  formationActors.marker.visible = false;
  formationActors.group.visible = false;
  scene.add(clipActors.group, formationActors.group);

  const seconds = (span / 1000).toFixed(span >= 1000 ? 0 : 1);
  clipEl.textContent = decisionSet
    ? `${clipName} · ${frames.length} frames · ${seconds} s · ${decisionSet.decision_count} checked-in decisions · uncalibrated`
    : `${clipName} · ${frames.length} frames · ${seconds} s · checked-in decisions unavailable`;
  scrub.max = String(span);
  scrub.value = String(tMs);

  function formationActive() {
    return tool === "formation" && paused;
  }

  function placeFormation() {
    for (const slot of slots) {
      const mesh = formationActors.meshes.get(slot.player_id);
      if (!mesh) continue;
      const at = toScene(slot.x, slot.y, 0);
      mesh.position.set(at.x, at.y, at.z);
      mesh.rotation.y = slot.facing;
    }
  }

  function syncPresentation() {
    const formation = formationActive();
    if (formationOn && !formation) resetBroadcast();
    formationOn = formation;
    formationActors.group.visible = formation;
    for (const mesh of clipActors.meshes.values()) mesh.visible = !formation;
    const wantOrbit = formation && mode === "broadcast" && dragId === null;
    if (wantOrbit && !orbitOn) {
      controls.target.set(0, 0, 0);
      controls.enabled = true;
      controls.update();
      orbitOn = true;
    } else if (!wantOrbit && orbitOn) {
      controls.enabled = false;
      orbitOn = false;
    }
    for (const button of toolButtons) {
      button.setAttribute("aria-pressed", String(button.dataset.tool === tool));
    }
    broadcastBtn.setAttribute("aria-pressed", String(mode === "broadcast"));
    topBtn.setAttribute("aria-pressed", String(mode === "top"));
    document.documentElement.dataset.camera = mode;
    playBtn.textContent = paused ? "Play" : "Pause";
  }

  function setCamera(next: CameraMode) {
    mode = next;
    syncPresentation();
  }

  function setTool(next: Tool) {
    tool = next;
    if (draft && draft.tool !== next) draft = null;
    syncPresentation();
  }

  function ownerOf(frame: TrackingFrame, people: Person[]): Person | null {
    const id = frame.ball_owner_id;
    if (typeof id !== "string" || id.length === 0) return null;
    return people.find((person) => person.id === id) ?? null;
  }

  function buildGhost(frame: TrackingFrame): GhostView | null {
    if (!paused || formationActive()) return null;
    if (suppressedT !== null && Math.abs(suppressedT - tMs) <= 0.5) return null;
    const people = peopleOf(frame);
    const owner = ownerOf(frame, people);
    if (!owner) return null;
    const spots = people.map(({ id, teamId, x, y }) => ({ id, teamId, x, y }));
    const ball: XY = [frame.ball[0], frame.ball[1]];
    const attackDir = frame.attack_dir < 0 ? -1 : 1;
    const decision = decisionSet ? decisionAt(decisionSet, tMs, GHOST_MAX_AGE_MS) : null;
    if (decision) {
      const routed = routeForDecision({ decision, owner, spots, ball, attackDir });
      return {
        action: routed.action,
        route: routed.route,
        probabilities: decision.probabilities,
        note: routed.route?.score != null ? `Completion score ${routed.route.score.toFixed(4)}` : null,
        markerAt: routed.action === "hold" ? [owner.x, owner.y] : null,
      };
    }
    const routed = fallbackRoute({ owner, spots, ball, attackDir });
    return {
      action: routed.action,
      route: routed.route,
      probabilities: null,
      note:
        routed.action === "pass"
          ? "No checked-in decision for this frame. The route is the nearest offside-free teammate."
          : "No checked-in decision for this frame. Six metres along the attacking direction.",
      markerAt: null,
    };
  }

  function ghostStrokes(ghost: GhostView | null): Stroke[] {
    if (!ghost) return [];
    if (ghost.action === "hold" && ghost.markerAt) {
      return [{ key: "ghost", kind: "hold", path: null, at: ghost.markerAt, opacity: GHOST_OPACITY, height: 0.1, ghost: true }];
    }
    if (!ghost.route) return [];
    return [{
      key: "ghost",
      kind: ghost.route.kind,
      path: ghost.route.path,
      at: null,
      opacity: GHOST_OPACITY,
      height: 0.1,
      ghost: true,
    }];
  }

  function paintGhost(ghost: GhostView | null) {
    const stamp = JSON.stringify(ghostStrokes(ghost));
    if (stamp === ghostStamp) return;
    ghostStamp = stamp;
    setStrokes(ghostGroup, ghostStrokes(ghost));
  }

  function inkStrokes(): Stroke[] {
    return inks.map((ink) => {
      const selected = ink.ink_id === selectedId;
      if (ink.kind === "hold") {
        return {
          key: ink.ink_id,
          kind: "hold",
          path: null,
          at: ink.at,
          opacity: selected ? 1 : INK_OPACITY,
          height: 0.08,
          ghost: false,
        };
      }
      return {
        key: ink.ink_id,
        kind: ink.kind,
        path: ink.path,
        at: null,
        opacity: selected ? 1 : INK_OPACITY,
        height: ink.kind === "pass" && ink.style === "loft" ? 0.9 : 0.08,
        ghost: false,
      };
    });
  }

  function paintInk() {
    const stamp = JSON.stringify(inkStrokes());
    if (stamp === inkStamp) return;
    inkStamp = stamp;
    setStrokes(inkGroup, inkStrokes());
  }

  function showEditor() {
    const ink = inks.find((item) => item.ink_id === selectedId) ?? null;
    fillingEditor = true;
    if (!ink) {
      inkEdit.hidden = true;
      fillingEditor = false;
      return;
    }
    inkEdit.hidden = false;
    inkTitle.textContent = KIND_LABEL[ink.kind];
    passFields.hidden = ink.kind !== "pass";
    shotFields.hidden = ink.kind !== "shot";
    if (ink.kind === "pass") {
      passStyle.value = ink.style;
      passCurve.value = ink.curve;
    }
    if (ink.kind === "shot") shotStyle.value = ink.style;
    fillingEditor = false;
  }

  function pushHistory() {
    history.push(structuredClone(inks));
    if (history.length > 50) history.shift();
  }

  function nextInkId() {
    inkCounter += 1;
    return `ink-${inkCounter}`;
  }

  function acceptGhost() {
    const frame = frameAt(tMs);
    const ghost = buildGhost(frame);
    const owner = ownerOf(frame, peopleOf(frame));
    if (!ghost || !owner) return;
    const ink = commitGhost({
      action: ghost.action,
      route: ghost.route,
      owner: { id: owner.id, teamId: owner.teamId, x: owner.x, y: owner.y },
      frameId: frame.frame_id,
      tMs: frame.t_ms,
      inkId: nextInkId(),
    });
    if (!ink) return;
    pushHistory();
    inks.push(ink);
    selectedId = ink.ink_id;
    suppressedT = tMs;
    draft = null;
    paintInk();
    showEditor();
  }

  function deleteSelected() {
    if (!selectedId) return;
    const index = inks.findIndex((ink) => ink.ink_id === selectedId);
    if (index < 0) return;
    pushHistory();
    inks.splice(index, 1);
    selectedId = null;
    paintInk();
    showEditor();
  }

  function undo() {
    const prev = history.pop();
    if (!prev) return;
    inks.splice(0, inks.length, ...prev);
    if (selectedId && !inks.some((ink) => ink.ink_id === selectedId)) selectedId = null;
    paintInk();
    showEditor();
  }

  function personById(frame: TrackingFrame, id: string): Person | null {
    return peopleOf(frame).find((person) => person.id === id) ?? null;
  }

  function onPlayer(id: string) {
    const frame = frameAt(tMs);
    const person = personById(frame, id);
    if (!person || tool === "formation") return;
    if (tool === "pass") {
      if (!draft || draft.tool !== "pass") {
        draft = { tool: "pass", fromId: id };
        return;
      }
      if (draft.fromId === id) return;
      const from = personById(frame, draft.fromId);
      if (!from) {
        draft = null;
        return;
      }
      pushHistory();
      const ink = coachPass({ inkId: nextInkId(), frameId: frame.frame_id, tMs: frame.t_ms, from, to: person });
      inks.push(ink);
      selectedId = ink.ink_id;
      draft = null;
      paintInk();
      showEditor();
      return;
    }
    draft = { tool, fromId: id };
  }

  function onGround(point: XY) {
    if (!draft || (draft.tool !== "carry" && draft.tool !== "shot")) return;
    const frame = frameAt(tMs);
    const from = personById(frame, draft.fromId);
    if (!from) {
      draft = null;
      return;
    }
    if (Math.hypot(point[0] - from.x, point[1] - from.y) < 0.4) return;
    pushHistory();
    const ink =
      draft.tool === "carry"
        ? coachCarry({ inkId: nextInkId(), frameId: frame.frame_id, tMs: frame.t_ms, from, end: point })
        : coachShot({ inkId: nextInkId(), frameId: frame.frame_id, tMs: frame.t_ms, from, end: point });
    inks.push(ink);
    selectedId = ink.ink_id;
    draft = null;
    paintInk();
    showEditor();
  }

  function activeCamera() {
    return mode === "broadcast" ? broadcast : top;
  }

  function rayFrom(event: PointerEvent) {
    const rect = canvas.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / Math.max(rect.width, 1)) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / Math.max(rect.height, 1)) * 2 + 1;
    raycaster.setFromCamera(pointer, activeCamera());
    return raycaster;
  }

  function pickPlayer(root: THREE.Object3D): { id: string; distance: number } | null {
    for (const hit of raycaster.intersectObject(root, true)) {
      let obj: THREE.Object3D | null = hit.object;
      while (obj) {
        const id = obj.userData.playerId;
        if (typeof id === "string") return { id, distance: hit.distance };
        obj = obj.parent;
      }
    }
    return null;
  }

  function closestHit(): Hit | null {
    const hits: Hit[] = [];
    const player = pickPlayer(formationActive() ? formationActors.group : clipActors.group);
    if (player) hits.push({ kind: "player", id: player.id, distance: player.distance });
    for (const hit of raycaster.intersectObject(ghostGroup, true)) {
      if (hit.object.userData.stroke === "ghost") {
        hits.push({ kind: "ghost", id: "", distance: hit.distance });
        break;
      }
    }
    for (const hit of raycaster.intersectObject(inkGroup, true)) {
      if (hit.object.userData.stroke === "ink") {
        hits.push({ kind: "ink", id: String(hit.object.userData.inkId), distance: hit.distance });
        break;
      }
    }
    hits.sort((a, b) => a.distance - b.distance);
    return hits[0] ?? null;
  }

  function groundPoint(): XY | null {
    const hit = raycaster.ray.intersectPlane(ground, groundHit);
    if (!hit) return null;
    const x = hit.x;
    const y = -hit.z;
    if (Math.abs(x) > PITCH.halfLength + 8 || Math.abs(y) > PITCH.halfWidth + 8) return null;
    return clampToPitch(x, y);
  }

  function onPointerDown(event: PointerEvent) {
    if (event.button !== 0 || !paused) return;
    rayFrom(event);
    const hit = closestHit();
    if (hit?.kind === "player" && formationActive()) {
      dragId = hit.id;
      canvas.setPointerCapture(event.pointerId);
      syncPresentation();
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    if (hit?.kind === "ghost") {
      acceptGhost();
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    if (hit?.kind === "ink") {
      selectedId = hit.id;
      paintInk();
      showEditor();
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    if (hit?.kind === "player") {
      if ((tool === "carry" || tool === "shot") && draft && draft.fromId !== hit.id) {
        const person = personById(frameAt(tMs), hit.id);
        if (person) onGround([person.x, person.y]);
      } else {
        onPlayer(hit.id);
      }
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    const point = groundPoint();
    if (point && (tool === "carry" || tool === "shot") && draft) {
      onGround(point);
      event.preventDefault();
      event.stopPropagation();
    }
  }

  function onPointerMove(event: PointerEvent) {
    if (!dragId) return;
    rayFrom(event);
    const point = groundPoint();
    if (!point) return;
    const slot = slots.find((item) => item.player_id === dragId);
    if (!slot) return;
    slot.x = point[0];
    slot.y = point[1];
    placeFormation();
  }

  function onPointerUp() {
    if (!dragId) return;
    dragId = null;
    syncPresentation();
  }

  function replaceSelected(next: Ink) {
    const index = inks.findIndex((ink) => ink.ink_id === selectedId);
    if (index < 0) return;
    pushHistory();
    inks[index] = next;
    paintInk();
  }

  canvas.addEventListener("pointerdown", onPointerDown, true);
  canvas.addEventListener("pointermove", onPointerMove);
  canvas.addEventListener("pointerup", onPointerUp);
  canvas.addEventListener("pointercancel", onPointerUp);

  for (const button of toolButtons) {
    button.addEventListener("click", () => {
      const next = button.dataset.tool;
      if (next === "pass" || next === "carry" || next === "shot" || next === "formation") setTool(next);
    });
  }
  broadcastBtn.addEventListener("click", () => setCamera("broadcast"));
  topBtn.addEventListener("click", () => setCamera("top"));
  playBtn.addEventListener("click", () => {
    paused = !paused;
    if (!paused) draft = null;
    syncPresentation();
  });
  scrub.addEventListener("pointerdown", () => {
    scrubbing = true;
  });
  window.addEventListener("pointerup", () => {
    scrubbing = false;
  });
  scrub.addEventListener("input", () => {
    tMs = Number(scrub.value);
    if (!paused) {
      paused = true;
      draft = null;
    }
    syncPresentation();
  });
  fillBtn.addEventListener("click", () => {
    const frame = frameAt(tMs);
    try {
      const filled = formationFromFrame(peopleOf(frame), meta.players, frame.attack_dir);
      slots = filled.slots;
      formationAttack = filled.attack_dir;
      placeFormation();
    } catch (error) {
      statusEl.textContent = error instanceof Error ? error.message : "The formation could not be filled.";
    }
  });
  downloadBtn.addEventListener("click", () => {
    const formation: Formation = {
      label: labelInput.value.trim() || "4-3-3",
      attack_dir: formationAttack,
      slots,
    };
    const file = boardDocument({ clipDir: CLIP_DIR, camera: mode, formation, ink: inks });
    const blob = new Blob([JSON.stringify(file, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "board.json";
    link.click();
    URL.revokeObjectURL(url);
  });
  inkDelete.addEventListener("click", deleteSelected);
  passStyle.addEventListener("change", () => {
    if (fillingEditor) return;
    const ink = inks.find((item) => item.ink_id === selectedId);
    if (!ink || ink.kind !== "pass" || !isPassStyle(passStyle.value) || ink.style === passStyle.value) return;
    replaceSelected({ ...ink, style: passStyle.value });
  });
  passCurve.addEventListener("change", () => {
    if (fillingEditor) return;
    const ink = inks.find((item) => item.ink_id === selectedId);
    if (!ink || ink.kind !== "pass" || !isCurve(passCurve.value) || ink.curve === passCurve.value) return;
    replaceSelected(withPassCurve(ink, passCurve.value));
  });
  shotStyle.addEventListener("change", () => {
    if (fillingEditor) return;
    const ink = inks.find((item) => item.ink_id === selectedId);
    if (!ink || ink.kind !== "shot" || !isShotStyle(shotStyle.value) || ink.style === shotStyle.value) return;
    replaceSelected({ ...ink, style: shotStyle.value });
  });

  window.addEventListener("keydown", (event) => {
    if (event.repeat) return;
    const typing = isTyping(event.target);
    if (event.key === " " && !typing) {
      event.preventDefault();
      paused = !paused;
      if (!paused) draft = null;
      syncPresentation();
      return;
    }
    if (typing) return;
    if (event.key === "1" || event.key === "b" || event.key === "B") setCamera("broadcast");
    if (event.key === "2" || event.key === "t" || event.key === "T") setCamera("top");
    if (event.key === "Tab") {
      event.preventDefault();
      acceptGhost();
    }
    if (event.key === "Escape") {
      suppressedT = tMs;
      draft = null;
    }
    if ((event.key === "Delete" || event.key === "Backspace") && selectedId) {
      event.preventDefault();
      deleteSelected();
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z" && !event.shiftKey) {
      event.preventDefault();
      undo();
    }
  });

  setCamera(mode);
  placeFormation();

  const ringMaterial = draftRing.material as THREE.MeshBasicMaterial;
  let previous = performance.now();
  const tick = (now: number) => {
    const dt = now - previous;
    previous = now;
    if (!paused && !scrubbing) {
      tMs += dt;
      if (tMs >= span) {
        tMs = span;
        paused = true;
      }
    }
    if (suppressedT !== null && Math.abs(suppressedT - tMs) > 0.5) suppressedT = null;

    const discrete = frameAt(tMs);
    let ballZ = discrete.ball[2];
    let shownT = discrete.t_ms;
    let shownFrame = discrete.frame_id;
    if (paused) {
      ballZ = applyPose(clipActors, discrete, discrete, 0);
    } else {
      const { i0, i1, a } = sampleAt(tMs, hz, frames.length);
      const f0 = frames[i0];
      const f1 = frames[i1];
      if (f0 && f1) {
        ballZ = applyPose(clipActors, f0, f1, a);
        shownT = f0.t_ms + (f1.t_ms - f0.t_ms) * a;
        shownFrame = f0.frame_id;
      }
    }
    placeFormation();
    syncPresentation();

    const ghost = buildGhost(discrete);
    paintGhost(ghost);
    renderPanel(ghost);
    paintInk();

    const draftPerson = draft && paused && !formationActive() ? personById(discrete, draft.fromId) : null;
    if (draftPerson && draft) {
      const at = toScene(draftPerson.x, draftPerson.y, 0.08);
      draftRing.position.set(at.x, at.y, at.z);
      draftRing.visible = true;
      const color = draft.tool === "carry" ? 0x3ad6ff : draft.tool === "shot" ? 0xff8a3d : 0xffe500;
      ringMaterial.color.setHex(color);
    } else {
      draftRing.visible = false;
    }

    renderer.render(scene, activeCamera());
    if (!scrubbing) scrub.value = String(Math.round(Math.min(span, Math.max(0, tMs))));
    statusEl.textContent = statusLine({
      tMs: shownT,
      frameId: shownFrame,
      ballZ,
      players: clipActors.meshes.size,
      camera: mode,
      hz,
    });
    document.documentElement.dataset.ready = "true";
    document.documentElement.dataset.paused = String(paused);
    document.documentElement.dataset.players = String(clipActors.meshes.size);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

void main();
