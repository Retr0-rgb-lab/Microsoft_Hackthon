import * as THREE from "three";
import { toScene } from "../coords";
import type { ActionClass, DecideFromTracking, PitchPoint } from "./types";
import { ranked } from "./types";

const ACTUAL = 0x241433;
const HYPO = 0x7c3aed;
const LIFT = 0.55;

export type ArrowLayer = {
  group: THREE.Group;
  entries: { action: ActionClass; materials: THREE.MeshBasicMaterial[] }[];
};

/** One mark per action class. Solid ink is the recorded action. Dashed purple is every other class. */
export function buildArrows(decide: DecideFromTracking): ArrowLayer {
  const group = new THREE.Group();
  const entries: ArrowLayer["entries"] = [];
  const origin = pathOrigin(decide);
  for (const action of ranked(decide)) {
    const materials: THREE.MeshBasicMaterial[] = [];
    const dashed = action.action !== decide.actual_action;
    const color = dashed ? HYPO : ACTUAL;
    if (action.action === "hold" || !action.geometry) {
      if (origin) addHold(group, origin, color, dashed, materials);
    } else {
      addPath(group, action.geometry.path, color, dashed, materials);
    }
    entries.push({ action: action.action, materials });
  }
  return { group, entries };
}

export function setArrowEmphasis(layer: ArrowLayer, emphasize: ActionClass | null): void {
  for (const entry of layer.entries) {
    const hot = emphasize == null || entry.action === emphasize;
    for (const material of entry.materials) {
      material.opacity = hot ? 1 : 0.28;
      material.transparent = true;
    }
  }
}

export function disposeArrows(layer: ArrowLayer): void {
  layer.group.traverse((obj) => {
    if (obj instanceof THREE.Mesh) {
      obj.geometry.dispose();
      const material = obj.material;
      if (Array.isArray(material)) material.forEach((item) => item.dispose());
      else material.dispose();
    }
  });
  layer.group.clear();
}

function pathOrigin(decide: DecideFromTracking): PitchPoint | null {
  for (const action of ranked(decide)) {
    const start = action.geometry?.path[0];
    if (start) return start;
  }
  return null;
}

function addPath(
  group: THREE.Group,
  path: readonly PitchPoint[],
  color: number,
  dashed: boolean,
  materials: THREE.MeshBasicMaterial[],
): void {
  const points = path.map(([x, y]) => {
    const at = toScene(x, y, LIFT);
    return new THREE.Vector3(at.x, at.y, at.z);
  });
  for (let i = 0; i < points.length - 1; i += 1) {
    const a = points[i];
    const b = points[i + 1];
    if (!a || !b) continue;
    addRibbon(group, a, b, color, dashed, materials);
  }
  const end = points[points.length - 1];
  const prev = points[points.length - 2] ?? points[0];
  if (end && prev) addHead(group, prev, end, color, materials);
}

function addRibbon(
  group: THREE.Group,
  a: THREE.Vector3,
  b: THREE.Vector3,
  color: number,
  dashed: boolean,
  materials: THREE.MeshBasicMaterial[],
): void {
  const dx = b.x - a.x;
  const dz = b.z - a.z;
  const len = Math.hypot(dx, dz);
  if (len < 0.08) return;
  const yaw = Math.atan2(-dz, dx);
  if (!dashed) {
    addBox(group, a, b, len, yaw, color, 0.72, materials);
    return;
  }
  const dash = 1.5;
  const gap = 0.85;
  let traveled = 0;
  while (traveled < len - 0.05) {
    const dashLen = Math.min(dash, len - traveled);
    if (dashLen < 0.15) break;
    const start = a.clone().lerp(b, traveled / len);
    const finish = a.clone().lerp(b, (traveled + dashLen) / len);
    addBox(group, start, finish, dashLen, yaw, color, 0.48, materials);
    traveled += dash + gap;
  }
}

function addBox(
  group: THREE.Group,
  a: THREE.Vector3,
  b: THREE.Vector3,
  len: number,
  yaw: number,
  color: number,
  width: number,
  materials: THREE.MeshBasicMaterial[],
): void {
  const material = new THREE.MeshBasicMaterial({ color });
  materials.push(material);
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(Math.max(len, 0.05), 0.07, width), material);
  mesh.position.set((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2);
  mesh.rotation.y = yaw;
  group.add(mesh);
}

function addHead(
  group: THREE.Group,
  prev: THREE.Vector3,
  end: THREE.Vector3,
  color: number,
  materials: THREE.MeshBasicMaterial[],
): void {
  const dx = end.x - prev.x;
  const dz = end.z - prev.z;
  const len = Math.hypot(dx, dz) || 1;
  const geometry = new THREE.ConeGeometry(0.85, 2.05, 12);
  geometry.rotateZ(-Math.PI / 2);
  const material = new THREE.MeshBasicMaterial({ color });
  materials.push(material);
  const mesh = new THREE.Mesh(geometry, material);
  const back = 0.35;
  mesh.position.set(end.x - (dx / len) * back, end.y + 0.02, end.z - (dz / len) * back);
  mesh.rotation.y = Math.atan2(-dz, dx);
  group.add(mesh);
}

function addHold(
  group: THREE.Group,
  at: PitchPoint,
  color: number,
  dashed: boolean,
  materials: THREE.MeshBasicMaterial[],
): void {
  const point = toScene(at[0], at[1], 0.08);
  const radii: Array<[number, number]> = dashed
    ? [
        [1.15, 1.4],
        [1.85, 2.15],
      ]
    : [[1.2, 1.7]];
  for (const [inner, outer] of radii) {
    const material = new THREE.MeshBasicMaterial({
      color,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: dashed ? 0.9 : 1,
    });
    materials.push(material);
    const mesh = new THREE.Mesh(new THREE.RingGeometry(inner, outer, 40), material);
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set(point.x, point.y, point.z);
    group.add(mesh);
  }
}
