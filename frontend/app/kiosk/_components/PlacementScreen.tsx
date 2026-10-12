"use client";
import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import CompartmentMap from "./CompartmentMap";
import FlowHeading from "./FlowHeading";

export default function PlacementScreen() {
  const kiosk = useKiosk();
  const assignment = kiosk.state.assignment;
  if (!assignment) return <p role="alert">No storage position has been assigned.</p>;
  return <><FlowHeading flow="found" current={3} title={`${assignment.section} door is ready`} subtitle={`Place the item in the highlighted position ${assignment.slot_code}.`} />
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.55fr)_minmax(310px,1fr)]"><CompartmentMap slots={kiosk.slots} assignedCode={assignment.slot_code} section={assignment.section} />
      <section className="flex flex-col rounded-2xl border border-[#d4d4d4] bg-white p-5"><span className="w-fit rounded-md bg-[#d9eeeb] px-3 py-1 text-xs font-semibold text-[#0b474f]">Position {assignment.slot_code}</span><h2 className="mt-8 text-xl font-semibold text-[#092a2f]">Waiting for item placement</h2><p className="mt-1 text-sm text-[#444]">Put the item in {assignment.slot_code}, then record the simulated placement.</p><p className="mt-5 text-xs text-[#666]">This is a web simulation. No physical door or sensor is connected.</p>{kiosk.state.error && <p role="alert" className="mt-4 text-sm text-red-700">{kiosk.state.error}</p>}<Button type="button" className="mt-auto w-full" disabled={kiosk.busy} onClick={kiosk.simulateCorrectPlacement}>{kiosk.busy ? "Recording placement…" : "Simulate item placed"}</Button></section>
    </div></>;
}
