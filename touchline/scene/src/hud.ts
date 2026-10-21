export type CameraMode = "broadcast" | "top";

export function statusLine(input: {
  tMs: number;
  frameId: number;
  ballZ: number;
  players: number;
  camera: CameraMode;
  hz: number;
}): string {
  const sec = Math.max(0, input.tMs) / 1000;
  const mm = Math.floor(sec / 60);
  const ss = sec - mm * 60;
  const clock = `${String(mm).padStart(2, "0")}:${ss.toFixed(1).padStart(4, "0")}`;
  const cam = input.camera === "broadcast" ? "转播" : "俯视";
  return `${cam} · ${clock} · frame ${input.frameId} · ball z ${input.ballZ.toFixed(2)} m · ${input.players} players · ${input.hz} Hz`;
}

export function clipNameFromQuery(raw: string | null): string {
  if (!raw) return "clip.jsonl";
  if (!/^[A-Za-z0-9._-]+$/.test(raw) || raw.startsWith(".")) {
    throw new Error("Clip name must be a file in the sample folder.");
  }
  return raw;
}
