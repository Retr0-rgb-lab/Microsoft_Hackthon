import { toPitchSvg } from "./geometry";
import { pointAlong } from "./geometry";
import type { ActionClass, DecideFromTracking, PitchPoint } from "./types";
import { ranked } from "./types";

const ACTUAL = "#241433";
const HYPO = "#7c3aed";

export type DiagramPlayer = {
  team: "HOME" | "AWAY";
  x: number;
  y: number;
  carrier: boolean;
};

export function diagramMarkup(input: {
  players: readonly DiagramPlayer[];
  ball: { x: number; y: number } | null;
  decide: DecideFromTracking | null;
  showArrows: boolean;
  emphasize: ActionClass | null;
  preview: { action: ActionClass; t: number } | null;
}): string {
  const parts: string[] = [
    `<rect x="0" y="0" width="105" height="68" fill="#f6f1ff"/>`,
    `<rect x="0.4" y="0.4" width="104.2" height="67.2" fill="none" stroke="#d9c8f5" stroke-width="0.45"/>`,
    `<line x1="52.5" y1="0" x2="52.5" y2="68" stroke="#d9c8f5" stroke-width="0.35"/>`,
    `<circle cx="52.5" cy="34" r="9.15" fill="none" stroke="#d9c8f5" stroke-width="0.35"/>`,
    `<line x1="0" y1="30.34" x2="0" y2="37.66" stroke="#241433" stroke-width="0.7"/>`,
    `<line x1="105" y1="30.34" x2="105" y2="37.66" stroke="#241433" stroke-width="0.7"/>`,
  ];
  for (const player of input.players) {
    const [sx, sy] = toPitchSvg(player.x, player.y);
    const fill = player.team === "HOME" ? "#2f6fed" : "#f07a3a";
    parts.push(`<circle cx="${sx}" cy="${sy}" r="${player.carrier ? 1.7 : 1.15}" fill="${fill}"/>`);
    if (player.carrier) {
      parts.push(`<circle cx="${sx}" cy="${sy}" r="2.5" fill="none" stroke="#6d28d9" stroke-width="0.45"/>`);
    }
  }
  if (input.ball) {
    const [bx, by] = toPitchSvg(input.ball.x, input.ball.y);
    parts.push(`<circle cx="${bx}" cy="${by}" r="0.7" fill="#fffaf3" stroke="#241433" stroke-width="0.25"/>`);
  }
  if (input.showArrows && input.decide) {
    for (const action of ranked(input.decide)) {
      const dashed = action.action !== input.decide.actual_action;
      const color = dashed ? HYPO : ACTUAL;
      const width = input.emphasize === action.action ? 1.45 : dashed ? 0.75 : 1.2;
      const marker = dashed ? "url(#mk-hypo)" : "url(#mk-actual)";
      if (action.action === "hold" || !action.geometry) {
        const at = carrierPoint(input);
        if (!at) continue;
        const [hx, hy] = toPitchSvg(at[0], at[1]);
        const dash = dashed ? ` stroke-dasharray="1.2 0.9"` : "";
        parts.push(
          `<circle cx="${hx}" cy="${hy}" r="3.1" fill="none" stroke="${color}" stroke-width="${width}"${dash}/>`,
        );
        continue;
      }
      const points = action.geometry.path.map(([x, y]) => toPitchSvg(x, y).join(" ")).join(" ");
      const dash = dashed ? ` stroke-dasharray="3.6 2.3"` : "";
      parts.push(
        `<polyline points="${points}" fill="none" stroke="${color}" stroke-width="${width}" stroke-linejoin="round" stroke-linecap="round" marker-end="${marker}"${dash}><title>${action.action}</title></polyline>`,
      );
    }
    if (input.preview && input.decide) {
      const action = ranked(input.decide).find((item) => item.action === input.preview?.action);
      const path = action?.geometry?.path;
      if (path && path.length > 0) {
        const [gx, gy] = toPitchSvg(...pointAlong(path, input.preview.t));
        parts.push(`<circle cx="${gx}" cy="${gy}" r="1.15" fill="#c4b5fd" stroke="#5b21b6" stroke-width="0.3"/>`);
      }
    }
  }
  return `${markers()}${parts.join("")}`;
}

function carrierPoint(input: { players: readonly DiagramPlayer[]; decide: DecideFromTracking | null }): PitchPoint | null {
  const carrier = input.players.find((player) => player.carrier);
  if (carrier) return [carrier.x, carrier.y];
  for (const action of input.decide ? ranked(input.decide) : []) {
    const start = action.geometry?.path[0];
    if (start) return start;
  }
  return null;
}

function markers(): string {
  return `<defs><marker id="mk-actual" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto"><path d="M0 0 L5 2.5 L0 5 Z" fill="${ACTUAL}"/></marker><marker id="mk-hypo" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto"><path d="M0 0 L5 2.5 L0 5 Z" fill="${HYPO}"/></marker></defs>`;
}
