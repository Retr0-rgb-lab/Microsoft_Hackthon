import { BALL_RADIUS } from "./colors";

export const PITCH = {
  length: 105,
  width: 68,
  halfLength: 52.5,
  halfWidth: 34,
} as const;

export type PlayerRow = [string, number, number, number, number, number];
export type BallRow = [number, number, number, number, number, number];

export type Frame = {
  frame_id: number;
  t_ms: number;
  attack_dir: number;
  players: PlayerRow[];
  ball: BallRow;
};

export type ScenePoint = { x: number; y: number; z: number };

/** Data (x along length, y along width, z up) → three.js Y-up. */
export function toScene(x: number, y: number, z = 0): ScenePoint {
  const sceneZ = -y;
  return { x, y: z, z: sceneZ === 0 ? 0 : sceneZ };
}

/**
 * Local +X after `rotation.y = facing`.
 * Data facing 0 points along +x; π/2 points along +y, which is scene -Z.
 */
export function facingDirection(facing: number): { x: number; z: number } {
  return { x: Math.cos(facing), z: -Math.sin(facing) };
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function sampleAt(tMs: number, hz: number, frameCount: number): { i0: number; i1: number; a: number } {
  if (frameCount < 1) throw new Error("empty clip");
  const k = (tMs * hz) / 1000;
  const i0 = Math.max(0, Math.min(Math.floor(k), frameCount - 1));
  const i1 = Math.min(i0 + 1, frameCount - 1);
  const a = i0 === i1 ? 0 : k - i0;
  return { i0, i1, a };
}

export type Pose = {
  players: { id: string; x: number; y: number; facing: number }[];
  ball: { x: number; y: number; z: number };
};

export function pose(f0: Frame, f1: Frame, a: number): Pose {
  const next = new Map(f1.players.map((row) => [row[0], row]));
  return {
    players: f0.players.map(([id, x, y, , , facing]) => {
      const other = next.get(id);
      const x1 = other ? other[1] : x;
      const y1 = other ? other[2] : y;
      return { id, x: lerp(x, x1, a), y: lerp(y, y1, a), facing };
    }),
    ball: {
      x: lerp(f0.ball[0], f1.ball[0], a),
      y: lerp(f0.ball[1], f1.ball[1], a),
      z: lerp(f0.ball[2], f1.ball[2], a),
    },
  };
}

export function ballCenter(x: number, y: number, z: number, radius = BALL_RADIUS): ScenePoint {
  return toScene(x, y, z + radius);
}
