import { FRAME_H, FRAME_W } from "../display";
import type { PlayerMark } from "../types";

const CROWD = Array.from({ length: 120 }, (_, index) => {
  const x = (index * 137) % 1000;
  const y = (index * 47) % 188 + 8;
  const radius = 2.2 + (index % 5);
  const fills = ["#7a2433", "#243044", "#4c1d38", "#1a1e2c", "#5c2430"];
  return { x, y, radius, fill: fills[index % fills.length] };
});

const BOARDS = [
  { x: 0, w: 110, fill: "#d71920" },
  { x: 110, w: 90, fill: "#f4f4f4" },
  { x: 200, w: 120, fill: "#141414" },
  { x: 320, w: 80, fill: "#1c8cdb" },
  { x: 400, w: 100, fill: "#c45c26" },
  { x: 500, w: 90, fill: "#241c4b" },
  { x: 590, w: 110, fill: "#0b8f4d" },
  { x: 700, w: 80, fill: "#f4f4f4" },
  { x: 780, w: 120, fill: "#c8102e" },
  { x: 900, w: 100, fill: "#1a1a1a" },
];

type PitchBackdropProps = {
  players: readonly PlayerMark[];
};

/** Illustrated plate used until a local preview file is loaded. */
export function PitchBackdrop({ players }: PitchBackdropProps) {
  return (
    <svg
      className="plate-svg"
      viewBox={`0 0 ${FRAME_W} ${FRAME_H}`}
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      <rect width={FRAME_W} height={FRAME_H} fill="#12060e" />
      {CROWD.map((dot, index) => (
        <circle key={index} cx={dot.x} cy={dot.y} r={dot.radius} fill={dot.fill} />
      ))}
      {BOARDS.map((board) => (
        <rect key={board.x} x={board.x} y={214} width={board.w} height={50} fill={board.fill} />
      ))}
      <defs>
        <clipPath id="grass-clip">
          <polygon points="60,268 940,268 1000,640 0,640" />
        </clipPath>
      </defs>
      <g clipPath="url(#grass-clip)">
        <rect x="0" y="260" width="1000" height="380" fill="#176b2e" />
        {Array.from({ length: 18 }, (_, index) => (
          <rect key={index} x={index * 56} y="260" width="28" height="380" fill="#1e7d38" />
        ))}
      </g>
      <polygon points="60,268 940,268 1000,640 0,640" fill="none" stroke="rgba(255,255,255,0.82)" strokeWidth="2" />
      <line x1="500" y1="268" x2="500" y2="640" stroke="rgba(255,255,255,0.82)" strokeWidth="2" />
      <ellipse cx="500" cy="430" rx="78" ry="34" fill="none" stroke="rgba(255,255,255,0.82)" strokeWidth="2" />
      <polygon points="60,300 168,300 210,470 18,470" fill="none" stroke="rgba(255,255,255,0.75)" strokeWidth="2" />
      <polygon points="940,300 832,300 790,470 982,470" fill="none" stroke="rgba(255,255,255,0.75)" strokeWidth="2" />
      {players.map((player) => (
        <circle
          key={player.id}
          cx={player.frame.x * FRAME_W}
          cy={player.frame.y * FRAME_H}
          r={8}
          fill={player.team === "home" ? "#f4f7fb" : "#c8102e"}
          stroke={player.team === "home" ? "#1d3557" : "#f7f7f7"}
          strokeWidth="1.6"
        />
      ))}
    </svg>
  );
}
