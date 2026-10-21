import * as THREE from "three";
import { PITCH, toScene } from "./coords";

const LINE_Y = 0.045;
const LINE_W = 0.12;

function lineMaterial(): THREE.MeshBasicMaterial {
  return new THREE.MeshBasicMaterial({
    color: 0xf4f7f2,
    polygonOffset: true,
    polygonOffsetFactor: -2,
    polygonOffsetUnits: -2,
  });
}

function addSegment(parent: THREE.Object3D, material: THREE.Material, x1: number, y1: number, x2: number, y2: number) {
  const a = toScene(x1, y1, LINE_Y);
  const b = toScene(x2, y2, LINE_Y);
  const dx = b.x - a.x;
  const dz = b.z - a.z;
  const len = Math.hypot(dx, dz);
  if (len < 1e-4) return;
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(len, 0.012, LINE_W), material);
  mesh.position.set((a.x + b.x) / 2, LINE_Y, (a.z + b.z) / 2);
  mesh.rotation.y = Math.atan2(-dz, dx);
  mesh.receiveShadow = true;
  parent.add(mesh);
}

function addRect(parent: THREE.Object3D, material: THREE.Material, x0: number, y0: number, x1: number, y1: number) {
  addSegment(parent, material, x0, y0, x1, y0);
  addSegment(parent, material, x1, y0, x1, y1);
  addSegment(parent, material, x1, y1, x0, y1);
  addSegment(parent, material, x0, y1, x0, y0);
}

function addArc(
  parent: THREE.Object3D,
  material: THREE.Material,
  cx: number,
  cy: number,
  radius: number,
  a0: number,
  a1: number,
  steps: number,
  keep?: (x: number, y: number) => boolean,
) {
  let prev: [number, number] | null = null;
  for (let i = 0; i <= steps; i += 1) {
    const t = a0 + ((a1 - a0) * i) / steps;
    const x = cx + radius * Math.cos(t);
    const y = cy + radius * Math.sin(t);
    if (keep && !keep(x, y)) {
      prev = null;
      continue;
    }
    if (prev) addSegment(parent, material, prev[0], prev[1], x, y);
    prev = [x, y];
  }
}

function addSpot(parent: THREE.Object3D, material: THREE.Material, x: number, y: number) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.02, 16), material);
  const p = toScene(x, y, 0.04);
  mesh.position.set(p.x, p.y, p.z);
  parent.add(mesh);
}

function grassTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 512;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas 2d unavailable");
  const stripes = 14;
  for (let i = 0; i < stripes; i += 1) {
    ctx.fillStyle = i % 2 === 0 ? "#2f8d4c" : "#277a41";
    ctx.fillRect((i * canvas.width) / stripes, 0, canvas.width / stripes + 1, canvas.height);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = THREE.ClampToEdgeWrapping;
  texture.wrapT = THREE.ClampToEdgeWrapping;
  return texture;
}

function addGoals(parent: THREE.Object3D) {
  const post = new THREE.MeshStandardMaterial({ color: 0xf7f7f5, roughness: 0.35, metalness: 0.05 });
  const net = new THREE.MeshStandardMaterial({
    color: 0xe7eef5,
    transparent: true,
    opacity: 0.28,
    roughness: 1,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  const halfGoal = 7.32 / 2;
  const height = 2.44;
  for (const sign of [1, -1] as const) {
    const goal = new THREE.Group();
    for (const gy of [halfGoal, -halfGoal]) {
      const upright = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, height, 12), post);
      const p = toScene(sign * PITCH.halfLength, gy, height / 2);
      upright.position.set(p.x, p.y, p.z);
      upright.castShadow = true;
      goal.add(upright);
    }
    const bar = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 7.32, 12), post);
    bar.rotation.x = Math.PI / 2;
    const barPos = toScene(sign * PITCH.halfLength, 0, height);
    bar.position.set(barPos.x, barPos.y, barPos.z);
    bar.castShadow = true;
    goal.add(bar);

    const back = new THREE.Mesh(new THREE.PlaneGeometry(7.32, height), net);
    const backPos = toScene(sign * (PITCH.halfLength + 1.6), 0, height / 2);
    back.position.set(backPos.x, backPos.y, backPos.z);
    back.rotation.y = sign > 0 ? 0 : Math.PI;
    back.renderOrder = 2;
    goal.add(back);

    parent.add(goal);
  }
}

