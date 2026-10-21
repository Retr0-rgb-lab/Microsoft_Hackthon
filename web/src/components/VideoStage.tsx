import type { RefObject } from "react";
import { ArrowOverlay } from "./ArrowOverlay";
import { PitchBackdrop } from "./PitchBackdrop";
import type { Moment } from "../types";

type VideoStageProps = {
  moment: Moment;
  videoUrl: string | null;
  videoRef: RefObject<HTMLVideoElement | null>;
  stageRef: RefObject<HTMLDivElement | null>;
  onLoadedMetadata: () => void;
};

export function VideoStage({ moment, videoUrl, videoRef, stageRef, onLoadedMetadata }: VideoStageProps) {
  return (
    <div
      className="stage"
      ref={stageRef}
      data-testid="stage"
      data-plate={videoUrl ? "video" : "placeholder"}
      data-recommended={moment.recommended}
    >
      {videoUrl ? (
        <video
          ref={videoRef}
          className="plate"
          src={videoUrl}
          muted
          playsInline
          preload="auto"
          onLoadedMetadata={onLoadedMetadata}
        />
      ) : (
        <PitchBackdrop players={moment.players} />
      )}
      <ArrowOverlay moment={moment} />
    </div>
  );
}
