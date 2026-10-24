import type { Language, QuestionId } from "./types";

export type SampleOption = {
  option_id: string;
  type: "pass" | "carry" | "shot";
  target_player_id: string | null;
  end_location: [number, number];
  progress_m: number;
  offside: boolean;
};

/** A `decision_point` from events.jsonl. Probability fields on the file are not copied. */
export type DecisionPoint = {
  event_id: string;
  match_id: string;
  team_id: "HOME" | "AWAY";
  player_id: string;
  available_at_ms: number;
  location: [number, number];
  options: SampleOption[];
  chosen_option_id: string;
  chosen_index: number;
};

export type RosterPlayer = {
  player_id: string;
  team_id: "HOME" | "AWAY";
  jersey_number: number;
};

export function parseDecisionPoints(rawEvents: unknown[], clipEndMs: number): DecisionPoint[] {
  const points: DecisionPoint[] = [];
  for (const raw of rawEvents) {
    if (!raw || typeof raw !== "object") continue;
    const event = raw as Record<string, unknown>;
    if (event.type !== "decision_point") continue;
    const tMs = Number(event.available_at_ms);
    if (!Number.isFinite(tMs) || tMs > clipEndMs) continue;
    const options = parseOptions(event.options);
    const chosen = options.find((option) => option.option_id === String(event.chosen_option_id ?? ""));
    if (!chosen) continue;
    const location = pair(event.location) ?? [0, 0];
    points.push({
      event_id: String(event.event_id ?? ""),
      match_id: String(event.match_id ?? ""),
      team_id: event.team_id === "AWAY" ? "AWAY" : "HOME",
      player_id: String(event.player_id ?? ""),
      available_at_ms: tMs,
      location,
      options,
      chosen_option_id: chosen.option_id,
      chosen_index: Number(event.chosen_index ?? 0),
    });
  }
  return points;
}

export function frameForTime<T>(frames: readonly T[], tMs: number, hz: number): T {
  const index = Math.round((tMs * hz) / 1000);
  const frame = frames[index];
  if (!frame) throw new Error(`No frame at ${tMs} ms`);
  return frame;
}

export function snapshotIdFor(frameId: number, eventId: string): string {
  return `f${frameId}:${eventId}`;
}

export function chosenOption(event: DecisionPoint): SampleOption {
  const option = event.options.find((item) => item.option_id === event.chosen_option_id);
  if (!option) throw new Error(`Missing chosen option on ${event.event_id}`);
  return option;
}

/** Onside pass with the greatest forward progress. One pass arrow uses this when the touch was not a pass. */
export function forwardPass(event: DecisionPoint): SampleOption | null {
  const passes = event.options.filter((option) => option.type === "pass" && !option.offside && option.target_player_id);
  if (!passes.length) return null;
  return [...passes].sort((a, b) => b.progress_m - a.progress_m || a.option_id.localeCompare(b.option_id))[0] ?? null;
}

export function momentLabel(
  index: number,
  event: DecisionPoint,
  shirt: (playerId: string) => string,
  language: Language,
): string {
  const code = index < 3 ? String.fromCharCode(65 + index) : String(index + 1);
  const prefix = language === "zh" ? "案例" : "Case";
  const seconds = (event.available_at_ms / 1000).toFixed(1);
  return `${prefix} ${code} · ${seconds}s · ${shirt(event.player_id)}`;
}

export function questionSet(
  event: DecisionPoint,
  shirt: (playerId: string | null) => string,
  language: Language,
): { id: QuestionId; label: string }[] {
  const forward = forwardPass(event);
  const forwardShirt = shirt(forward?.target_player_id ?? null);
  if (language === "zh") {
    return [
      { id: "why_actual", label: "为什么是这个动作？" },
      { id: "why_not_pass", label: `为什么不传给 ${forwardShirt}？` },
      { id: "why_forward", label: "为什么不向前处理？" },
    ];
  }
  return [
    { id: "why_actual", label: "Why this action?" },
    { id: "why_not_pass", label: `Why not pass to ${forwardShirt}?` },
    { id: "why_forward", label: "Why not play forward?" },
  ];
}

function parseOptions(raw: unknown): SampleOption[] {
  if (!Array.isArray(raw)) return [];
  const options: SampleOption[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const option = item as Record<string, unknown>;
    const type = option.type;
    if (type !== "pass" && type !== "carry" && type !== "shot") continue;
    const end = pair(option.end_location);
    if (!end) continue;
    options.push({
      option_id: String(option.option_id ?? ""),
      type,
      target_player_id: option.target_player_id == null ? null : String(option.target_player_id),
      end_location: end,
      progress_m: Number(option.progress_m ?? 0),
      offside: Boolean(option.offside),
    });
  }
  return options;
}

function pair(raw: unknown): [number, number] | null {
  if (!Array.isArray(raw) || raw.length < 2) return null;
  const x = Number(raw[0]);
  const y = Number(raw[1]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return [x, y];
}
