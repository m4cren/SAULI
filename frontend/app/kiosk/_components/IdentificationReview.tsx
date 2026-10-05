"use client";

import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import FlowHeading from "./FlowHeading";
import ImagePairPreview from "./ImagePairPreview";

export default function IdentificationReview() {
  const kiosk = useKiosk();
  const { front, back } = kiosk.state.images;
  if (!front || !back) return null;

  return <>
    <FlowHeading flow="found" current={2} title="Review item details" subtitle="Correct anything that does not match the item before confirming." />
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.55fr)_minmax(340px,1fr)]">
      <ImagePairPreview front={front} back={back} />
      <section className="flex min-h-[410px] flex-col rounded-2xl border border-[#d4d4d4] bg-white p-4">
        <h2 id="identified-summary-label" className="mb-1 text-sm font-semibold text-[#092a2f]">SAULI summary <span className="ml-1 font-normal text-[#666]">(preview only)</span></h2>
        <div aria-labelledby="identified-summary-label" className="min-h-24 rounded-md border border-[#e4e4e4] bg-[#e4e4e4] px-3 py-2 text-sm leading-relaxed text-[#505050]">{kiosk.state.review.summary}</div>
        <label htmlFor="correction-note" className="mb-1 mt-4 text-sm font-semibold text-[#092a2f]">Correction note <span className="font-normal text-[#555]">(optional)</span></label>
        <textarea id="correction-note" value={kiosk.state.correctionNote} onChange={(event) => kiosk.setCorrectionNote(event.target.value)} rows={4} className="min-h-24 w-full resize-y rounded-md border border-[#ccc] px-3 py-2 text-sm outline-none focus-visible:outline-2 focus-visible:outline-[#0b474f]" />
        {kiosk.state.error && <p role="alert" className="mt-2 text-sm text-red-700">{kiosk.state.error}</p>}
        <div className="mt-auto pt-3">
          <p className="mb-4 text-xs text-[#555]">SAULI can make mistakes. Check important information before saving.</p>
          <Button type="button" onClick={kiosk.saveReview} className="w-full">Confirm item details</Button>
        </div>
      </section>
    </div>
  </>;
}
