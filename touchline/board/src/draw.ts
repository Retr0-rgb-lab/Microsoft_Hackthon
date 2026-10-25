import * as THREE from "three";
import { toScene } from "@scene/coords";
import type { XY } from "./ghost";

export const GHOST_OPACITY = 0.35;
export const INK_OPACITY = 0.95;

const COLOR = {
  pass: 0xffe500,
  carry: 0x3ad6ff,
  shot: 0xff8a3d,
  hold: 0xf4f1e8,
} as const;

export type Stroke = {
  key: string;
  kind: "pass" | "carry" | "shot" | "hold";
  path: XY[] | null;
  at: XY | null;
  opacity: number;
  height: number;
  ghost: boolean;
};

function scenePoint(x: number, y: number, height: number): [number, number, number] {
  const point = toScene(x, y, height);
  return [point.x, point.y, point.z];
}

function ribbonGeometry(points: XY[], halfWidth: number, height: number): THREE.BufferGeometry | null {
  const positions: number[] = [];
  for (let i = 0; i < points.length - 1; i += 1) {
    const [ax, ay] = points[i]!;
    const [bx, by] = points[i + 1]!;
    const dx = bx - ax;
    const dy = by - ay;
    const len = Math.hypot(dx, dy);
    if (len < 1e-4) continue;
    const nx = (-dy / len) * halfWidth;
    const ny = (dx / len) * halfWidth;
    const a = scenePoint(ax + nx, ay + ny, height);
    const b = scenePoint(ax - nx, ay - ny, height);
    const c = scenePoint(bx + nx, by + ny, height);
    const d = scenePoint(bx - nx, by - ny, height);
    positions.push(...a, ...b, ...c, ...b, ...d, ...c);
  }
  if (positions.length === 0) return null;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return geometry;
}

function arrowGeometry(points: XY[], height: number): THREE.BufferGeometry | null {
  if (points.length < 2) return null;
  const [bx, by] = points[points.length - 1]!;
  const [ax, ay] = points[points.length - 2]!;
  const dx = bx - ax;
  const dy = by - ay;
  const len = Math.hypot(dx, dy);
  if (len < 0.4) return null;
  const head = Math.min(1.7, len * 0.45);
  const ux = dx / len;
  const uy = dy / len;
  const backX = bx - ux * head;
  const backY = by - uy * head;
  const nx = -uy * head * 0.42;
  const ny = ux * head * 0.42;
  const positions = [
    ...scenePoint(bx, by, height),
    ...scenePoint(backX + nx, backY + ny, height),
    ...scenePoint(backX - nx, backY - ny, height),
  ];
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return geometry;
}

function material(color: number, opacity: number): THREE.MeshBasicMaterial {
  return new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity,
    depthWrite: false,
    side: THREE.DoubleSide,
    polygonOffset: true,
    polygonOffsetFactor: -4,
    polygonOffsetUnits: -4,
  });
}

function tag(mesh: THREE.Mesh, stroke: Stroke) {
  mesh.userData.stroke = stroke.ghost ? "ghost" : "ink";
  mesh.userData.inkId = stroke.ghost ? "" : stroke.key;
  mesh.renderOrder = stroke.ghost ? 5 : 6;
}

function clearGroup(group: THREE.Group) {
  for (const child of [...group.children]) {
    group.remove(child);
    const mesh = child as THREE.Mesh;
    mesh.geometry?.dispose();
    const current = mesh.material;
    if (Array.isArray(current)) current.forEach((item) => item.dispose());
    else current?.dispose();
  }
}

function addHold(group: THREE.Group, stroke: Stroke, x: number, y: number) {
  const paint = material(COLOR.hold, stroke.opacity);
  const ring = new THREE.Mesh(new THREE.RingGeometry(stroke.ghost ? 0.85 : 0.5, stroke.ghost ? 1.35 : 0.92, 40), paint);
  ring.geometry.rotateX(-Math.PI / 2);
  const at = toScene(x, y, stroke.height);
  ring.position.set(at.x, at.y, at.z);
  tag(ring, stroke);
  group.add(ring);
  const disc = new THREE.Mesh(new THREE.CircleGeometry(stroke.ghost ? 0.28 : 0.22, 24), paint.clone());
  disc.geometry.rotateX(-Math.PI / 2);
  disc.position.set(at.x, at.y + 0.01, at.z);
  tag(disc, stroke);
  group.add(disc);
}

export function setStrokes(group: THREE.Group, strokes: Stroke[]) {
  clearGroup(group);
  for (const stroke of strokes) {
    if (stroke.kind === "hold" && stroke.at) {
      addHold(group, stroke, stroke.at[0], stroke.at[1]);
      continue;
    }
    if (!stroke.path || stroke.path.length < 2) continue;
    const half = (stroke.kind === "carry" ? 0.34 : stroke.kind === "shot" ? 0.4 : 0.46) * (stroke.ghost ? 0.9 : 1);
    const ribbon = ribbonGeometry(stroke.path, half, stroke.height);
    if (!ribbon) continue;
    const mesh = new THREE.Mesh(ribbon, material(COLOR[stroke.kind], stroke.opacity));
    tag(mesh, stroke);
    group.add(mesh);
    const arrow = arrowGeometry(stroke.path, stroke.height + 0.02);
    if (!arrow) continue;
    const head = new THREE.Mesh(arrow, material(COLOR[stroke.kind], stroke.opacity));
    tag(head, stroke);
    group.add(head);
  }
}
