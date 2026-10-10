"use client";

import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import FlowHeading from "./FlowHeading";
import ImagePairPreview from "./ImagePairPreview";

export default function IdentificationSummary() {
  const kiosk = useKiosk();
  const { review, foundLocation, extraNotes } = kiosk.state;
  const { front, back } = kiosk.state.images;
  return <>
    <FlowHeading flow="found" current={2} title="Item details confirmed" subtitle="Review the final description before saving the item for search matching." />
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(340px,1fr)]">
      {front && back && <ImagePairPreview front={front} back={back} />}
      <div className="flex flex-col gap-4">
        <section className="rounded-2xl border border-[#d4d4d4] bg-white p-5">
          <h2 className="text-2xl font-semibold">{review.name}</h2>
          <p className="mt-3 text-sm leading-relaxed text-[#444]">{review.summary}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {[review.category, review.color, review.material].filter(Boolean).map((value) => <span key={value} className="rounded bg-[#d3ece9] px-3 py-1 text-xs font-semibold text-[#0b474f]">{value}</span>)}
          </div>
          <dl className="mt-5 text-sm">
            <div className="flex justify-between gap-3 border-t border-[#d4d4d4] py-3"><dt>Found location</dt><dd className="text-right font-semibold">{foundLocation}</dd></div>
            {extraNotes.trim() && <div className="flex justify-between gap-3 border-t border-[#d4d4d4] py-3"><dt>Finder notes</dt><dd className="max-w-[65%] text-right">{extraNotes}</dd></div>}
          </dl>
        </section>
        {kiosk.state.error && <p role="alert" className="text-sm text-red-700">{kiosk.state.error}</p>}
        <Button type="button" onClick={kiosk.confirmFound} disabled={kiosk.busy} className="w-full">{kiosk.busy ? "Saving item…" : "Confirm and save item"}</Button>
      </div>
    </div>
  </>;
}
