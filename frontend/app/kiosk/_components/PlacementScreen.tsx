"use client";

import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import CompartmentMap from "./CompartmentMap";
import FlowHeading from "./FlowHeading";
import SensorStatusCard from "./SensorStatusCard";
import DoorUnlockNotice from "./DoorUnlockNotice";

export default function PlacementScreen() {
  const kiosk = useKiosk();
  const assignment = kiosk.state.assignment;
  if (!assignment) return <p role="alert">No storage position has been assigned.</p>;
  const section = assignment.section === "medium" || assignment.section === "Medium-size" ? "Medium-size" : "Pocket-size";
  const provisional = kiosk.hardwarePhase === "provisional_success" || kiosk.hardwarePhase === "awaiting_door_close";
  const review = kiosk.hardwarePhase === "requires_review" || kiosk.hardwarePhase === "warning_active";
  const doorOpen = kiosk.hardwareOnline === true && kiosk.hardwareDoor === "open";
  return <><FlowHeading flow="found" current={3} title={doorOpen ? `${section} door is unlocked` : "Waiting for storage door"} subtitle={doorOpen ? `Place the item carefully in ${assignment.slot_code}, then close the door.` : `Your assigned position is ${assignment.slot_code}. Wait for the door to open before placing the item.`} />
    <div className="kiosk-grid"><CompartmentMap slots={kiosk.slots} assignedCode={assignment.slot_code} section={section} />
      <section className="kiosk-card flex flex-col p-4 sm:p-5"><span className="kiosk-pill w-fit">POSITION {assignment.slot_code}</span>
        <div aria-hidden="true" className="mx-auto mt-2 flex h-18 items-center justify-center text-6xl text-[#149e93]">↓<span className="ml-1 text-5xl">▱</span></div>
        <h2 className="text-[clamp(20px,2.1vw,28px)] font-bold">{review ? "Placement needs attention" : provisional ? "Item detected. Close the door" : doorOpen ? "Waiting for item placement" : "Waiting for door unlock"}</h2><p className="text-sm text-[#53646c]">{review ? "Check that the item is in its assigned position and return any other item you moved. SAULI will check the sensors again." : provisional ? "The sensor detected an item. Close the door carefully; SAULI will verify every position before saving." : doorOpen ? `Place the item fully in ${assignment.slot_code}. SAULI will confirm it automatically.` : "Keep the item with you until the door sensor reports it open."}</p>
        {!provisional && !review && <DoorUnlockNotice />}
        <ol className="mt-3 grid gap-1 text-sm"><li><strong>1.</strong> Open the {section.toLowerCase()} door.</li><li><strong>2.</strong> Place the item in {assignment.slot_code}.</li><li><strong>3.</strong> Close the door carefully.</li></ol>
        <div className="mt-auto"><SensorStatusCard title="Placement sensor active" detail={provisional ? "Waiting for the door to close and sensors to agree" : "Waiting for the item to be placed"} />
          {kiosk.hardwareOnline === false && <p role="status" className="mt-2 text-sm text-amber-800">The hardware connection is unavailable. Keep the item in its position while SAULI reconnects.</p>}
          {kiosk.state.error && <p role="alert" className="mt-2 text-sm text-red-700">{kiosk.state.error}</p>}
          {process.env.NODE_ENV !== "production" && <details className="mt-2 rounded-lg border border-dashed border-[#a8d6d1] p-2 text-sm"><summary className="cursor-pointer font-semibold">Hardware simulation</summary><div className="mt-2 grid grid-cols-2 gap-2"><Button type="button" disabled={kiosk.busy} onClick={kiosk.simulateCorrectPlacement} className="text-sm">{kiosk.busy ? "Recording placement…" : "Simulate item placed"}</Button><Button type="button" variant="outline" disabled={kiosk.busy} onClick={kiosk.simulateWrongPlacement} className="text-sm">Simulate wrong placement</Button></div></details>}
        </div>
      </section></div></>;
}