export function createStage(scene: THREE.Scene, renderer: THREE.WebGLRenderer) {
  scene.background = new THREE.Color(0x8eafc6);

  const hemi = new THREE.HemisphereLight(0xd7ecff, 0x1d3a22, 0.9);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xfff6e8, 1.45);
  sun.position.set(-36, 54, 28);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.near = 10;
  sun.shadow.camera.far = 160;
  sun.shadow.camera.left = -70;
  sun.shadow.camera.right = 70;
  sun.shadow.camera.top = 50;
  sun.shadow.camera.bottom = -50;
  sun.shadow.bias = -0.00035;
  scene.add(sun);
  scene.add(sun.target);
  const fill = new THREE.DirectionalLight(0xd5e6f5, 0.4);
  fill.position.set(24, 16, 48);
  scene.add(fill);

  const bowl = new THREE.Mesh(
    new THREE.PlaneGeometry(420, 280),
    new THREE.MeshStandardMaterial({ color: 0x102018, roughness: 1 }),
  );
  bowl.rotation.x = -Math.PI / 2;
  bowl.position.y = -0.08;
  bowl.receiveShadow = true;
  scene.add(bowl);

  const apron = new THREE.Mesh(
    new THREE.PlaneGeometry(140, 96),
    new THREE.MeshStandardMaterial({ color: 0x1c5a34, roughness: 0.96 }),
  );
  apron.rotation.x = -Math.PI / 2;
  apron.position.y = -0.02;
  apron.receiveShadow = true;
  scene.add(apron);

  const texture = grassTexture();
  texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
  const grass = new THREE.Mesh(
    new THREE.PlaneGeometry(PITCH.length, PITCH.width),
    new THREE.MeshStandardMaterial({ map: texture, roughness: 0.92, metalness: 0 }),
  );
  grass.rotation.x = -Math.PI / 2;
  grass.receiveShadow = true;
  scene.add(grass);

  const marks = new THREE.Group();
  const paint = lineMaterial();
  const hl = PITCH.halfLength;
  const hw = PITCH.halfWidth;
  addRect(marks, paint, -hl, -hw, hl, hw);
  addSegment(marks, paint, 0, -hw, 0, hw);
  addRing(marks, 0, 0, 9.15);
  addSpot(marks, paint, 0, 0);

  for (const sign of [1, -1] as const) {
    const goalX = sign * hl;
    const boxX = sign * (hl - 16.5);
    const sixX = sign * (hl - 5.5);
    addSegment(marks, paint, boxX, -20.16, boxX, 20.16);
    addSegment(marks, paint, boxX, 20.16, goalX, 20.16);
    addSegment(marks, paint, boxX, -20.16, goalX, -20.16);
    addSegment(marks, paint, sixX, -9.16, sixX, 9.16);
    addSegment(marks, paint, sixX, 9.16, goalX, 9.16);
    addSegment(marks, paint, sixX, -9.16, goalX, -9.16);
    addSpot(marks, paint, sign * (hl - 11), 0);
    const limit = hl - 16.5;
    addArc(marks, paint, sign * (hl - 11), 0, 9.15, 0, Math.PI * 2, 80, (x) =>
      sign > 0 ? x <= limit + 0.04 : x >= -limit - 0.04,
    );
  }

  const corners: Array<[number, number, number, number]> = [
    [hl, hw, Math.PI, Math.PI * 1.5],
    [hl, -hw, Math.PI / 2, Math.PI],
    [-hl, hw, Math.PI * 1.5, Math.PI * 2],
    [-hl, -hw, 0, Math.PI / 2],
  ];
  for (const [cx, cy, a0, a1] of corners) {
    addArc(marks, paint, cx, cy, 1, a0, a1, 8);
  }

  addGoals(marks);
  scene.add(marks);
  return marks;
}

function addRing(parent: THREE.Object3D, cx: number, cy: number, radius: number) {
  const geo = new THREE.RingGeometry(radius - 0.06, radius + 0.06, 96);
  geo.rotateX(-Math.PI / 2);
  const mesh = new THREE.Mesh(geo, lineMaterial());
  const p = toScene(cx, cy, LINE_Y);
  mesh.position.set(p.x, p.y, p.z);
  parent.add(mesh);
}
