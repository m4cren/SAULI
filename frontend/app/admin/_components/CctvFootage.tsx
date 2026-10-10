"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import AdminIcon from "./AdminIcon";
import AdminPageHeader from "./AdminPageHeader";
import { hasPrototypeFootage } from "../_data/mockAdminData";

interface Selection { camera: string; date: string; start: string; duration: number; }
type LoadState = "idle" | "loading" | "ready" | "missing";
const cameras = [
  { id: "front", name: "Camera 01 · Kiosk Front" },
  { id: "rear", name: "Camera 02 · Cabinet Rear" },
];
const durations = [5, 10, 15, 30];
const timeLabel = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

export default function CctvFootage() {
  const [camera, setCamera] = useState("");
  const [date, setDate] = useState("");
  const [start, setStart] = useState("");
  const [duration, setDuration] = useState("");
  const [selection, setSelection] = useState<Selection | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [playing, setPlaying] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [volume, setVolume] = useState(75);
  const [lastVolume, setLastVolume] = useState(75);
  const [speed, setSpeed] = useState(1);
  const playerRef = useRef<HTMLDivElement>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timeoutRef.current) clearTimeout(timeoutRef.current); }, []);
  useEffect(() => {
    if (!playing || !selection || loadState !== "ready") return;
    const id = window.setInterval(() => setSeconds((current) => {
      const next = Math.min(selection.duration * 60, current + speed);
      if (next >= selection.duration * 60) setPlaying(false);
      return next;
    }), 1000);
    return () => window.clearInterval(id);
  }, [playing, selection, speed, loadState]);
  const load = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!camera || !date || !start || !duration) return;
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    const next = { camera, date, start, duration: Number(duration) };
    setSelection(next); setPlaying(false); setSeconds(0); setLoadState("loading");
    timeoutRef.current = setTimeout(() => setLoadState(hasPrototypeFootage(camera, date, start) ? "ready" : "missing"), 650);
  };
  const changeSelection = () => { setPlaying(false); setLoadState("idle"); setSelection(null); };
  const total = (selection?.duration ?? 0) * 60;
  const recordedAt = selection ? new Date(`${selection.date}T${selection.start}:00+08:00`) : null;
  const recordedText = recordedAt ? new Intl.DateTimeFormat("en-PH", { timeZone: "Asia/Manila", month: "long", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true }).format(recordedAt) : "";
  return <>
    <AdminPageHeader title="CCTV Footage" description="Select archived footage using a camera, date, and timestamp." />
    <form className="admin-card admin-cctv-form" onSubmit={load}>
      <label><span>Camera</span><select value={camera} onChange={(event) => setCamera(event.target.value)} required><option value="">Select camera</option>{cameras.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label><span>Date</span><input type="date" value={date} onChange={(event) => setDate(event.target.value)} required /></label>
      <label><span>Start time</span><input type="time" value={start} onChange={(event) => setStart(event.target.value)} required /></label>
      <label><span>Duration</span><select value={duration} onChange={(event) => setDuration(event.target.value)} required><option value="">Select duration</option>{durations.map((value) => <option key={value} value={value}>{value} minutes</option>)}</select></label>
      <button type="submit" className="admin-primary" disabled={!camera || !date || !start || !duration || loadState === "loading"}><AdminIcon name="play" size={18} />{loadState === "loading" ? "Loading sample…" : "Load Footage"}</button>
    </form>
    <p className="admin-cctv-hint">Prototype archive: choose Camera 01, September 8, 2026, at 3:30 PM to preview sample footage. Other selections demonstrate the empty state.</p>
    {loadState === "idle" && <div className="admin-card admin-cctv-empty"><AdminIcon name="camera" size={42} /><h2>Select footage to begin</h2><p>Choose a camera, date, start time, and duration above. Nothing plays automatically.</p></div>}
    {loadState === "loading" && <div className="admin-card admin-cctv-empty" role="status"><span className="admin-loader" aria-hidden="true" /><h2>Loading prototype footage…</h2><p>Preparing a local demonstration preview.</p></div>}
    {loadState === "missing" && <div className="admin-card admin-cctv-empty" role="status"><AdminIcon name="camera" size={42} /><h2>No archived footage found</h2><p>No recording is available for the selected camera, date, and time.</p><button type="button" className="admin-secondary" onClick={changeSelection}>Change selection</button></div>}
    {loadState === "ready" && selection && <section className="admin-card admin-player" ref={playerRef} aria-label="Prototype footage player">
      <div className="admin-player-heading"><span className="admin-player-camera-icon"><AdminIcon name="camera" size={22} /></span><div><strong>{cameras.find((item) => item.id === selection.camera)?.name}</strong><small>{recordedText} · prototype footage</small></div><span className="admin-quality">1080p · simulated</span></div>
      <div className="admin-video-poster"><div className="admin-video-overlay">CAM 01 · PROTOTYPE FOOTAGE</div><div className="admin-cabinet-illustration" aria-hidden="true"><div className="admin-cabinet-left"><i /><i /><i /><i /></div><div className="admin-cabinet-right"><i /><i /></div><div className="admin-cabinet-kiosk"><span /><b /></div></div><div className="admin-video-timestamp">{recordedText}<br />{timeLabel(seconds)} / {timeLabel(total)}</div>{!playing && <button type="button" className="admin-poster-play" onClick={() => { if (seconds >= total) setSeconds(0); setPlaying(true); }} aria-label="Play prototype footage"><AdminIcon name="play" size={28} /></button>}</div>
      <div className="admin-player-controls"><label className="admin-timeline-label"><span className="admin-sr-only">Playback position</span><input type="range" min="0" max={total} value={seconds} onChange={(event) => setSeconds(Number(event.target.value))} /></label><div className="admin-player-time"><span>{timeLabel(seconds)}</span><span>{timeLabel(total)}</span></div><div className="admin-control-row"><div><button type="button" className="admin-icon-button" onClick={() => setSeconds((value) => Math.max(0, value - 10))} aria-label="Rewind 10 seconds">↶</button><button type="button" className="admin-icon-button emphasized" onClick={() => { if (seconds >= total) setSeconds(0); setPlaying(!playing); }} aria-label={playing ? "Pause" : "Play"}><AdminIcon name={playing ? "pause" : "play"} size={18} /></button><button type="button" className="admin-icon-button" onClick={() => setSeconds((value) => Math.min(total, value + 10))} aria-label="Forward 10 seconds">↷</button><button type="button" className="admin-icon-button" onClick={() => { if (volume) { setLastVolume(volume); setVolume(0); } else setVolume(lastVolume || 75); }} aria-label={volume ? "Mute" : "Unmute"}><AdminIcon name={volume ? "volume" : "mute"} size={18} /></button><label className="admin-volume"><span className="admin-sr-only">Volume</span><input type="range" min="0" max="100" value={volume} onChange={(event) => setVolume(Number(event.target.value))} /></label><span className="admin-current-time">{timeLabel(seconds)} / {timeLabel(total)}</span></div><div><label className="admin-speed"><span className="admin-sr-only">Playback speed</span><select value={speed} onChange={(event) => setSpeed(Number(event.target.value))}><option value="0.5">0.5×</option><option value="1">1×</option><option value="1.5">1.5×</option><option value="2">2×</option></select></label><button type="button" className="admin-icon-button" onClick={() => { if (document.fullscreenElement) document.exitFullscreen(); else playerRef.current?.requestFullscreen(); }} aria-label="Toggle fullscreen"><AdminIcon name="expand" size={18} /></button></div></div></div>
    </section>}
  </>;
}
