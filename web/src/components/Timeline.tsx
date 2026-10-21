import { formatClock } from "../display";
import type { Moment } from "../types";
import { IconFullscreen, IconPause, IconPlay } from "./icons";

type TimelineProps = {
  t: number;
  duration: number;
  moments: readonly Moment[];
  activeId: string;
  playing: boolean;
  onTogglePlay: () => void;
  onSeek: (t: number) => void;
  onFullscreen: () => void;
};

export function Timeline({
  t,
  duration,
  moments,
  activeId,
  playing,
  onTogglePlay,
  onSeek,
  onFullscreen,
}: TimelineProps) {
  const progress = duration > 0 ? Math.min(100, Math.max(0, (t / duration) * 100)) : 0;
  return (
    <div className="timeline">
      <button type="button" className="play" data-testid="play" aria-label={playing ? "Pause" : "Play"} onClick={onTogglePlay}>
        {playing ? <IconPause /> : <IconPlay />}
      </button>
      <div className="track-wrap">
        <input
          data-testid="scrubber"
          type="range"
          min={0}
          max={duration}
          step={1}
          value={Math.round(t)}
          aria-label="Match clock"
          style={{ ["--progress" as string]: `${progress}%` }}
          onChange={(event) => onSeek(Number(event.target.value))}
        />
        {moments.map((moment) => {
          const left = duration > 0 ? (moment.t_seconds / duration) * 100 : 0;
          const active = moment.id === activeId;
          return (
            <button
              key={moment.id}
              type="button"
              className={active ? "diamond is-active" : "diamond"}
              style={{ left: `${left}%` }}
              data-testid={`moment-${moment.id}`}
              aria-label={`Possession at ${formatClock(moment.t_seconds)}`}
              aria-pressed={active}
              onClick={() => onSeek(moment.t_seconds)}
            />
          );
        })}
        <span className="tick-label start">0:00</span>
        {moments.map((moment) => (
          <span
            key={`${moment.id}-label`}
            className={moment.id === activeId ? "tick-label is-active" : "tick-label"}
            style={{ left: `${(moment.t_seconds / duration) * 100}%` }}
          >
            {formatClock(moment.t_seconds)}
          </span>
        ))}
      </div>
      <div className="clock" data-testid="clock">
        <span className="clock-now">{formatClock(t)}</span>
        <span className="clock-dur"> / {formatClock(duration)}</span>
      </div>
      <button type="button" className="fullscreen" aria-label="Fullscreen" onClick={onFullscreen}>
        <IconFullscreen />
      </button>
    </div>
  );
}
