import { ArrowGlyph } from "./ArrowGlyph";
import { arrowsForDisplay, FRAME_H, FRAME_W, PRIMARY_ARROW } from "../display";
import type { Moment } from "../types";

type ArrowOverlayProps = {
  moment: Moment;
};

export function ArrowOverlay({ moment }: ArrowOverlayProps) {
  const arrows = arrowsForDisplay(moment.recommended, moment.arrows);
  const possessor = moment.players.find((player) => player.possessor);
  const paint = [...arrows].sort((a, b) => Number(a.primary) - Number(b.primary));
  return (
    <svg
      className="arrow-svg"
      viewBox={`0 0 ${FRAME_W} ${FRAME_H}`}
      preserveAspectRatio="xMidYMid slice"
      data-testid="arrow-layer"
      data-count={arrows.length}
    >
      {possessor ? (
        <circle
          data-testid="possessor-ring"
          cx={possessor.frame.x * FRAME_W}
          cy={possessor.frame.y * FRAME_H}
          r={20}
          fill="rgba(255,229,0,0.22)"
          stroke={PRIMARY_ARROW}
          strokeWidth={4}
        />
      ) : null}
      {paint.map((arrow, index) => (
        <ArrowGlyph
          key={`${arrow.kind}-${index}-${arrow.primary}`}
          x1={arrow.from_frame.x * FRAME_W}
          y1={arrow.from_frame.y * FRAME_H}
          x2={arrow.to_frame.x * FRAME_W}
          y2={arrow.to_frame.y * FRAME_H}
          primary={arrow.primary}
          kind={arrow.kind}
          head={arrow.primary ? 26 : 14}
          width={arrow.primary ? 10 : 3.5}
          halo={arrow.primary ? 3.5 : 0}
          dash={arrow.kind === "dribble" ? "18 12" : undefined}
          testId={arrow.primary ? "arrow-primary" : "arrow-secondary"}
        />
      ))}
    </svg>
  );
}
