"use client";

import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import FlowHeading from "./FlowHeading";
import ImagePairPreview from "./ImagePairPreview";
import ProcessingScreen from "./ProcessingScreen";

export default function IdentificationReview() {
  const kiosk = useKiosk();
  const { front, back } = kiosk.state.images;
  if (!front || !back) return null;
  if (kiosk.busy) return <ProcessingScreen kind="storage" />;
  return <><FlowHeading flow="found" current={2} title="Review item details" subtitle="Correct anything that does not match the item before saving." />
    <section className="kiosk-card mb-3 p-4"><h2 className="text-lg font-bold">SAULI summary <span className="text-sm font-normal text-[#7c8b91]">preview</span></h2><p className="mt-2 rounded-xl border border-[#dce7e8] bg-[#f2f7f7] px-4 py-3 text-base text-[#4f646c]">{kiosk.state.review.summary}</p><p className="mt-1 text-sm text-[#87929a]">SAULI can make mistakes. Review the details before saving.</p></section>
    <div className="kiosk-grid"><ImagePairPreview front={front} back={back} />
      <section className="kiosk-card flex flex-col gap-3 p-4"><div><label htmlFor="review-location" className="mb-1 block text-base font-bold">Where was the item found?</label><input id="review-location" required maxLength={200} value={kiosk.state.foundLocation} onChange={(event) => kiosk.setLocation(event.target.value)} placeholder="e.g. Campus gym" className="min-h-12 w-full rounded-lg border border-[#b8ccd0] bg-white px-3 text-base focus-visible:outline-2 focus-visible:outline-[#0b474f]" /></div>
      <div><label htmlFor="correction-note" className="mb-1 block text-base font-bold">Correction note <span className="font-normal">(optional)</span></label><textarea id="correction-note" maxLength={1500} value={kiosk.state.correctionNote} onChange={(event) => kiosk.setCorrectionNote(event.target.value)} rows={3} placeholder="Describe what needs to be corrected" className="min-h-20 w-full resize-y rounded-lg border border-[#b8ccd0] bg-white px-3 py-2 text-base focus-visible:outline-2 focus-visible:outline-[#0b474f]" /></div>
      {kiosk.state.error && <p role="alert" className="text-sm text-red-700">{kiosk.state.error}</p>}
      </section></div>
    <Button type="button" onClick={kiosk.saveReview} disabled={!kiosk.state.foundLocation.trim()} className="kiosk-button kiosk-button-primary mt-3">Confirm item details</Button>
  </>;
}
