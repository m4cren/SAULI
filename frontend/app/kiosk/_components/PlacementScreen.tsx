"use client";

import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import CompartmentMap from "./CompartmentMap";
import FlowHeading from "./FlowHeading";
import SensorStatusCard from "./SensorStatusCard";

export default function PlacementScreen() {
  const kiosk = useKiosk();
  const assignment = kiosk.state.assignment;
  if (!assignment) return <p role="alert">No storage position has been assigned.</p>;
  const section = assignment.section === "medium" || assignment.section === "Medium-size" ? "Medium-size" : "Pocket-size";
  return <><FlowHeading flow="found" current={3} title={`${section} door is now unlocked`} subtitle={`Place the item carefully in ${assignment.slot_code}, then close the door.`} />
    <div className="kiosk-grid"><CompartmentMap slots={kiosk.slots} assignedCode={assignment.slot_code} section={section} />
      <section className="kiosk-card flex flex-col p-4 sm:p-5"><span className="kiosk-pill w-fit">POSITION {assignment.slot_code}</span>
        <div aria-hidden="true" className="mx-auto mt-2 flex h-18 items-center justify-center text-6xl text-[#149e93]">↓<span className="ml-1 text-5xl">▱</span></div>
        <h2 className="text-[clamp(20px,2.1vw,28px)] font-bold">Waiting for item placement</h2><p className="text-sm text-[#53646c]">Place the item fully in {assignment.slot_code}. SAULI will confirm it automatically.</p>
        <ol className="mt-3 grid gap-1 text-sm"><li><strong>1.</strong> Open the {section.toLowerCase()} door.</li><li><strong>2.</strong> Place the item in {assignment.slot_code}.</li><li><strong>3.</strong> Close the door carefully.</li></ol>
        <div className="mt-auto"><SensorStatusCard title="Placement sensor active" detail="Waiting for the item to be placed" />
          {kiosk.state.error && <p role="alert" className="mt-2 text-sm text-red-700">{kiosk.state.error}</p>}
          <details className="mt-2 rounded-lg border border-dashed border-[#a8d6d1] p-2 text-sm"><summary className="cursor-pointer font-semibold">Hardware simulation</summary><div className="mt-2 grid grid-cols-2 gap-2"><Button type="button" disabled={kiosk.busy} onClick={kiosk.simulateCorrectPlacement} className="text-sm">{kiosk.busy ? "Recording placement…" : "Simulate item placed"}</Button><Button type="button" variant="outline" disabled={kiosk.busy} onClick={kiosk.simulateWrongPlacement} className="text-sm">Simulate wrong placement</Button></div></details>
        </div>
      </section></div></>;
}
