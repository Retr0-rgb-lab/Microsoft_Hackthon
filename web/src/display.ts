import {
  ACTIONS,
  type Action,
  type ArrowMark,
  type Fixture,
  type Moment,
  type PlayerMark,
  type Point,
  type TeamId,
} from "./types";

/** High-contrast yellow for the on-video primary arrow. Not the sidebar green. */
export const PRIMARY_ARROW = "#FFE500";

/** Premier League green. Softmax highlight in the sidebar only. */
export const SIDEBAR_HIGHLIGHT = "#00FF85";

export const FRAME_W = 1000;
export const FRAME_H = 640;

export const DISTRIBUTION_SUM_TOLERANCE = 1e-3;

const MAX_SECONDARY_PASSES = 2;

export function isAction(value: unknown): value is Action {
  return typeof value === "string" && (ACTIONS as readonly string[]).includes(value);
}

/**
 * Secondary explain is copy for the spare pass. A hold line is never valid there,
 * including when hold is the highlighted bar.
 */
export function isSecondaryPassCopy(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed || /[\r\n]/.test(text)) return false;
  if (/\bhold\b/i.test(trimmed)) return false;
  return /\bpass\b/i.test(trimmed);
}

export function formatPercent(probability: number): string {
  return `${Math.round(probability * 100)}%`;
}

export function formatClock(totalSeconds: number): string {
  const whole = Math.max(0, Math.round(totalSeconds));
  const minutes = Math.floor(whole / 60);
  const seconds = whole % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function argmaxAction(distribution: Record<Action, number>): Action {
  return ACTIONS.reduce((best, label) => (distribution[label] > distribution[best] ? label : best));
}

/**
 * Scheme A field arrows.
 * Pass: bright primary plus at most two secondary passes.
 * Dribble: one dashed carry plus at most one secondary pass.
 * Shoot and hold: nothing on the pitch.
 */
export function arrowsForDisplay(recommended: Action, arrows: readonly ArrowMark[]): ArrowMark[] {
  if (recommended === "shoot" || recommended === "hold") return [];
  const usable = arrows.filter((arrow) => arrow.kind === "pass" || arrow.kind === "dribble");
  if (recommended === "dribble") {
    const primary = usable.find((arrow) => arrow.primary && arrow.kind === "dribble");
    if (!primary) return [];
    const secondary = usable.find((arrow) => !arrow.primary && arrow.kind === "pass");
    return secondary ? [primary, secondary] : [primary];
  }
  const primary = usable.find((arrow) => arrow.primary && arrow.kind === "pass");
  if (!primary) return [];
  const secondaries = usable
    .filter((arrow) => !arrow.primary && arrow.kind === "pass")
    .slice(0, MAX_SECONDARY_PASSES);
  return [primary, ...secondaries];
}

/** Latest key possession at or before `t`. Before the first mark, show that mark. */
export function momentAt(moments: readonly Moment[], t: number): Moment {
  if (moments.length === 0) {
    throw new Error("no possession moments");
  }
  const sorted = [...moments].sort((a, b) => a.t_seconds - b.t_seconds);
  let current = sorted[0];
  for (const moment of sorted) {
    if (moment.t_seconds <= t + 1e-6) current = moment;
  }
  return current;
}

export function shaftEnd(x1: number, y1: number, x2: number, y2: number, trim: number): Point {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const length = Math.hypot(x2 - x1, y2 - y1);
  const cut = Math.min(Math.max(trim, 0), length * 0.45);
  return { x: x2 - Math.cos(angle) * cut, y: y2 - Math.sin(angle) * cut };
}

export function arrowHeadPoints(x1: number, y1: number, x2: number, y2: number, size: number): string {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const left = angle + Math.PI * 0.84;
  const right = angle - Math.PI * 0.84;
  const lx = x2 + Math.cos(left) * size;
  const ly = y2 + Math.sin(left) * size;
  const rx = x2 + Math.cos(right) * size;
  const ry = y2 + Math.sin(right) * size;
  return `${x2},${y2} ${lx},${ly} ${rx},${ry}`;
}

function asRecord(value: unknown, name: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${name} must be an object`);
  }
  return value as Record<string, unknown>;
}

function asString(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function asNumber(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${name} must be a finite number`);
  }
  return value;
}

