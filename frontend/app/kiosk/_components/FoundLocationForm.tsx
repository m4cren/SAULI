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
    <FlowHeading flow="found" current={1} compact title="Review captured item" subtitle="Check both images and add the last place found before analysis." />
    <div className="kiosk-fill-grid kiosk-location-review grid gap-5 sm:grid-cols-[minmax(0,1.65fr)_minmax(270px,1fr)]">
      <div className="flex min-w-0 flex-col"><ImagePairPreview front={front} back={back} /><div className="mt-3 grid grid-cols-2 gap-2">
        <Button type="button" variant="outline" className="kiosk-retake-action" onClick={() => kiosk.retakeSide("front")}>Retake front</Button>
        <Button type="button" variant="outline" className="kiosk-retake-action" onClick={() => kiosk.retakeSide("back")}>Retake back</Button>
      </div></div>
      <section className="flex min-h-[280px] flex-col rounded-2xl border border-[#d4d4d4] bg-white p-5">
        <label htmlFor="found-location" className="mb-2 text-sm font-semibold text-[#092a2f]">Where was the item found?</label>
        <input id="found-location" maxLength={200} enterKeyHint="done" value={kiosk.state.foundLocation} onChange={(event) => kiosk.setLocation(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }} placeholder="e.g. Campus gym, Library" className="min-h-12 rounded-lg border border-[#ccc] px-3 outline-none focus-visible:border-[#0b474f] focus-visible:outline-2 focus-visible:outline-[#0b474f]" />
        {kiosk.state.error && <p role="alert" className="mt-2 text-sm text-red-700">{kiosk.state.error}</p>}
        <div className="mt-auto grid gap-2 pt-5">
          <Button type="button" onClick={kiosk.identify} disabled={kiosk.busy}>Analyze item</Button>
          <Button type="button" variant="outline" className="kiosk-retake-action" onClick={kiosk.retakePhotos}>Retake photos</Button>
        </div>
      </section>
    </div>
  </>;
}
