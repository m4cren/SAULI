"use client";

import { useState } from "react";
import AdminIcon from "./AdminIcon";
import AdminModal from "./AdminModal";
import AdminPageHeader from "./AdminPageHeader";
import CompartmentGrid from "./CompartmentGrid";
import HardwareStatusPanel from "./HardwareStatusPanel";
import { compartments, compartmentTotals, formatManilaDate, unrecognizedCaptures } from "../_data/mockAdminData";
import { markCaptureReviewed, setDoorUnlocked, type DoorId } from "../_lib/adminState";
import type { Compartment } from "../_types/admin";

const { available, occupied } = compartmentTotals(compartments);

export default function ContainerStatus() {
  const [selected, setSelected] = useState<Compartment | null>(null);
  const [unlocking, setUnlocking] = useState<DoorId | null>(null);
  const [unlockedDoors, setUnlockedDoors] = useState<DoorId[]>([]);
  const [showCaptures, setShowCaptures] = useState(false);
  const [captureIndex, setCaptureIndex] = useState(0);
  const [reviewed, setReviewed] = useState<string[]>([]);
  const capture = unrecognizedCaptures[captureIndex];
  const pending = unrecognizedCaptures.length - reviewed.length;
  return <>
    <AdminPageHeader title="Container Status" description="Monitor all pocket-size and medium-size compartments." action={<button type="button" className="admin-capture-trigger" onClick={() => { setCaptureIndex(0); setShowCaptures(true); }}><AdminIcon name="camera" size={20} /><span>Unrecognized captures</span><b>{pending} need review</b></button>} />
    <div className="admin-summary-row">
      <div className="admin-card admin-summary-card"><span className="admin-summary-icon green"><AdminIcon name="check" size={32} /></span><div><strong>Available</strong><b>{available}</b><small>Ready for item intake · sample data</small></div></div>
      <div className="admin-card admin-summary-card"><span className="admin-summary-icon gray"><AdminIcon name="box" size={31} /></span><div><strong>Occupied</strong><b>{occupied}</b><small>Items currently stored · sample data</small></div></div>
    </div>
    <div className="admin-status-layout"><CompartmentGrid compartments={compartments} onSelect={setSelected} /><HardwareStatusPanel unlockedDoors={unlockedDoors} onUnlock={setUnlocking} onRelock={(door) => setUnlockedDoors((items) => setDoorUnlocked(items, door, false))} /></div>
    {selected && <AdminModal title={selected.id} description="Compartment details · static sensor sample" onClose={() => setSelected(null)}>
      <div className={`admin-modal-status ${selected.status}`}>{selected.status === "occupied" ? "Occupied" : "Available"}<span>Sensor {selected.sensor.replace("_", " ")}</span></div>
      {selected.sensor !== "active" && <p className="admin-sensor-warning"><AdminIcon name="warning" size={18} /> Sensor {selected.sensor.replace("_", " ")}. Check this compartment before relying on its reading.</p>}
      <dl className="admin-detail-list"><div><dt>Size</dt><dd>{selected.size}</dd></div><div><dt>Weight sensor</dt><dd>{selected.weightGrams} g</dd></div><div><dt>Stored item</dt><dd>{selected.storedItem ?? "None"}</dd></div><div><dt>Last activity</dt><dd>{selected.lastActivity}</dd></div></dl>
      <button type="button" className="admin-primary admin-modal-done" onClick={() => setSelected(null)}>Done</button>
    </AdminModal>}
    {unlocking && <AdminModal title={`Unlock ${unlocking === "pocket-door" ? "pocket-size" : "medium-size"} door?`} description="Use this only when physical access is required." onClose={() => setUnlocking(null)}>
      <p className="admin-confirm-note">This is a frontend simulation. No command will be sent to the hardware.</p>
      <div className="admin-dialog-actions"><button type="button" className="admin-secondary" onClick={() => setUnlocking(null)}>Cancel</button><button type="button" className="admin-primary" onClick={() => { setUnlockedDoors((items) => setDoorUnlocked(items, unlocking, true)); setUnlocking(null); }}>Simulate unlock</button></div>
    </AdminModal>}
    {showCaptures && <AdminModal title="Unrecognized captures" description={`${pending} item${pending === 1 ? "" : "s"} need review · prototype records`} onClose={() => setShowCaptures(false)} className="admin-capture-modal">
      <div className="admin-capture-preview"><AdminIcon name="camera" size={43} /><span>Image placeholder · no image stored in this prototype</span></div>
      <div className="admin-capture-meta"><div><span>Capture {captureIndex + 1} of {unrecognizedCaptures.length}</span><strong>{capture.id} · {capture.title}</strong></div><p>{capture.reason}</p><dl><div><dt>Captured</dt><dd>{formatManilaDate(capture.timestamp, { month: "long" })}</dd></div><div><dt>Camera</dt><dd>{capture.source}</dd></div><div><dt>Confidence</dt><dd>{capture.confidence === undefined ? "Not available" : `${capture.confidence}%`}</dd></div><div><dt>Status</dt><dd>{reviewed.includes(capture.id) ? "Reviewed — simulated" : "Needs review"}</dd></div></dl></div>
      <div className="admin-capture-actions"><button type="button" className="admin-secondary" onClick={() => setCaptureIndex((index) => (index - 1 + unrecognizedCaptures.length) % unrecognizedCaptures.length)}><AdminIcon name="chevronLeft" size={16} /> Previous</button><button type="button" className="admin-secondary" onClick={() => setCaptureIndex((index) => (index + 1) % unrecognizedCaptures.length)}>Next <AdminIcon name="chevronRight" size={16} /></button><button type="button" className="admin-primary" disabled={reviewed.includes(capture.id)} onClick={() => setReviewed((items) => markCaptureReviewed(items, capture.id))}>{reviewed.includes(capture.id) ? "Reviewed" : "Mark as reviewed"}</button></div>
    </AdminModal>}
  </>;
}