function asBoolean(value: unknown, name: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${name} must be a boolean`);
  return value;
}

function asPoint(value: unknown, name: string, maxX: number, maxY: number): Point {
  const record = asRecord(value, name);
  const x = asNumber(record.x, `${name}.x`);
  const y = asNumber(record.y, `${name}.y`);
  if (x < 0 || y < 0 || x > maxX || y > maxY) {
    throw new Error(`${name} is outside 0..${maxX} by 0..${maxY}`);
  }
  return { x, y };
}

function asDistribution(value: unknown, momentId: string): Record<Action, number> {
  const record = asRecord(value, `${momentId} distribution`);
  const missing = ACTIONS.filter((label) => !(label in record));
  const extra = Object.keys(record).filter((key) => !isAction(key));
  if (missing.length > 0 || extra.length > 0) {
    throw new Error(`${momentId} distribution must cover pass, shoot, dribble, and hold`);
  }
  const distribution = {} as Record<Action, number>;
  for (const label of ACTIONS) {
    const probability = asNumber(record[label], `${momentId} distribution.${label}`);
    if (probability < 0) throw new Error(`${momentId} distribution.${label} must be non-negative`);
    distribution[label] = probability;
  }
  const total = ACTIONS.reduce((sum, label) => sum + distribution[label], 0);
  if (Math.abs(total - 1) > DISTRIBUTION_SUM_TOLERANCE) {
    throw new Error(`${momentId} distribution must sum to 1 (got ${total})`);
  }
  return distribution;
}

function assertDisclaimer(text: string): void {
  const lower = text.toLowerCase();
  if (!lower.includes("decision aid")) throw new Error("disclaimer must say decision aid");
  if (!lower.includes("full distribution")) {
    throw new Error("disclaimer must call this a full distribution");
  }
  if (!lower.includes("not a single optimal action")) {
    throw new Error("disclaimer must say this is not a single optimal action");
  }
  for (const label of ACTIONS) {
    if (!lower.includes(label)) throw new Error(`disclaimer must name ${label}`);
  }
}

function asTeam(value: unknown, name: string): TeamId {
  if (value !== "home" && value !== "away") throw new Error(`${name} must be home or away`);
  return value;
}

function asPlayer(value: unknown, momentId: string, index: number): PlayerMark {
  const name = `${momentId} players[${index}]`;
  const record = asRecord(value, name);
  return {
    id: asString(record.id, `${name}.id`),
    team: asTeam(record.team, `${name}.team`),
    possessor: asBoolean(record.possessor, `${name}.possessor`),
    frame: asPoint(record.frame, `${name}.frame`, 1, 1),
    pitch: asPoint(record.pitch, `${name}.pitch`, 105, 68),
  };
}

function asArrow(value: unknown, momentId: string, index: number): ArrowMark {
  const name = `${momentId} arrows[${index}]`;
  const record = asRecord(value, name);
  const kind = record.kind;
  if (!isAction(kind)) throw new Error(`${name}.kind must be pass, shoot, dribble, or hold`);
  return {
    kind,
    primary: asBoolean(record.primary, `${name}.primary`),
    from_frame: asPoint(record.from_frame, `${name}.from_frame`, 1, 1),
    to_frame: asPoint(record.to_frame, `${name}.to_frame`, 1, 1),
    from_pitch: asPoint(record.from_pitch, `${name}.from_pitch`, 105, 68),
    to_pitch: asPoint(record.to_pitch, `${name}.to_pitch`, 105, 68),
  };
}

function asMoment(value: unknown, index: number, duration: number): Moment {
  const record = asRecord(value, `moments[${index}]`);
  const id = asString(record.id, `moments[${index}].id`);
  const tSeconds = asNumber(record.t_seconds, `${id} t_seconds`);
  if (tSeconds < 0 || tSeconds > duration) {
    throw new Error(`${id} t_seconds is outside 0..${duration}`);
  }
  const recommended = record.recommended;
  if (!isAction(recommended)) {
    throw new Error(`${id} recommended must be pass, shoot, dribble, or hold`);
  }
  const secondary = asString(record.secondary_explain, `${id} secondary_explain`);
  if (!isSecondaryPassCopy(secondary)) {
    throw new Error(`${id} secondary_explain must be secondary pass copy and must not mention hold`);
  }
  const rationale = asString(record.system2_rationale, `${id} system2_rationale`);
  if (/[\r\n]/.test(rationale)) throw new Error(`${id} system2_rationale must be one line`);
  const playerValues = record.players;
  const arrowValues = record.arrows;
  if (!Array.isArray(playerValues) || playerValues.length === 0) {
    throw new Error(`${id} needs players`);
  }
  if (!Array.isArray(arrowValues)) throw new Error(`${id} arrows must be a list`);
  const players = playerValues.map((player, playerIndex) => asPlayer(player, id, playerIndex));
  const seen = new Set<string>();
  for (const player of players) {
    if (seen.has(player.id)) throw new Error(`${id} duplicates player ${player.id}`);
    seen.add(player.id);
  }
  if (players.filter((player) => player.possessor).length !== 1) {
    throw new Error(`${id} needs exactly one possessor`);
  }
  return {
    id,
    t_seconds: tSeconds,
    recommended,
    distribution: asDistribution(record.distribution, id),
    primary_explain: asString(record.primary_explain, `${id} primary_explain`),
    secondary_explain: secondary,
    system2_rationale: rationale,
    players,
    arrows: arrowValues.map((arrow, arrowIndex) => asArrow(arrow, id, arrowIndex)),
  };
}

export function parseFixture(input: unknown): Fixture {
  const data = asRecord(input, "fixture");
  if (data.schema_version !== 1) throw new Error("schema_version must be 1");
  const title = asString(data.title, "title");
  if (title !== "Inside the Game") throw new Error('title must be "Inside the Game"');
  const scheme = asString(data.scheme, "scheme");
  if (scheme !== "Scheme A") throw new Error('scheme must be "Scheme A"');
  const duration = asNumber(data.duration_seconds, "duration_seconds");
  if (duration <= 0) throw new Error("duration_seconds must be positive");
  const disclaimer = asString(data.disclaimer, "disclaimer");
  assertDisclaimer(disclaimer);
  if (!Array.isArray(data.moments) || data.moments.length === 0) {
    throw new Error("moments must be a non-empty list");
  }
  const moments = data.moments.map((moment, index) => asMoment(moment, index, duration));
  const ids = new Set<string>();
  for (const moment of moments) {
    if (ids.has(moment.id)) throw new Error(`duplicate moment id ${moment.id}`);
    ids.add(moment.id);
  }
  const initialId = asString(data.initial_moment_id, "initial_moment_id");
  if (!ids.has(initialId)) throw new Error("initial_moment_id does not match a moment");
  return {
    schema_version: 1,
    title,
    scheme,
    duration_seconds: duration,
    initial_moment_id: initialId,
    disclaimer,
    moments,
  };
}
