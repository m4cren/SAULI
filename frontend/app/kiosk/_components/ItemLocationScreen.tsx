"use client";

import Button from "@/app/components/Button";
import { assignedCompartment, retrievedItem } from "../_data/mockKioskData";
import { useKiosk } from "../_hooks/useKioskFlow";
import CompartmentMap from "./CompartmentMap";
import FlowHeading from "./FlowHeading";
import SensorStatusCard from "./SensorStatusCard";

export default function ItemLocationScreen() {
  const kiosk = useKiosk();
  return <><FlowHeading flow="retrieve" current={3} title="Lift your item" subtitle={`The pocket-size door is unlocked in this prototype. Use position ${assignedCompartment}.`} /><div className="grid gap-5 lg:grid-cols-[minmax(0,1.55fr)_minmax(310px,1fr)]"><CompartmentMap slots={kiosk.slots} /><section className="flex flex-col rounded-2xl border border-[#d4d4d4] bg-white p-5"><span className="w-fit rounded-md bg-[#d9eeeb] px-3 py-1 text-xs font-semibold text-[#0b474f]">Position {assignedCompartment}</span><h2 className="mt-8 text-xl font-semibold text-[#092a2f]">Waiting for item removal</h2><p className="mt-1 text-sm text-[#444]">Lift only your item: <strong>{retrievedItem}</strong>. The final kiosk will confirm automatically.</p><SensorStatusCard title="Simulated sensor monitoring" detail="No item-removal change simulated yet." /><p className="mt-5 text-xs text-[#666]">Prototype only: no physical door or load cell is connected.</p><div className="mt-auto pt-5"><Button type="button" variant="outline" onClick={kiosk.requestCancel} className="w-full">Cancel</Button></div></section></div></>;
}
