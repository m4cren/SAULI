"use client";

import Image from "next/image";
import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import FlowHeading from "./FlowHeading";

export default function DifferentItemScreen() {
  const kiosk = useKiosk();
  const { front, back } = kiosk.state.images;
  return <><FlowHeading flow="found" current={1} title="Different item detected" subtitle="Side 2 does not appear to match the item from Side 1." />
    <div className="kiosk-grid"><section className="kiosk-card grid grid-cols-2 gap-3 bg-[#edf8f6] p-3">{[[front, "Side 1 · Kept"], [back, "Side 2 · Needs retake"]].map(([url, label]) => <div key={label} className="flex min-w-0 flex-col rounded-xl border border-[#d3e2e2] bg-white p-2"><h2 className="mb-2 text-center text-base font-bold">{label}</h2><div className="relative min-h-[200px] flex-1 overflow-hidden rounded-lg bg-[#eef3f4]">{url ? <Image src={url} fill unoptimized alt={label ?? "Captured side"} sizes="(max-width:900px) 40vw, 300px" className="object-contain" /> : null}</div></div>)}</section>
      <section className="kiosk-card flex flex-col p-5"><div className="grid grid-cols-2 gap-2 text-center text-sm"><span className="rounded-lg border border-[#28b5a7] bg-[#e4f8f4] p-2">✓ Side 1 captured</span><span className="rounded-lg border border-amber-500 bg-amber-50 p-2 text-amber-800">! Side 2 needs retake</span></div><div className="my-auto text-center"><h2 className="text-2xl font-bold">Use the same item</h2><p className="mt-2 text-base">Turn the Side 1 item around, then capture its other side.</p><p className="kiosk-pill mt-4">Your Side 1 photo will be kept.</p></div><div className="grid gap-2"><Button type="button" onClick={() => kiosk.retakeSide("back")} className="kiosk-button kiosk-button-primary">Retake side 2</Button><Button type="button" variant="outline" onClick={kiosk.requestCancel} className="kiosk-button">Cancel</Button></div></section></div>
  </>;
}
