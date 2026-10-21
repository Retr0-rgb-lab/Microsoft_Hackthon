import { ArrowGlyph } from "./ArrowGlyph";
import { arrowsForDisplay } from "../display";
import type { Moment } from "../types";

type MiniPitchProps = {
  moment: Moment;
};

export function MiniPitch({ moment }: MiniPitchProps) {
  const arrows = arrowsForDisplay(moment.recommended, moment.arrows);
  const paint = [...arrows].sort((a, b) => Number(a.primary) - Number(b.primary));
  return (
    <svg
      className="minimap"
      viewBox="-2 -2 109 72"
      role="img"
      aria-label="Mini pitch with the same arrows as the video"
      data-testid="minimap"
    >
      <rect x="0.4" y="0.4" width="104.2" height="67.2" fill="none" stroke="#ffffff" strokeWidth="0.7" />
      <line x1="52.5" y1="0" x2="52.5" y2="68" stroke="#ffffff" strokeWidth="0.55" />
      <circle cx="52.5" cy="34" r="9.15" fill="none" stroke="#ffffff" strokeWidth="0.55" />
      <rect x="0" y="13.84" width="16.5" height="40.32" fill="none" stroke="#ffffff" strokeWidth="0.55" />
      <rect x="88.5" y="13.84" width="16.5" height="40.32" fill="none" stroke="#ffffff" strokeWidth="0.55" />
      <rect x="0" y="24.84" width="5.5" height="18.32" fill="none" stroke="#ffffff" strokeWidth="0.55" />
      <rect x="99.5" y="24.84" width="5.5" height="18.32" fill="none" stroke="#ffffff" strokeWidth="0.55" />
      {moment.players.map((player) => (
        <g key={player.id}>
          {player.possessor ? (
            <circle cx={player.pitch.x} cy={player.pitch.y} r="2.7" fill="rgba(255,229,0,0.35)" stroke="#FFE500" strokeWidth="0.55" />
          ) : null}
          <circle
            cx={player.pitch.x}
            cy={player.pitch.y}
            r="1.25"
            fill={player.team === "home" ? "#f4f7fb" : "#e7a3ad"}
          />
        </g>
      ))}
      {paint.map((arrow, index) => (
        <ArrowGlyph
          key={`${arrow.kind}-${index}-${arrow.primary}`}
          x1={arrow.from_pitch.x}
          y1={arrow.from_pitch.y}
          x2={arrow.to_pitch.x}
          y2={arrow.to_pitch.y}
          primary={arrow.primary}
          kind={arrow.kind}
          head={arrow.primary ? 3.4 : 2.4}
          width={arrow.primary ? 1.15 : 0.7}
          halo={arrow.primary ? 0.9 : 0}
          dash={arrow.kind === "dribble" ? "2.2 1.5" : undefined}
          testId={arrow.primary ? "minimap-arrow-primary" : "minimap-arrow-secondary"}
        />
      ))}
    </svg>
  );
}
