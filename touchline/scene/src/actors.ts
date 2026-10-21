import * as THREE from "three";
import { AWAY_COLOR, BALL_RADIUS, HOME_COLOR } from "./colors";
import { ballCenter, pose, toScene, type Frame } from "./coords";

export type ActorSet = {
  group: THREE.Group;
  meshes: Map<string, THREE.Group>;
  ball: THREE.Mesh;
  marker: THREE.Mesh;
};

function makePlayer(color: number, bodyGeo: THREE.CapsuleGeometry, noseGeo: THREE.CapsuleGeometry, discGeo: THREE.CylinderGeometry): THREE.Group {
  const group = new THREE.Group();
  const kit = new THREE.MeshStandardMaterial({ color, roughness: 0.48, metalness: 0.02 });
  const body = new THREE.Mesh(bodyGeo, kit);
  body.position.y = 0.93;
  body.castShadow = true;
  group.add(body);
  const nose = new THREE.Mesh(
    noseGeo,
    new THREE.MeshStandardMaterial({ color: 0xf7f4ee, roughness: 0.4 }),
  );
  nose.rotation.z = Math.PI / 2;
  nose.position.set(0.58, 1.48, 0);
  nose.castShadow = true;
  group.add(nose);
  const disc = new THREE.Mesh(discGeo, kit);
  disc.position.y = 0.025;
  disc.receiveShadow = true;
  group.add(disc);
  return group;
}

export function createActors(players: { player_id: string; team_id: string }[]): ActorSet {
  const group = new THREE.Group();
  const meshes = new Map<string, THREE.Group>();
  const bodyGeo = new THREE.CapsuleGeometry(0.42, 1.02, 6, 16);
  const noseGeo = new THREE.CapsuleGeometry(0.11, 0.2, 4, 8);
  const discGeo = new THREE.CylinderGeometry(0.9, 0.9, 0.035, 24);
  let home = 0;
  let away = 0;
  for (const player of players) {
    const color = player.team_id === "HOME" ? HOME_COLOR : player.team_id === "AWAY" ? AWAY_COLOR : null;
    if (color === null) continue;
    if (player.team_id === "HOME") home += 1;
    else away += 1;
    const mesh = makePlayer(color, bodyGeo, noseGeo, discGeo);
    meshes.set(player.player_id, mesh);
    group.add(mesh);
  }
  if (home !== 11 || away !== 11 || meshes.size !== 22) {
    throw new Error(`Expected 11 HOME and 11 AWAY, got ${home} and ${away}.`);
  }

  const ball = new THREE.Mesh(
    new THREE.SphereGeometry(BALL_RADIUS, 28, 18),
    new THREE.MeshStandardMaterial({
      color: 0xf7f4ee,
      roughness: 0.32,
      metalness: 0.02,
      emissive: 0x3a342c,
      emissiveIntensity: 0.45,
    }),
  );
  ball.castShadow = true;
  const seam = new THREE.Mesh(
    new THREE.TorusGeometry(BALL_RADIUS * 0.96, 0.018, 8, 24),
    new THREE.MeshStandardMaterial({ color: 0x24282e, roughness: 0.55 }),
  );
  seam.rotation.x = Math.PI / 2;
  ball.add(seam);
  const marker = new THREE.Mesh(
    new THREE.RingGeometry(0.28, 0.5, 28),
    new THREE.MeshBasicMaterial({ color: 0xf6f3ec, side: THREE.DoubleSide }),
  );
  marker.rotation.x = -Math.PI / 2;
  group.add(ball, marker);
  return { group, meshes, ball, marker };
}

export function applyPose(actors: ActorSet, f0: Frame, f1: Frame, a: number): number {
  const sample = pose(f0, f1, a);
  for (const player of sample.players) {
    const mesh = actors.meshes.get(player.id);
    if (!mesh) continue;
    const at = toScene(player.x, player.y, 0);
    mesh.position.set(at.x, at.y, at.z);
    mesh.rotation.y = player.facing;
  }
  const center = ballCenter(sample.ball.x, sample.ball.y, sample.ball.z);
  actors.ball.position.set(center.x, center.y, center.z);
  const mark = toScene(sample.ball.x, sample.ball.y, 0.06);
  actors.marker.position.set(mark.x, mark.y, mark.z);
  return sample.ball.z;
}
