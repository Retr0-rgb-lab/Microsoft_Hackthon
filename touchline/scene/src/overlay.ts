import * as THREE from "three";
import type { Decision, DecisionPath } from "./decisions";

export const OVERLAY_COLORS = {
  pass: 0xffe500,
  carry: 0x3ad6ff,
  ring: 0xffffff,
} as const;

const HEIGHT = 0.06;
const PASS_HALF_WIDTH = 0.42;
const CARRY_HALF_WIDTH = 0.3;
const DASH_ON = 1.7;
const DASH_OFF = 1.0;
const ARROW_LENGTH = 1.5;
const ARROW_HALF_WIDTH = 0.85;

type XY = [number, number];

export type Overlay = {
  group: THREE.Group;
  show(decision: Decision | null): void;
  readonly visibleDecisionId: string | null;
};

/** Data metres (x along length, y along width) → three.js (x, up, -y). */
function toScenePoint(x: number, y: number, height: number): [number, number, number] {
  return [x, height, -y];
}

/** Split a polyline into drawn and skipped runs. */
function dashSegments(points: XY[], on: number, off: number): XY[][] {
  const runs: XY[][] = [];
  let drawing = true;
  let remaining = on;
  let current: XY[] = [];
  for (let i = 0; i < points.length - 1; i += 1) {
    let [ax, ay] = points[i];
    const [bx, by] = points[i + 1];
    const total = Math.hypot(bx - ax, by - ay);
    if (total < 1e-6) continue;
    const ux = (bx - ax) / total;
    const uy = (by - ay) / total;
    let left = total;
    while (left > 1e-6) {
      const step = Math.min(left, remaining);
      const nx = ax + ux * step;
      const ny = ay + uy * step;
      if (drawing) {
        if (current.length === 0) current.push([ax, ay]);
        current.push([nx, ny]);
      }
      ax = nx;
      ay = ny;
      left -= step;
      remaining -= step;
      if (remaining <= 1e-6) {
        if (drawing && current.length > 1) runs.push(current);
        current = [];
        drawing = !drawing;
        remaining = drawing ? on : off;
      }
    }
  }
  if (drawing && current.length > 1) runs.push(current);
  return runs;
}

/** A flat ribbon on the ground, so it reads as chalk from both cameras. */
function ribbonGeometry(runs: XY[][], halfWidth: number, height: number): THREE.BufferGeometry {
  const positions: number[] = [];
  for (const run of runs) {
    for (let i = 0; i < run.length - 1; i += 1) {
      const [ax, ay] = run[i];
      const [bx, by] = run[i + 1];
      const dx = bx - ax;
      const dy = by - ay;
      const len = Math.hypot(dx, dy);
      if (len < 1e-6) continue;
      const nx = (-dy / len) * halfWidth;
      const ny = (dx / len) * halfWidth;
      const a = toScenePoint(ax + nx, ay + ny, height);
      const b = toScenePoint(ax - nx, ay - ny, height);
      const c = toScenePoint(bx + nx, by + ny, height);
      const d = toScenePoint(bx - nx, by - ny, height);
      positions.push(...a, ...b, ...c, ...b, ...d, ...c);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.computeVertexNormals();
  return geometry;
}

/** A flat triangle pointing along the last segment of a path. */
function arrowGeometry(points: XY[], height: number): THREE.BufferGeometry {
  if (points.length < 2) return new THREE.BufferGeometry();
  const [bx, by] = points[points.length - 1];
  const [ax, ay] = points[points.length - 2];
  const dx = bx - ax;
  const dy = by - ay;
  const len = Math.hypot(dx, dy);
  if (len < 1e-6) return new THREE.BufferGeometry();
  const ux = dx / len;
  const uy = dy / len;
  const tipX = bx + ux * ARROW_LENGTH;
  const tipY = by + uy * ARROW_LENGTH;
  const backX = bx - ux * ARROW_LENGTH * 0.25;
  const backY = by - uy * ARROW_LENGTH * 0.25;
  const nx = -uy * ARROW_HALF_WIDTH;
  const ny = ux * ARROW_HALF_WIDTH;
  const positions = [
    ...toScenePoint(tipX, tipY, height),
    ...toScenePoint(backX + nx, backY + ny, height),
    ...toScenePoint(backX - nx, backY - ny, height),
  ];
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.computeVertexNormals();
  return geometry;
}

function ringGeometry(x: number, y: number, height: number, inner: number, outer: number): THREE.BufferGeometry {
  const geometry = new THREE.RingGeometry(inner, outer, 40);
  geometry.rotateX(-Math.PI / 2);
  const [sx, sy, sz] = toScenePoint(x, y, height);
  geometry.translate(sx, sy, sz);
  return geometry;
}

function ribbonMaterial(color: number, opacity: number): THREE.MeshBasicMaterial {
  return new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity,
    depthWrite: false,
    side: THREE.DoubleSide,
    polygonOffset: true,
    polygonOffsetFactor: -6,
    polygonOffsetUnits: -6,
  });
}

function addPath(
  parent: THREE.Group,
  path: DecisionPath,
  color: number,
  opacity: number,
  halfWidth: number,
  dashed: boolean,
): void {
  const points = path.path;
  if (!Array.isArray(points) || points.length < 2) return;
  const runs = dashed ? dashSegments(points, DASH_ON, DASH_OFF) : [points];
  if (runs.length === 0) return;
  const mesh = new THREE.Mesh(ribbonGeometry(runs, halfWidth, HEIGHT), ribbonMaterial(color, opacity));
  mesh.renderOrder = 5;
  parent.add(mesh);

  if (!dashed) {
    const head = new THREE.Mesh(arrowGeometry(points, HEIGHT + 0.01), ribbonMaterial(color, opacity));
    head.renderOrder = 6;
    parent.add(head);
  }
}

export function createOverlay(): Overlay {
  const group = new THREE.Group();
  group.renderOrder = 4;
  let shown: string | null = null;

  function clear(): void {
    for (const child of [...group.children]) {
      group.remove(child);
      const mesh = child as THREE.Mesh;
      mesh.geometry?.dispose?.();
      const material = mesh.material as THREE.Material | THREE.Material[] | undefined;
      if (Array.isArray(material)) material.forEach((m) => m.dispose());
      else material?.dispose?.();
    }
  }

  function show(decision: Decision | null): void {
    const id = decision?.event_id ?? null;
    if (id === shown) return;
    shown = id;
    clear();
    if (!decision) return;

    if (decision.primary_pass) {
      addPath(group, decision.primary_pass, OVERLAY_COLORS.pass, 0.95, PASS_HALF_WIDTH, false);
    }
    if (decision.secondary_pass) {
      addPath(group, decision.secondary_pass, OVERLAY_COLORS.pass, 0.38, PASS_HALF_WIDTH, false);
    }
    if (decision.carry) {
      addPath(group, decision.carry, OVERLAY_COLORS.carry, 0.85, CARRY_HALF_WIDTH, true);
    }

    const origin = decision.primary_pass?.path[0] ?? decision.carry?.path[0];
    if (origin) {
      const ring = new THREE.Mesh(
        ringGeometry(origin[0], origin[1], HEIGHT + 0.01, 0.55, 0.85),
        ribbonMaterial(OVERLAY_COLORS.ring, 0.8),
      );
      ring.renderOrder = 7;
      group.add(ring);
    }
  }

  return {
    group,
    show,
    get visibleDecisionId() {
      return shown;
    },
  };
}
