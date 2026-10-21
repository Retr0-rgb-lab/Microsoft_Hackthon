import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { BALL_RADIUS } from "./colors";
import { ballCenter, facingDirection, pose, sampleAt, toScene, type Frame } from "./coords";
import { clipNameFromQuery, statusLine } from "./hud";

const sceneRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sampleDir = path.resolve(sceneRoot, "../data/samples/sample_25hz_10min");

function readClip(): Frame[] {
  return readFileSync(path.join(sampleDir, "clip.jsonl"), "utf8")
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line) as Frame);
}

describe("pitch coordinates", () => {
  it("maps length, width, and height onto three.js Y-up", () => {
    expect(toScene(10, 4, 2)).toEqual({ x: 10, y: 2, z: -4 });
    expect(toScene(0, 0)).toEqual({ x: 0, y: 0, z: 0 });
  });

  it("keeps facing 0 along +X and facing π/2 along data +y", () => {
    expect(facingDirection(0).x).toBeCloseTo(1);
    expect(facingDirection(0).z).toBeCloseTo(0);
    expect(facingDirection(Math.PI / 2).x).toBeCloseTo(0);
    expect(facingDirection(Math.PI / 2).z).toBeCloseTo(-1);
  });

  it("matches three.js rotation.y of a local +X nose", () => {
    const obj = new THREE.Object3D();
    const nose = new THREE.Vector3(1, 0, 0);
    for (const facing of [0, Math.PI / 2, -Math.PI / 2, Math.PI]) {
      obj.rotation.y = facing;
      obj.updateMatrixWorld(true);
      const world = nose.clone().applyMatrix4(obj.matrixWorld);
      const expected = facingDirection(facing);
      expect(world.x).toBeCloseTo(expected.x, 6);
      expect(world.z).toBeCloseTo(expected.z, 6);
      expect(world.y).toBeCloseTo(0, 6);
    }
  });

  it("samples frames the way the format note describes", () => {
    expect(sampleAt(0, 25, 751)).toEqual({ i0: 0, i1: 1, a: 0 });
    expect(sampleAt(20, 25, 751).a).toBeCloseTo(0.5);
    expect(sampleAt(20320, 25, 751)).toEqual({ i0: 508, i1: 509, a: 0 });
    expect(sampleAt(30000, 25, 751)).toEqual({ i0: 750, i1: 750, a: 0 });
  });

  it("lifts the ball centre by its radius above ball.z", () => {
    expect(ballCenter(8.557, -6.989, 1.8)).toEqual({ x: 8.557, y: 1.8 + BALL_RADIUS, z: 6.989 });
  });

  it("interpolates player feet and ball height between frames", () => {
    const f0 = {
      frame_id: 0,
      t_ms: 0,
      attack_dir: 1,
      players: [["H01", 0, 0, 0, 0, 0] as Frame["players"][number]],
      ball: [0, 0, 0, 0, 0, 0] as Frame["ball"],
    };
    const f1 = {
      frame_id: 1,
      t_ms: 40,
      attack_dir: 1,
      players: [["H01", 2, -4, 0, 0, 1] as Frame["players"][number]],
      ball: [2, 2, 2, 0, 0, 0] as Frame["ball"],
    };
    const sample = pose(f0, f1, 0.5);
    expect(sample.players[0]).toMatchObject({ id: "H01", x: 1, y: -2, facing: 0 });
    expect(sample.ball).toEqual({ x: 1, y: 1, z: 1 });
  });
});

describe("sample clip", () => {
  const frames = readClip();
  const meta = JSON.parse(readFileSync(path.join(sampleDir, "metadata.json"), "utf8")) as {
    frame_hz: number;
    teams: { name: string; short_name: string }[];
    venue: { name: string };
    players: { player_id: string; name: string; team_id: string }[];
  };

  it("is the first 30 seconds at 25 Hz with 22 players", () => {
    expect(meta.frame_hz).toBe(25);
    expect(frames).toHaveLength(751);
    expect(frames[0]?.frame_id).toBe(0);
    expect(frames[0]?.players).toHaveLength(22);
    expect(frames[750]?.frame_id).toBe(750);
    expect(frames[750]?.t_ms).toBe(30000);
    expect(frames[508]?.ball[2]).toBeCloseTo(1.8);
    const teams = new Map(meta.players.map((player) => [player.player_id, player.team_id]));
    expect([...teams.values()].filter((team) => team === "HOME")).toHaveLength(11);
    expect([...teams.values()].filter((team) => team === "AWAY")).toHaveLength(11);
  });

  it("keeps squad and club names out of the scene UI sources", () => {
    const banned = [
      ...meta.teams.flatMap((team) => [team.name, team.short_name]),
      meta.venue.name,
      ...meta.players.map((player) => player.name),
    ];
    const files = sourceFiles(path.join(sceneRoot, "src")).concat(path.join(sceneRoot, "index.html"));
    for (const file of files) {
      if (file.endsWith(".test.ts")) continue;
      const text = readFileSync(file, "utf8");
      for (const word of banned) {
        expect(text.includes(word), `${path.relative(sceneRoot, file)} contains ${word}`).toBe(false);
      }
    }
  });
});

describe("hud", () => {
  it("labels the two cameras without a squad name", () => {
    const line = statusLine({
      tMs: 20320,
      frameId: 508,
      ballZ: 1.8,
      players: 22,
      camera: "broadcast",
      hz: 25,
    });
    expect(line).toContain("转播");
    expect(line).toContain("ball z 1.80 m");
    expect(line).toContain("22 players");
    expect(clipNameFromQuery(null)).toBe("clip.jsonl");
    expect(clipNameFromQuery("tracking.jsonl")).toBe("tracking.jsonl");
    expect(() => clipNameFromQuery("../tracking.jsonl")).toThrow();
  });
});

function sourceFiles(dir: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) found.push(...sourceFiles(full));
    else if (/\.(ts|css|html)$/.test(entry)) found.push(full);
  }
  return found;
}
