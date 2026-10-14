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
    <nav aria-label="Image capture progress" className="mb-4 grid grid-cols-3 gap-2 text-center text-xs font-semibold sm:text-sm">
      {(["Front", "Back", "Review"] as const).map((label, index) => <span key={label} aria-current={index === 2 ? "step" : undefined}
        className={`rounded-lg border px-2 py-2 ${index === 2 ? "border-[#0B474F] bg-[#d7e6e6] text-[#0B474F]" : "border-[#d5d5d5] text-[#555]"}`}>{index + 1}. {label}</span>)}
    </nav>
    <div className="grid gap-5 sm:grid-cols-[minmax(0,1.65fr)_minmax(270px,1fr)]">
      <div><ImagePairPreview front={front} back={back} /><div className="mt-3 grid grid-cols-2 gap-2">
        <Button type="button" variant="outline" onClick={() => kiosk.retakeSide("front")}>Retake front</Button>
        <Button type="button" variant="outline" onClick={() => kiosk.retakeSide("back")}>Retake back</Button>
      </div></div>
      <section className="flex min-h-[280px] flex-col rounded-2xl border border-[#d4d4d4] bg-white p-5">
        <label htmlFor="found-location" className="mb-2 text-sm font-semibold text-[#092a2f]">Where was the item found?</label>
        <input id="found-location" maxLength={200} value={kiosk.state.foundLocation} onChange={(event) => kiosk.setLocation(event.target.value)} placeholder="e.g. Campus gym, Library" className="min-h-12 rounded-lg border border-[#ccc] px-3 outline-none focus-visible:border-[#0b474f] focus-visible:outline-2 focus-visible:outline-[#0b474f]" />
        {kiosk.state.error && <p role="alert" className="mt-2 text-sm text-red-700">{kiosk.state.error}</p>}
        <div className="mt-auto grid gap-2 pt-5">
          <Button type="button" onClick={kiosk.identify} disabled={kiosk.busy}>Analyze item</Button>
          <Button type="button" variant="outline" onClick={kiosk.retakePhotos}>Retake photos</Button>
        </div>
      </section>
    </div>
  </>;
}
