"use client";

import Button from "@/app/components/Button";
import { assignedCompartment, compartments } from "../_data/mockKioskData";
import { useKiosk } from "../_hooks/useKioskFlow";
import FlowHeading from "./FlowHeading";

export default function IdentificationSummary() {
  const kiosk = useKiosk();
  const { review, foundLocation } = kiosk.state;
  const pocketAvailable = kiosk.slots.filter((slot) => slot.size === "Pocket-size" && !slot.occupied).length;
  const mediumAvailable = kiosk.slots.filter((slot) => slot.size === "Medium-size" && !slot.occupied).length;

  return <>
    <FlowHeading flow="found" current={2} title="Item details confirmed" subtitle={`Unlock the pocket-size door to place the item in ${assignedCompartment}.`} />
    <div className="grid gap-5 lg:grid-cols-[minmax(0,0.93fr)_minmax(0,1.07fr)]">
      <div className="flex min-w-0 flex-col gap-4">
        <section className="flex min-h-[398px] flex-col rounded-2xl border border-[#d4d4d4] bg-white p-5">
          <h2 className="max-w-[420px] text-[clamp(22px,2.4vw,28px)] font-semibold leading-[1.18]">{review.name}</h2>
          <p className="mt-4 text-sm leading-snug text-[#272727]">{review.summary}</p>
          <div className="mt-4 flex flex-wrap gap-2" aria-label="Identified attributes">
            {[review.category, review.color, review.material].map((value, index) => <span key={`${index}-${value}`} className="rounded bg-[#d3ece9] px-3 py-1 text-xs font-semibold text-[#0b474f]">{value}</span>)}
          </div>
          <dl className="mt-auto pt-5 text-sm">
            <div className="flex justify-between gap-4 border-t border-[#d4d4d4] py-3"><dt>Found location</dt><dd className="text-right font-semibold">{foundLocation}</dd></div>
            <div className="flex justify-between gap-4 border-t border-[#d4d4d4] py-3"><dt>Detected size</dt><dd className="text-right font-semibold">{review.size}</dd></div>
            <div className="flex justify-between gap-4 border-t border-[#d4d4d4] py-3"><dt>Available position</dt><dd className="font-semibold">{assignedCompartment}</dd></div>
            <div className="flex justify-between gap-4 border-y border-[#d4d4d4] py-3"><dt>Door to unlock</dt><dd className="font-semibold">Pocket-size door</dd></div>
          </dl>
        </section>
        {kiosk.state.error && <p role="alert" className="text-sm text-red-700">{kiosk.state.error}</p>}
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
          <Button type="button" onClick={kiosk.confirmFound} className="text-sm sm:text-base">Unlock the door</Button>
          <Button type="button" variant="outline" onClick={kiosk.requestCancel}>Cancel</Button>
        </div>
      </div>
      <section aria-label="Compartment availability" className="relative min-h-[460px] overflow-hidden rounded-2xl bg-gradient-to-br from-[#213c40] to-[#316b70] p-7 text-white">
        <div className="grid h-full grid-cols-[minmax(0,0.88fr)_minmax(0,1.5fr)] gap-2">
          <div className="relative rounded-2xl border-2 border-[#83c5c0] bg-white/5 p-4">
            <h3 className="text-sm font-semibold tracking-wide">Pocket-size</h3>
            <span className="absolute right-4 top-4 h-4 w-4 rounded-full border-[5px] border-[#218f89] bg-[#86cfca]" aria-hidden="true" />
            <p className="absolute bottom-4 left-4 right-4 text-sm leading-tight"><strong className="mr-1 text-4xl">{pocketAvailable}</strong> available</p>
          </div>
          <div className="relative rounded-2xl border-2 border-white/35 p-4">
            <h3 className="text-sm font-semibold tracking-wide text-white/65">Medium-size</h3>
            <p className="absolute bottom-4 left-4 right-4 text-sm leading-tight text-white/70"><strong className="mr-1 text-4xl">{mediumAvailable}</strong> available</p>
          </div>
        </div>
        <p className="sr-only">{kiosk.availableCount} of {compartments.length} total positions available. Assigned compartment {assignedCompartment} is in the pocket-size section.</p>
      </section>
    </div>
  </>;
}
