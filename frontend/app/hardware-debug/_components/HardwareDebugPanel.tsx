"use client";

import { useEffect, useState } from "react";
import styles from "./HardwareDebugPanel.module.css";

type Connection = "online" | "stale" | "offline";
type Slot = { code: string; ready?: boolean; grams?: number | null; present?: boolean | null; calibrated?: boolean; light_command?: boolean; fault?: string | null };
type Unit = {
  unit_name: string; received_at: string; connection: Connection;
  doors: Record<string, { raw_level: number | null; door: string }>;
  outputs: Record<string, boolean>; lock_feedback: string;
  esp: { connection: Connection; frame_errors: number; error: string | null; slots: Slot[] };
  door_workflow?: { command_id?: string | null; door?: string | null; phase?: string; fault?: string | null };
  events: { at: string; kind: string; command_id?: string | null }[];
};
const codes = [...Array.from({ length: 8 }, (_, i) => `P-0${i + 1}`), ...Array.from({ length: 4 }, (_, i) => `M-0${i + 1}`)];

export default function HardwareDebugPanel() {
  const [mode, setMode] = useState<"live" | "simulation">("live");
  const [units, setUnits] = useState<Unit[]>([]);
  const [selected, setSelected] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [simDoors, setSimDoors] = useState({ pocket: false, medium: false });
  const [simSlots, setSimSlots] = useState<Record<string, boolean>>({});
  const [simLights, setSimLights] = useState<Record<string, boolean>>({});
  const [simEsp, setSimEsp] = useState(true);
  const [simBackend, setSimBackend] = useState(true);
  const [events, setEvents] = useState<string[]>([]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const response = await fetch("/api/hardware-debug", { cache: "no-store" });
        if (!response.ok) throw new Error();
        const data = await response.json();
        if (active) { setUnits(data.units || []); setError(""); }
      } catch {
        if (active) setError("Backend status is unavailable. Live controls are read-only.");
      } finally { if (active) setLoading(false); }
    };
    void load();
    const timer = setInterval(() => { void load(); }, 3000);
    return () => { active = false; clearInterval(timer); };
  }, []);

  const unit = units[selected];
  const log = (message: string) => setEvents((old) => [`${new Date().toLocaleTimeString()}  ${message}`, ...old].slice(0, 8));
  const slots = codes.map((code) => unit?.esp.slots.find((slot) => slot.code === code) || { code });
  const connection = mode === "simulation" ? (simBackend ? "Simulated online" : "Simulated offline") : error ? "Unavailable" : unit?.connection || "No telemetry";

  return <main className={styles.shell}>
    <header className={styles.header}><strong>SAULI / Hardware Debug</strong><span>{mode === "simulation" ? "LOCAL SIMULATION · NO HARDWARE CONTROL" : "PUBLIC LIVE VIEW · READ ONLY"}</span></header>
    <div className={styles.content}>
      <div className={styles.toolbar} role="group" aria-label="Diagnostics mode">
        <button aria-pressed={mode === "live"} onClick={() => setMode("live")}>Live view</button>
        <button aria-pressed={mode === "simulation"} onClick={() => setMode("simulation")}>Simulation</button>
        {mode === "live" && units.length > 1 && <select aria-label="SAULI unit" value={selected} onChange={(e) => setSelected(Number(e.target.value))}>{units.map((row, i) => <option key={i} value={i}>{row.unit_name}</option>)}</select>}
      </div>
      {mode === "live" && <p className={styles.note} role="status">{loading ? "Connecting to backend…" : error || (unit ? `Last update: ${new Date(unit.received_at).toLocaleString()}. Commands show requested output state, not mechanical confirmation.` : "No physical device telemetry yet. Check the Pi service and backend migration.")}</p>}
      {mode === "simulation" && <p className={styles.note}>Every value below is simulated in this browser. Nothing is sent to GPIO, UART, or production occupancy.</p>}

      <section className={styles.cards} aria-label="Connections and doors">
        <article className={styles.card}><h2>Backend</h2><strong>{connection}</strong></article>
        <article className={styles.card}><h2>Raspberry Pi</h2><strong>{mode === "simulation" ? "Simulated connected" : unit?.connection || "Unavailable"}</strong></article>
        <article className={styles.card}><h2>ESP32-S3</h2><strong>{mode === "simulation" ? (simEsp ? "Simulated connected" : "Simulated disconnected") : unit?.esp.connection || "Unavailable"}</strong></article>
        {(["medium", "pocket"] as const).map((door) => <article className={styles.card} key={door}><h2>{door === "medium" ? "Medium door · BCM8" : "Pocket door · BCM7"}</h2><strong>{mode === "simulation" ? (simDoors[door] ? "Open" : "Closed") : unit?.doors[door]?.door || "Unknown"}</strong><small>Raw level: {mode === "simulation" ? (simDoors[door] ? "HIGH" : "LOW") : unit?.doors[door]?.raw_level === null || unit?.doors[door]?.raw_level === undefined ? "Unavailable" : unit.doors[door].raw_level ? "HIGH" : "LOW"}</small></article>)}
      </section>

      <div className={styles.columns}>
        <section className={styles.card}><h2>Compartment sensors (12)</h2><div className={styles.grid}>{slots.map((slot) => {
          const present = mode === "simulation" ? !!simSlots[slot.code] : slot.present;
          const ready = mode === "simulation" ? simEsp : unit?.connection === "online" && unit.esp.connection === "online" && slot.ready;
          return <div className={styles.slot} key={slot.code}><strong>{slot.code}</strong><span>{!ready ? "Sensor unavailable" : present === null || present === undefined ? "Presence unknown" : present ? "Item detected" : "Empty"}</span><small>{mode === "simulation" ? "Simulated" : slot.calibrated && slot.grams !== null && slot.grams !== undefined ? `${slot.grams.toFixed(1)} g` : "Weight uncalibrated"}</small><small>Light command: {mode === "simulation" ? simLights[slot.code] ? "on" : "off" : slot.light_command ? "on" : "off"}</small></div>;
        })}</div></section>
        <aside className={styles.stack}>
          <section className={styles.card}><h2>Output commands</h2>{["main_light", "buzzer", "pocket_solenoid", "medium_solenoid", "pocket_light_gate", "medium_light_gate"].map((name) => <div className={styles.row} key={name}><span>{name.replaceAll("_", " ")}</span><strong>{mode === "simulation" ? "Simulated off" : unit?.outputs[name] ? "On" : "Off"}</strong></div>)}<p className={styles.muted}>Lock feedback: unavailable. Door contact is separate from lock status.</p>{mode === "live" && unit?.door_workflow && <><h3>Door workflow</h3><div className={styles.row}><span>{unit.door_workflow.door || "No door"}</span><strong>{unit.door_workflow.phase?.replaceAll("_", " ") || "idle"}</strong></div>{unit.door_workflow.command_id && <p className={styles.muted}>Command {unit.door_workflow.command_id.slice(0, 8)}{unit.door_workflow.fault ? ` · ${unit.door_workflow.fault.replaceAll("_", " ")}` : ""}</p>}</>}</section>
          {mode === "simulation" && <section className={styles.card}><h2>Local simulation controls</h2><div className={styles.controls}><button onClick={() => { setSimDoors((s) => ({...s, pocket: !s.pocket})); log("Pocket magnet changed"); }}>Toggle pocket magnet</button><button onClick={() => { setSimDoors((s) => ({...s, medium: !s.medium})); log("Medium magnet changed"); }}>Toggle medium magnet</button><button onClick={() => { setSimEsp((s) => !s); log("ESP link changed"); }}>Toggle ESP link</button><button onClick={() => { setSimBackend((s) => !s); log("Backend link changed"); }}>Toggle backend link</button><label>Compartment <select id="sim-slot" defaultValue="P-01">{codes.map((code) => <option key={code}>{code}</option>)}</select></label><button onClick={() => { const code = (document.getElementById("sim-slot") as HTMLSelectElement).value; setSimSlots((s) => ({...s, [code]: !s[code]})); log(`${code} item presence changed`); }}>Place / remove item</button><button onClick={() => { const code = (document.getElementById("sim-slot") as HTMLSelectElement).value; setSimLights((s) => ({...s, [code]: !s[code]})); log(`${code} light command changed`); }}>Toggle light command</button></div></section>}
          <section className={styles.card}><h2>Event feed</h2>{mode === "simulation" ? (events.length ? events.map((item, i) => <p key={i} className={styles.event}>{item}</p>) : <p className={styles.muted}>No simulated events yet.</p>) : unit?.events?.length ? unit.events.map((item, i) => <p key={`${item.at}-${i}`} className={styles.event}>{new Date(item.at).toLocaleTimeString()} {item.kind.replaceAll("_", " ")}{item.command_id ? ` / command ${item.command_id.slice(0, 8)}` : ""}</p>) : <p className={styles.muted}>No recent device events. Raw logs and item data are unavailable here.</p>}</section>
        </aside>
      </div>
    </div>
  </main>;
}
