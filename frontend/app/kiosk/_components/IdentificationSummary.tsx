"use client";

import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import FlowHeading from "./FlowHeading";
import ProcessingScreen from "./ProcessingScreen";
import { mediumCodes, pocketCodes } from "@/libs/storage/slots";

export default function IdentificationSummary() {
  const kiosk = useKiosk();
  const { review, foundLocation, storageSize } = kiosk.state;
  if (kiosk.busy) return <ProcessingScreen kind="storage" />;
  const summaryMentionsLocation = foundLocation.trim() && review.summary.toLowerCase().includes(foundLocation.trim().toLowerCase());
  return <><FlowHeading flow="found" current={2} title="Item is identified" subtitle="Review the recommended size before unlocking the storage door." />
    <div className="kiosk-grid"><div className="flex min-w-0 flex-col gap-3"><section className="kiosk-card flex flex-1 flex-col p-4 sm:p-5"><span className="kiosk-pill w-fit">✓ READY TO STORE</span><h2 className="mt-3 text-[clamp(20px,2.4vw,30px)] font-bold leading-tight">{review.name}</h2><p className="mt-2 text-sm leading-snug text-[#4a5a63]">{review.summary}</p>{!summaryMentionsLocation && foundLocation.trim() && <p className="mt-1 text-sm">Found at {foundLocation.trim()}.</p>}
      <div className="mt-2 flex flex-wrap gap-2">{[review.category, review.color, review.material].filter(Boolean).map((value, index) => <span key={`${index}-${value}`} className="max-w-full rounded-md bg-[#d9efed] px-2 py-1 text-xs font-bold text-[#0b474f]">{value}</span>)}</div>
      <div className="mt-auto grid gap-2 pt-3 text-sm"><div className="flex items-center justify-between gap-2 border-t border-[#d4e1e2] pt-2"><label htmlFor="storage-size">Recommended size</label><select id="storage-size" value={storageSize ?? ""} onChange={(event) => kiosk.setStorageSize(event.target.value as "pocket" | "medium")} className="min-h-12 rounded-lg border border-[#9bb7ba] bg-white px-2 font-bold"><option value="" disabled>No suggestion</option><option value="pocket">Pocket-size</option><option value="medium">Medium-size</option></select></div><div className="flex justify-between border-t border-[#d4e1e2] pt-2"><span>Available positions</span><strong>{storageSize ? kiosk.availableCount ?? (kiosk.availabilityError ? "Unavailable" : "Checking…") : "—"}</strong></div><div className="flex justify-between border-t border-[#d4e1e2] pt-2"><span>Assigned position</span><strong>Assigned on confirmation</strong></div></div></section>
      {kiosk.availabilityError && <p role="alert" className="text-sm text-amber-800">Live availability could not be checked. Confirmation will check again.</p>}{kiosk.state.error && <p role="alert" className="text-sm text-red-700">{kiosk.state.error}</p>}
      <div className="grid grid-cols-[1.5fr_1fr] gap-2"><Button type="button" onClick={kiosk.confirmFound} disabled={!storageSize || kiosk.availableCount === 0} className="kiosk-button kiosk-button-primary">Confirm and Save Item</Button><Button type="button" variant="outline" onClick={kiosk.requestCancel} className="kiosk-button">Cancel</Button></div>
    </div><section className="kiosk-card bg-gradient-to-b from-[#0b474f] to-[#245e64] p-4 text-white"><h2 className="text-lg font-bold">Container availability</h2><div className="mt-2 grid grid-cols-[1.2fr_.8fr] gap-3">{(["pocket", "medium"] as const).map((size) => <div key={size} className={`rounded-xl border p-3 ${storageSize === size ? "border-[#67e5d9]" : "border-white/30"}`}><h3 className="mb-2 text-sm font-semibold">{size === "pocket" ? "Pocket-size (P)" : "Medium-size (M)"}</h3><div className={`grid gap-1 ${size === "pocket" ? "grid-cols-2" : "grid-cols-1"}`}>{(size === "pocket" ? pocketCodes : mediumCodes).map((code) => <div key={code} className="flex min-h-10 items-center justify-center rounded-md bg-white/90 text-sm font-semibold text-[#0b474f]">{code}</div>)}</div><p className="mt-2 text-sm"><strong>{kiosk.availability[size]?.available ?? "—"}</strong> available</p></div>)}</div><p className="mt-3 text-xs text-white/80">The actual position is assigned by SAULI when you confirm.</p></section></div>
  </>;
}
