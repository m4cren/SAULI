"use client";

import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import CompartmentMap from "./CompartmentMap";
import FlowHeading from "./FlowHeading";

export default function ItemLocationScreen() {
  const kiosk = useKiosk();
  const retrieval = kiosk.state.validatedRetrieval;
  if (!retrieval) return null;
  const section = retrieval.section === "pocket" ? "Pocket-size" : "Medium-size";
  return <><FlowHeading flow="retrieve" current={2} title="Lift your item" subtitle={`Door unlocked — simulation. Use position ${retrieval.slot_code}.`} />
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.55fr)_minmax(310px,1fr)]">
      <CompartmentMap slots={kiosk.slots} assignedCode={retrieval.slot_code} section={section} />
      <section className="flex flex-col rounded-2xl border border-[#d4d4d4] bg-white p-5">
        <span className="w-fit rounded-md bg-[#d9eeeb] px-3 py-1 text-xs font-semibold text-[#0b474f]">Position {retrieval.slot_code}</span>
        <h2 className="mt-8 text-xl font-semibold">Waiting for item removal</h2>
        <p className="mt-1 text-sm text-[#444]">Lift only your item: <strong>{retrieval.item_summary}</strong>. The {section.toLowerCase()} door is ready in this simulation.</p>
        <div className="mt-8 rounded-lg border border-dashed border-[#6a9999] bg-[#f1f8f7] p-4">
          <h3 className="font-semibold text-[#0b474f]">Hardware simulation</h3>
          <p className="mt-1 text-xs">Use these controls to represent load-cell events. No physical door is controlled.</p>
          <div className="mt-3 grid gap-2">
            <Button type="button" disabled={kiosk.busy} onClick={kiosk.simulateCorrectItem}>Simulate correct item lifted</Button>
            <Button type="button" variant="outline" disabled={kiosk.busy} onClick={kiosk.simulateWrongItem}>Simulate wrong item lifted</Button>
          </div>
        </div>
        {kiosk.state.error && <p role="alert" className="mt-3 text-sm text-red-700">{kiosk.state.error}</p>}
      </section>
    </div></>;
}
