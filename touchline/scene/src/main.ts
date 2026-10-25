import * as THREE from "three";
import { applyPose, createActors } from "./actors";
import { AWAY_HEX, HOME_HEX } from "./colors";
import { sampleAt, type Frame } from "./coords";
import { clipNameFromQuery, statusLine, type CameraMode } from "./hud";
import { createStage } from "./pitch";

type Meta = {
  frame_hz: number;
  players: { player_id: string; team_id: string }[];
};

function required<T extends Element>(selector: string): T {
  const found = document.querySelector<T>(selector);
  if (!found) throw new Error(`scene markup missing: ${selector}`);
  return found;
}

const canvas = required<HTMLCanvasElement>("#view");
const statusEl = required<HTMLElement>("#status");
const clipEl = required<HTMLElement>("#clip-label");
const broadcastBtn = required<HTMLButtonElement>("#cam-broadcast");
const topBtn = required<HTMLButtonElement>("#cam-top");

document.documentElement.style.setProperty("--home", HOME_HEX);
document.documentElement.style.setProperty("--away", AWAY_HEX);

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

const params = new URLSearchParams(window.location.search);
let mode: CameraMode = params.get("cam") === "top" ? "top" : "broadcast";
let paused = params.get("pause") === "1";
const requested = Number(params.get("t") ?? "0");
let tMs = Number.isFinite(requested) ? Math.max(0, requested * 1000) : 0;

function setCamera(next: CameraMode) {
  mode = next;
  broadcastBtn.setAttribute("aria-pressed", String(next === "broadcast"));
  topBtn.setAttribute("aria-pressed", String(next === "top"));
  document.documentElement.dataset.camera = next;
}

broadcastBtn.addEventListener("click", () => setCamera("broadcast"));
topBtn.addEventListener("click", () => setCamera("top"));
window.addEventListener("keydown", (event) => {
  if (event.key === "1" || event.key === "b") setCamera("broadcast");
  if (event.key === "2" || event.key === "t") setCamera("top");
  if (event.key === " ") {
    paused = !paused;
    event.preventDefault();
  }
});
setCamera(mode);

function frameTop() {
  const width = canvas.clientWidth || 1;
  const height = canvas.clientHeight || 1;
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

function resize() {
  const width = canvas.clientWidth || 1;
  const height = canvas.clientHeight || 1;
  renderer.setSize(width, height, false);
  broadcast.aspect = width / height;
  broadcast.updateProjectionMatrix();
  frameTop();
}

const resizeObserver = new ResizeObserver(() => resize());
resizeObserver.observe(canvas);
resize();

async function loadClip(name: string): Promise<{ meta: Meta; frames: Frame[] }> {
  const metaRes = await fetch("/sample/metadata.json");
  if (!metaRes.ok) throw new Error(`metadata.json HTTP ${metaRes.status}`);
  const meta = (await metaRes.json()) as Meta;
  const clipRes = await fetch(`/sample/${encodeURIComponent(name)}`);
  if (!clipRes.ok) throw new Error(`${name} HTTP ${clipRes.status}`);
  const text = (await clipRes.text()).trim();
  const frames = text.split("\n").filter(Boolean).map((line) => JSON.parse(line) as Frame);
  if (!Number.isFinite(meta.frame_hz) || meta.frame_hz < 10) throw new Error("frame_hz missing");
  if (frames.length < 2) throw new Error("Clip needs at least two frames.");
  if (frames[0]?.players.length !== 22 || frames[0].ball.length !== 6) {
    throw new Error("Clip frame is not 22 players plus a ball.");
  }
  return { meta, frames };
}

function showError(message: string) {
  statusEl.textContent = message;
  document.documentElement.dataset.ready = "error";
}

async function main() {
  let clipName: string;
  try {
    clipName = clipNameFromQuery(params.get("clip"));
  } catch (error) {
    showError(error instanceof Error ? error.message : "Bad clip name.");
    return;
  }
  let meta: Meta;
  let frames: Frame[];
  try {
    ({ meta, frames } = await loadClip(clipName));
  } catch (error) {
    showError(error instanceof Error ? error.message : "Could not load the sample.");
    return;
  }

  const actors = createActors(meta.players);
  scene.add(actors.group);
  const hz = meta.frame_hz;
  const span = Math.max(1, frames[frames.length - 1]?.t_ms ?? 1);
  tMs = Math.min(tMs, span);
  const seconds = (span / 1000).toFixed(span >= 1000 ? 0 : 1);
  clipEl.textContent = `${clipName} · ${frames.length} frames · ${seconds} s`;

  let last = performance.now();
  const tick = (now: number) => {
    const dt = now - last;
    last = now;
    if (!paused) {
      tMs += dt;
      if (tMs > span) tMs %= span;
    }
    const { i0, i1, a } = sampleAt(tMs, hz, frames.length);
    const f0 = frames[i0];
    const f1 = frames[i1];
    if (!f0 || !f1) return;
    const ballZ = applyPose(actors, f0, f1, a);
    renderer.render(scene, mode === "broadcast" ? broadcast : top);
    statusEl.textContent = statusLine({
      tMs: f0.t_ms + (f1.t_ms - f0.t_ms) * a,
      frameId: f0.frame_id,
      ballZ,
      players: actors.meshes.size,
      camera: mode,
      hz,
    });
    document.documentElement.dataset.ready = "true";
    document.documentElement.dataset.players = String(actors.meshes.size);
    document.documentElement.dataset.ballZ = ballZ.toFixed(2);
    document.documentElement.dataset.frame = String(f0.frame_id);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

void main();
