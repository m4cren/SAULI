"use client";

import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import FlowHeading from "./FlowHeading";
import ImagePairPreview from "./ImagePairPreview";

export default function FoundLocationForm() {
  const kiosk = useKiosk();
  const { front, back } = kiosk.state.images;
  if (!front || !back) return null;

  return <>
    <FlowHeading flow="found" current={2} title="Item details" subtitle="Add where the item was found before identification." />
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.65fr)_minmax(310px,1fr)]">
      <ImagePairPreview front={front} back={back} />
      <section className="flex min-h-[410px] flex-col rounded-2xl border border-[#d4d4d4] bg-white p-5">
        <label htmlFor="found-location" className="mb-2 text-sm font-semibold text-[#092a2f]">Where was the item found?</label>
        <input id="found-location" value={kiosk.state.foundLocation} onChange={(event) => kiosk.setLocation(event.target.value)} placeholder="e.g. Campus gym, Library" className="min-h-12 rounded-lg border border-[#ccc] px-3 outline-none focus-visible:border-[#0b474f] focus-visible:outline-2 focus-visible:outline-[#0b474f]" />
        <label htmlFor="found-extra-notes" className="mb-2 mt-4 text-sm font-semibold text-[#092a2f]">Extra notes <span className="font-normal text-[#555]">(optional)</span></label>
        <textarea id="found-extra-notes" value={kiosk.state.extraNotes} onChange={(event) => kiosk.setExtraNotes(event.target.value)} placeholder="Add marks, labels, or other details you noticed" rows={4} className="min-h-28 w-full resize-y rounded-lg border border-[#ccc] px-3 py-2 outline-none focus-visible:border-[#0b474f] focus-visible:outline-2 focus-visible:outline-[#0b474f]" />
        {kiosk.state.error && <p role="alert" className="mt-2 text-sm text-red-700">{kiosk.state.error}</p>}
        <div className="mt-auto grid gap-2 pt-5">
          <Button type="button" onClick={kiosk.identify}>Identify item</Button>
          <Button type="button" variant="outline" onClick={kiosk.retakePhotos}>Retake photos</Button>
        </div>
      </section>
    </div>
  </>;
}
