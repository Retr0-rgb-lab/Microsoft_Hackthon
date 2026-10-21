import { useCallback, useEffect, useRef, useState } from "react";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { Timeline } from "./components/Timeline";
import { VideoStage } from "./components/VideoStage";
import { momentAt, parseFixture } from "./display";
import type { Fixture } from "./types";

const MATCH_SECONDS_PER_REAL_SECOND = 240;

export function App() {
  const [fixture, setFixture] = useState<Fixture | null>(null);
  const [raw, setRaw] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [t, setT] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [videoEpoch, setVideoEpoch] = useState(0);
  const stageRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/scheme-a.json", { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Could not load scheme-a.json (${response.status})`);
        const text = await response.text();
        const parsed = parseFixture(JSON.parse(text) as unknown);
        setRaw(text);
        setFixture(parsed);
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Could not load scheme-a.json");
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!fixture) return;
    setT((prev) => {
      if (prev !== null) return prev;
      const initial = fixture.moments.find((moment) => moment.id === fixture.initial_moment_id);
      return initial ? initial.t_seconds : fixture.moments[0].t_seconds;
    });
  }, [fixture]);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search).get("video");
    if (query === "") return;
    const candidate = query || "/preview.mp4";
    let cancelled = false;
    const probe = document.createElement("video");
    probe.preload = "metadata";
    probe.muted = true;
    probe.onloadedmetadata = () => {
      if (!cancelled) setVideoUrl((prev) => prev ?? candidate);
    };
    probe.onerror = () => {};
    probe.src = candidate;
    return () => {
      cancelled = true;
      probe.removeAttribute("src");
      probe.load();
    };
  }, []);

  useEffect(() => {
    if (!playing || !fixture) return;
    let last = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      setT((prev) => {
        if (prev === null) return prev;
        return Math.min(fixture.duration_seconds, prev + dt * MATCH_SECONDS_PER_REAL_SECOND);
      });
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, fixture]);

  useEffect(() => {
    if (!fixture || t === null) return;
    if (t >= fixture.duration_seconds && playing) setPlaying(false);
  }, [t, fixture, playing]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !fixture || t === null || !videoUrl) return;
    if (!Number.isFinite(video.duration) || video.duration <= 0) return;
    const target = Math.min(video.duration, (t / fixture.duration_seconds) * video.duration);
    if (Math.abs(video.currentTime - target) > 0.2) video.currentTime = target;
  }, [t, fixture, videoUrl, videoEpoch]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== " " || event.repeat) return;
      const target = event.target;
      if (target instanceof HTMLElement) {
        const tag = target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "BUTTON") return;
      }
      event.preventDefault();
      setPlaying((value) => !value);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const onOpenVideo = useCallback((file: File) => {
    const url = URL.createObjectURL(file);
    setVideoUrl((prev) => {
      if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
      return url;
    });
  }, []);

  const onSave = useCallback(() => {
    if (!raw) return;
    const blob = new Blob([raw], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "scheme-a.json";
    link.click();
    URL.revokeObjectURL(url);
  }, [raw]);

  const onFullscreen = useCallback(() => {
    const stage = stageRef.current;
    if (!stage) return;
    if (document.fullscreenElement) {
      void document.exitFullscreen();
      return;
    }
    void stage.requestFullscreen();
  }, []);

  const moment = fixture && t !== null ? momentAt(fixture.moments, t) : null;

  return (
    <div className="app">
      <Header
        title={fixture?.title ?? "Inside the Game"}
        scheme={fixture?.scheme ?? "Scheme A"}
        saveDisabled={!raw}
        onOpenVideo={onOpenVideo}
        onSave={onSave}
      />
      {error ? (
        <p className="load-error" role="alert">
          {error}
        </p>
      ) : null}
      {moment && fixture && t !== null ? (
        <div className="workspace">
          <div className="stage-column">
            <VideoStage
              moment={moment}
              videoUrl={videoUrl}
              videoRef={videoRef}
              stageRef={stageRef}
              onLoadedMetadata={() => setVideoEpoch((value) => value + 1)}
            />
            <Timeline
              t={t}
              duration={fixture.duration_seconds}
              moments={fixture.moments}
              activeId={moment.id}
              playing={playing}
              onTogglePlay={() => setPlaying((value) => !value)}
              onSeek={setT}
              onFullscreen={onFullscreen}
            />
          </div>
          <Sidebar moment={moment} disclaimer={fixture.disclaimer} />
        </div>
      ) : error ? null : (
        <p className="loading">Loading the on-ball distribution…</p>
      )}
    </div>
  );
}
