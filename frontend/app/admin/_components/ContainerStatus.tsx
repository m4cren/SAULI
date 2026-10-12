"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getStorageSlots, SauliApiError, type StorageSlot } from "@/libs/api/sauli";
import { slotTotals } from "@/libs/storage/slots";
import AdminIcon from "./AdminIcon";
import AdminModal from "./AdminModal";
import AdminPageHeader from "./AdminPageHeader";
import CompartmentGrid from "./CompartmentGrid";
import HardwareStatusPanel from "./HardwareStatusPanel";
import StoredItemImages from "./StoredItemImages";
import { setDoorUnlocked, type DoorId } from "../_lib/adminState";

export default function ContainerStatus() {
  const [slots, setSlots] = useState<StorageSlot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [unlocking, setUnlocking] = useState<DoorId | null>(null);
  const [unlockedDoors, setUnlockedDoors] = useState<DoorId[]>([]);
  const requestNumber = useRef(0);
  const accessDenied = useRef(false);
  const selected = slots.find((slot) => slot.code === selectedCode);

  const refresh = useCallback(async (force = false) => {
    if (accessDenied.current && !force) return;
    const request = ++requestNumber.current;
    try {
      const response = await getStorageSlots();
      if (request !== requestNumber.current) return;
      setSlots(response); setError(null); setLastUpdated(new Date());
    } catch (cause) {
      if (request !== requestNumber.current) return;
      if (cause instanceof SauliApiError && cause.status === 403) accessDenied.current = true;
      setError(cause instanceof Error ? cause.message : "Container status is unavailable.");
    } finally { if (request === requestNumber.current) setLoading(false); }
  }, []);

  useEffect(() => {
    const requests = requestNumber;
    const initial = window.setTimeout(() => { void refresh(); }, 0);
    const interval = window.setInterval(() => { void refresh(); }, 4000);
    const onFocus = () => { void refresh(); };
    const channel = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel("sauli-storage-slots") : null;
    if (channel) channel.onmessage = () => { void refresh(); };
    window.addEventListener("focus", onFocus);
    return () => { requests.current++; window.clearTimeout(initial); window.clearInterval(interval); window.removeEventListener("focus", onFocus); channel?.close(); };
  }, [refresh]);

  const { available, occupied, reserved } = slotTotals(slots);
  return <><AdminPageHeader title="Container Status" description="Monitor all pocket-size and medium-size compartments." />
    <p role="status" className="mb-3 text-sm text-[#426165]">{loading ? "Loading compartment status…" : error ? "Unable to refresh live status." : `Live slot data · updated ${lastUpdated?.toLocaleTimeString() ?? "just now"}`}</p>
    {error && <div role="alert" className="mb-4 rounded-lg border border-red-300 p-3 text-sm text-red-700">{error} <button type="button" onClick={() => { accessDenied.current = false; void refresh(true); }} className="ml-2 underline">Retry</button></div>}
    <div className="admin-summary-row"><div className="admin-card admin-summary-card"><span className="admin-summary-icon green"><AdminIcon name="check" size={32} /></span><div><strong>Available</strong><b>{available}</b><small>Ready for item intake</small></div></div><div className="admin-card admin-summary-card"><span className="admin-summary-icon gray"><AdminIcon name="box" size={31} /></span><div><strong>Occupied</strong><b>{occupied}</b><small>{reserved} reserved · {slots.length} total positions</small></div></div></div>
    <div className="admin-status-layout"><div>{!loading && !error && slots.length === 0 && <p className="admin-card p-5">No storage positions are configured.</p>}<CompartmentGrid compartments={slots} onSelect={(slot) => setSelectedCode(slot.code)} /></div><HardwareStatusPanel unlockedDoors={unlockedDoors} onUnlock={setUnlocking} onRelock={(door) => setUnlockedDoors((items) => setDoorUnlocked(items, door, false))} /></div>
    {selected && <AdminModal title={selected.code} description="Database compartment details" onClose={() => setSelectedCode(null)}><div className={`admin-modal-status ${selected.status}`}>{selected.status.replaceAll("_", " ")}</div>{selected.current_found_item_id && <StoredItemImages key={selected.current_found_item_id} itemId={selected.current_found_item_id} />}<dl className="admin-detail-list"><div><dt>Size</dt><dd>{selected.size_class === "pocket" ? "Pocket-size" : "Medium-size"}</dd></div><div><dt>Stored item</dt><dd>{selected.item_summary ?? "None"}</dd></div><div><dt>Reserved at</dt><dd>{selected.reserved_at ? new Date(selected.reserved_at).toLocaleString() : "—"}</dd></div><div><dt>Occupied at</dt><dd>{selected.occupied_at ? new Date(selected.occupied_at).toLocaleString() : "—"}</dd></div><div><dt>Last updated</dt><dd>{new Date(selected.updated_at).toLocaleString()}</dd></div></dl><button type="button" className="admin-primary admin-modal-done" onClick={() => setSelectedCode(null)}>Done</button></AdminModal>}
    {unlocking && <AdminModal title={`Unlock ${unlocking === "pocket-door" ? "pocket-size" : "medium-size"} door?`} description="Use this only when physical access is required." onClose={() => setUnlocking(null)}><p className="admin-confirm-note">This is a frontend simulation. No command will be sent to the hardware.</p><div className="admin-dialog-actions"><button type="button" className="admin-secondary" onClick={() => setUnlocking(null)}>Cancel</button><button type="button" className="admin-primary" onClick={() => { setUnlockedDoors((items) => setDoorUnlocked(items, unlocking, true)); setUnlocking(null); }}>Simulate unlock</button></div></AdminModal>}
  </>;
}
