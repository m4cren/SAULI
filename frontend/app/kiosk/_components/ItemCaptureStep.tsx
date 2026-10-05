"use client";

import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import FlowHeading from "./FlowHeading";
import ImageDropzone from "./ImageDropzone";

export default function ItemCaptureStep({ side }: { side: 1 | 2 }) {
  const kiosk = useKiosk();
  const kind = side === 1 ? "front" : "back";
  return <>
    <FlowHeading flow="found" current={1} title={side === 1 ? "Capture the first side" : "Capture the second side"} subtitle={side === 1 ? "Place the entire item inside the camera frame." : "Rotate the item to show its opposite side and unique details."} />
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.7fr)_minmax(310px,1fr)]"><ImageDropzone kind={kind} title={side === 1 ? "Place item inside the frame" : "Show the opposite side"} hint="Keep the item still and make sure all edges are visible." />
      <section className="flex flex-col rounded-2xl border border-[#d4d4d4] bg-white p-5 sm:p-6"><div className="grid grid-cols-2 gap-3">{[1, 2].map((number) => <div key={number} className={`rounded-lg border p-3 text-center ${number < side ? "border-[#0b474f] bg-[#d7e6e6]" : "border-[#d5d5d5]"}`}><strong className="block">{number < side ? "✓ " : ""}Side {number}</strong><span className="text-xs text-[#555]">{number < side ? "Captured" : number === side && kiosk.state.images[kind] ? "Image selected" : number === side ? "Ready" : "Waiting"}</span></div>)}</div>
        <h2 className="mt-6 text-lg font-semibold text-[#092a2f]">Before capturing</h2><ol className="mt-3 space-y-3 text-sm"><li><strong className="mr-4 text-lg">1</strong> Remove your hands from the frame.</li><li><strong className="mr-4 text-lg">2</strong> Make the brand, color, and marks visible.</li><li><strong className="mr-4 text-lg">3</strong> Do not scan loose money or unsafe items.</li></ol>
        {kiosk.state.error && <p role="alert" className="mt-3 text-sm text-red-700">{kiosk.state.error}</p>}
        <div className="mt-auto grid gap-2 pt-6"><Button type="button" disabled={!kiosk.state.images[kind]} onClick={() => kiosk.acceptSide(kind)}>{side === 1 ? "Use as side 1" : "Use as side 2"}</Button><Button type="button" variant="outline" onClick={kiosk.requestCancel}>Cancel</Button></div>
      </section></div>
  </>;
}
