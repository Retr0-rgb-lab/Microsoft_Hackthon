import { arrowHeadPoints, PRIMARY_ARROW, shaftEnd } from "../display";
import type { Action } from "../types";

type ArrowGlyphProps = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  primary: boolean;
  kind: Action;
  head: number;
  width: number;
  halo: number;
  dash?: string;
  testId: string;
};

export function ArrowGlyph({
  x1,
  y1,
  x2,
  y2,
  primary,
  kind,
  head,
  width,
  halo,
  dash,
  testId,
}: ArrowGlyphProps) {
  const end = shaftEnd(x1, y1, x2, y2, head * 0.72);
  const color = primary ? PRIMARY_ARROW : "rgba(255,255,255,0.48)";
  const dashProps = dash ? { strokeDasharray: dash } : {};
  return (
    <g data-testid={testId} data-kind={kind} data-primary={primary ? "true" : "false"}>
      {halo > 0 ? (
        <line
          x1={x1}
          y1={y1}
          x2={end.x}
          y2={end.y}
          stroke="#1a1204"
          strokeWidth={width + halo}
          strokeLinecap="butt"
          {...dashProps}
        />
      ) : null}
      <line
        x1={x1}
        y1={y1}
        x2={end.x}
        y2={end.y}
        stroke={color}
        strokeWidth={width}
        strokeLinecap="butt"
        {...dashProps}
      />
      <polygon points={arrowHeadPoints(x1, y1, x2, y2, head)} fill={color} />
    </g>
  );
}
