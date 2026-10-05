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
  else if (modal === "cancel") return null;
  else if (screen.mode === "home") controls.push({ label: "Simulate no available compartments", action: kiosk.simulateNoSlots });
  else if (screen.mode === "found" && screen.step === "placement") controls.push({ label: "Simulate wrong placement", action: kiosk.simulateWrongPlacement }, { label: "Simulate correct placement", action: kiosk.simulateCorrectPlacement });
  else if (screen.mode === "found" && screen.step === "placementCorrect") controls.push({ label: "Simulate door closed", action: kiosk.simulateDoorClosed });
  else if (screen.mode === "retrieve" && (screen.step === "uploadQr" || screen.step === "verifyingQr")) controls.push({ label: "Simulate valid QR", action: () => kiosk.simulateQr("valid") }, { label: "Simulate invalid QR", action: () => kiosk.simulateQr("invalid") });
  else if (screen.mode === "retrieve" && screen.step === "itemLocation") controls.push({ label: "Simulate wrong item retrieved", action: kiosk.simulateWrongItem }, { label: "Simulate correct item retrieved", action: kiosk.simulateCorrectItem });
  if (screen.mode !== "home" && !modal) controls.push({ label: "Reset kiosk", action: kiosk.requestCancel });
  if (!controls.length) return null;
  return <details open={inModal || undefined} className={`group relative text-left ${inModal ? "mt-5 w-full" : ""}`}><summary className="min-h-11 cursor-pointer list-none rounded-lg border border-dashed border-[#6a9999] bg-[#f1f8f7] px-3 py-2.5 text-sm font-semibold text-[#0b474f] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0b474f]">Desktop test controls <span aria-hidden="true">▾</span></summary><div className={`${inModal ? "mt-2 w-full" : "absolute right-0 top-12 z-30 w-max max-w-[min(92vw,320px)]"} rounded-lg border border-[#9fc3c0] bg-white p-3 shadow-lg`}><p className="mb-2 text-xs text-[#555]">Frontend simulation only. No hardware or backend is connected.</p><div className="grid gap-2">{controls.map(({ label, action }) => <button key={label} type="button" onClick={(event) => { event.currentTarget.closest("details")?.removeAttribute("open"); action(); }} className="min-h-11 rounded-md border border-[#0b474f] px-3 py-2 text-left text-xs font-semibold text-[#0b474f] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0b474f]">{label}</button>)}</div></div></details>;
}
