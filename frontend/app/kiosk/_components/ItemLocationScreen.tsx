"use client";

import Button from "@/app/components/Button";
import { isSlotCode } from "@/libs/storage/slots";
import { useKiosk } from "../_hooks/useKioskFlow";
import CompartmentMap from "./CompartmentMap";
import FlowHeading from "./FlowHeading";
import SensorStatusCard from "./SensorStatusCard";

export default function ItemLocationScreen() {
  const kiosk = useKiosk();
  const retrieval = kiosk.state.validatedRetrieval;
  if (!retrieval) return null;
  if (!isSlotCode(retrieval.slot_code)) return <><FlowHeading flow="retrieve" current={2} title="Staff assistance needed" subtitle={`Position ${retrieval.slot_code} is retired from the current cabinet.`} /><CompartmentMap slots={kiosk.slots} assignedCode={retrieval.slot_code} section={retrieval.section} /></>;
  const section = retrieval.section === "pocket" ? "Pocket-size" : "Medium-size";
  return <><FlowHeading flow="retrieve" current={3} title="Retrieve your item" subtitle={`The ${section.toLowerCase()} door is unlocked. Lift your item from ${retrieval.slot_code}.`} />
    <div className="kiosk-grid"><CompartmentMap slots={kiosk.slots} assignedCode={retrieval.slot_code} section={section} />
      <section className="kiosk-card flex flex-col p-4 sm:p-5"><span className="kiosk-pill w-fit">POSITION {retrieval.slot_code}</span>
        <div aria-hidden="true" className="mx-auto mt-2 flex h-18 items-center justify-center text-6xl text-[#149e93]">↑<span className="ml-1 text-5xl">▱</span></div>
        <h2 className="text-[clamp(20px,2.1vw,28px)] font-bold">Lift only your item</h2><p className="text-sm text-[#53646c]">Remove <strong>{retrieval.item_summary}</strong> from {retrieval.slot_code}. SAULI will confirm the retrieval automatically.</p>
        <ol className="mt-3 grid gap-1 text-sm"><li><strong>1.</strong> Open the {section.toLowerCase()} door.</li><li><strong>2.</strong> Lift only your item from {retrieval.slot_code}.</li><li><strong>3.</strong> Close the door carefully.</li></ol>
        <div className="mt-auto"><SensorStatusCard title="Removal sensor active" detail="Waiting for the item to be lifted" />
          {kiosk.state.error && <p role="alert" className="mt-2 text-sm text-red-700">{kiosk.state.error}</p>}
          <details className="mt-2 rounded-lg border border-dashed border-[#a8d6d1] p-2 text-sm"><summary className="cursor-pointer font-semibold">Hardware simulation</summary><div className="mt-2 grid grid-cols-2 gap-2"><Button type="button" disabled={kiosk.busy} onClick={kiosk.simulateCorrectItem} className="text-sm">Correct item</Button><Button type="button" variant="outline" disabled={kiosk.busy} onClick={kiosk.simulateWrongItem} className="text-sm">Wrong item</Button></div></details>
        </div>
      </section></div></>;
}
