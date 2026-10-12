"use client";
import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import FlowHeading from "./FlowHeading";

export default function IdentificationSummary() {
  const kiosk = useKiosk();
  const { review, foundLocation, storageSize } = kiosk.state;
  const summaryMentionsLocation = foundLocation.trim() && review.summary.toLowerCase().includes(foundLocation.trim().toLowerCase());
  return <><FlowHeading flow="found" current={2} title="Item is identified" subtitle="Confirm the result before the storage door is unlocked." />
    <div className="grid gap-5 lg:grid-cols-[minmax(0,0.87fr)_minmax(0,1fr)] lg:items-stretch"><div className="flex min-w-0 flex-col gap-5">
      <section className="flex min-h-[445px] flex-col rounded-2xl border border-[#d4d4d4] bg-white p-5 sm:p-6">
        <h2 className="text-[clamp(23px,2.4vw,28px)] font-semibold leading-[1.18] text-[#092a2f]">{review.name}</h2>
        <p className="mt-4 text-sm leading-relaxed text-[#383838]">{review.summary}</p>
        {!summaryMentionsLocation && foundLocation.trim() && <p className="mt-1 text-sm">Found at {foundLocation.trim()}.</p>}
        <div className="mt-4 flex flex-wrap gap-2">{[review.category, review.color, review.material].filter(Boolean).map((value, index) => <span key={`${index}-${value}`} className="max-w-full break-words rounded bg-[#cce9e6] px-3 py-1 text-xs font-semibold text-[#0b474f]">{value}</span>)}</div>
        <div className="mt-auto pt-8 text-sm"><label htmlFor="storage-size" className="block border-t border-[#d4d4d4] pt-3 font-semibold">Storage size</label>
          <select id="storage-size" value={storageSize ?? ""} onChange={(event) => kiosk.setStorageSize(event.target.value as "pocket" | "medium")} className="mt-2 w-full rounded-lg border border-[#9bb7ba] bg-white p-3"><option value="" disabled>No suggestion yet</option><option value="pocket">Pocket-size</option><option value="medium">Medium-size</option></select>
          <p className="mt-2 text-xs text-[#52666a]">Qwen suggests {kiosk.analysis?.storage_size === "medium" ? "Medium-size" : "Pocket-size"} from the photos. Change it if the item would not fit.</p>
          <div className="mt-3 flex justify-between gap-3 border-t border-[#d4d4d4] py-3"><span>Available positions</span><strong>{storageSize ? kiosk.availableCount ?? (kiosk.availabilityError ? "Unavailable" : "Checking…") : "Awaiting suggestion"}</strong></div>
          <div className="flex justify-between gap-3 border-y border-[#d4d4d4] py-3"><span>Position</span><strong>Assigned when confirmed</strong></div>
        </div></section>
      {kiosk.availabilityError && <p role="alert" className="text-sm text-amber-800">Live availability could not be checked. Confirmation will check the section again.</p>}
      {kiosk.state.error && <p role="alert" className="text-sm text-red-700">{kiosk.state.error}</p>}
      <div className="grid gap-2 sm:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]"><Button type="button" onClick={kiosk.confirmFound} disabled={kiosk.busy || !storageSize || kiosk.availableCount === 0} className="w-full">{kiosk.busy ? "Preparing door…" : "Unlock the door"}</Button><Button type="button" variant="outline" onClick={kiosk.requestCancel} disabled={kiosk.busy} className="w-full">Cancel</Button></div>
    </div><section aria-label="Storage availability" className="grid min-h-[500px] min-w-0 grid-cols-2 gap-2 rounded-2xl bg-gradient-to-b from-[#273f43] to-[#326e74] p-5 text-white sm:p-7">
      {(["pocket", "medium"] as const).map((size) => <button key={size} type="button" onClick={() => kiosk.setStorageSize(size)} aria-pressed={storageSize === size} className={`flex flex-col justify-between rounded-2xl border-2 p-4 text-left ${storageSize === size ? "border-[#70b7b3]" : "border-white/30"}`}><span className="text-xs font-semibold sm:text-sm">{size === "pocket" ? "Pocket-size" : "Medium-size"}</span><span><strong className="text-4xl">{kiosk.availability[size]?.available ?? "—"}</strong> <span className="text-sm">positions available</span></span></button>)}
    </section></div></>;
}
