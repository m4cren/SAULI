"use client";

import { useKiosk } from "../_hooks/useKioskFlow";
import { wrongCompartment } from "../_data/mockKioskData";

export default function DesktopTestControls({ inModal = false }: { inModal?: boolean }) {
  const kiosk = useKiosk();
  const { screen, modal } = kiosk.state;
  if (modal && !inModal) return null;
  const controls: { label: string; action: () => void }[] = [];
  if (modal === "wrongPlacement") controls.push({ label: `Simulate item removed from ${wrongCompartment}`, action: kiosk.simulatePlacementRemoved });
  else if (modal === "wrongItem") controls.push({ label: "Simulate item returned", action: kiosk.simulateItemReturned });
  else if (modal === "cancel" || screen.mode === "home") return null;
  else if (screen.mode === "retrieve") return null;
  if (!controls.length) return null;
  return <details open={inModal || undefined} className={`group relative text-left ${inModal ? "mt-5 w-full" : ""}`}>
    <summary className="min-h-11 cursor-pointer list-none rounded-lg border border-dashed border-[#6a9999] bg-[#f1f8f7] px-3 py-2.5 text-sm font-semibold text-[#0b474f]">Hardware simulation</summary>
    <div className="mt-2 rounded-lg border border-[#9fc3c0] bg-white p-3 shadow-lg"><div className="grid gap-2">
      {controls.map(({ label, action }) => <button key={label} type="button" disabled={kiosk.busy} onClick={action} className="min-h-11 rounded-md border border-[#0b474f] px-3 py-2 text-left text-xs font-semibold text-[#0b474f]">{label}</button>)}
    </div>{kiosk.state.error && <p role="alert" className="mt-2 text-sm text-red-700">{kiosk.state.error}</p>}</div>
  </details>;
}
