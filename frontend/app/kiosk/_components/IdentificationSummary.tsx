"use client";

import Button from "@/app/components/Button";
import type { StorageSize } from "@/libs/storage/slots";
import { useKiosk } from "../_hooks/useKioskFlow";
import CompartmentMap from "./CompartmentMap";
import FlowHeading from "./FlowHeading";
import ProcessingScreen from "./ProcessingScreen";

export default function IdentificationSummary() {
  const kiosk = useKiosk();
  const { review, foundLocation, storageSize } = kiosk.state;
  if (kiosk.busy) return <ProcessingScreen kind="storage" />;

  const section = storageSize === "medium" ? "Medium-size" : "Pocket-size";
  const summaryMentionsLocation = foundLocation.trim() && review.summary.toLowerCase().includes(foundLocation.trim().toLowerCase());

  return <>
    <FlowHeading flow="found" current={2} title="Item is identified" subtitle="Review the detected size, then confirm to unlock the storage door." />
    <div className="kiosk-grid">
      <div className="flex min-w-0 flex-col gap-3">
        <section className="kiosk-card flex flex-1 flex-col p-4 sm:p-5">
          <span className="kiosk-pill w-fit">✓ READY TO STORE</span>
          <h2 className="mt-3 text-[clamp(20px,2.4vw,30px)] font-bold leading-tight">{review.name}</h2>
          <p className="mt-2 text-sm leading-snug text-[#4a5a63]">{review.summary}</p>
          {!summaryMentionsLocation && foundLocation.trim() && <p className="mt-1 text-sm">Found at {foundLocation.trim()}.</p>}
          <div className="mt-2 flex flex-wrap gap-2">
            {[review.category, review.color, review.material].filter(Boolean).map((value, index) =>
              <span key={`${index}-${value}`} className="max-w-full rounded-md bg-[#d9efed] px-2 py-1 text-xs font-bold text-[#0b474f]">{value}</span>)}
          </div>
          <div className="mt-auto grid gap-2 pt-3 text-sm">
            <div className="flex items-center justify-between gap-2 border-t border-[#d4e1e2] pt-2">
              <label htmlFor="storage-size">Detected size</label>
              <select id="storage-size" value={storageSize ?? ""} onChange={(event) => kiosk.setStorageSize(event.target.value as StorageSize)} className="min-h-12 rounded-lg border border-[#9bb7ba] bg-white px-2 font-bold">
                <option value="" disabled>No suggestion</option>
                <option value="pocket">Pocket-size</option>
                <option value="medium">Medium-size</option>
              </select>
            </div>
            <div className="flex justify-between border-t border-[#d4e1e2] pt-2"><span>Available positions</span><strong>{storageSize ? kiosk.availableCount ?? (kiosk.availabilityError ? "Unavailable" : "Checking…") : "—"}</strong></div>
            <div className="flex justify-between border-t border-[#d4e1e2] pt-2"><span>Assigned position</span><strong>Assigned on confirmation</strong></div>
          </div>
        </section>
        {kiosk.availabilityError && <p role="alert" className="text-sm text-amber-800">Live availability could not be checked. Confirmation will check again.</p>}
        {kiosk.state.error && <p role="alert" className="text-sm text-red-700">{kiosk.state.error}</p>}
        <div className="grid grid-cols-[1.5fr_1fr] gap-2">
          <Button type="button" onClick={kiosk.confirmFound} disabled={!storageSize || kiosk.availableCount === 0} className="kiosk-button kiosk-button-primary">Confirm and unlock door</Button>
          <Button type="button" variant="outline" onClick={kiosk.requestCancel} className="kiosk-button">Cancel</Button>
        </div>
      </div>
      <CompartmentMap slots={kiosk.slots} section={section} />
    </div>
  </>;
}
