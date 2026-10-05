"use client";

import Button from "@/app/components/Button";
import { assignedCompartment } from "../_data/mockKioskData";
import { useKiosk } from "../_hooks/useKioskFlow";
import CompartmentMap from "./CompartmentMap";
import FlowHeading from "./FlowHeading";
import SensorStatusCard from "./SensorStatusCard";

export default function PlacementScreen({ correct = false }: { correct?: boolean }) {
  const kiosk = useKiosk();
  return <><FlowHeading flow="found" current={3} title={correct ? "Item placed correctly" : "The pocket-size door is now unlocked."} subtitle={correct ? "Load cell verified. Close the pocket-size door to finish." : "Place the item in the highlighted compartment."} /><div className="grid gap-5 lg:grid-cols-[minmax(0,1.55fr)_minmax(310px,1fr)]"><CompartmentMap slots={kiosk.slots} /><section className="flex flex-col rounded-2xl border border-[#d4d4d4] bg-white p-5"><span className="w-fit rounded-md bg-[#d9eeeb] px-3 py-1 text-xs font-semibold text-[#0b474f]">Position {assignedCompartment}</span><h2 className="mt-8 text-xl font-semibold text-[#092a2f]">{correct ? "Correct placement detected" : "Waiting for item placement"}</h2><p className="mt-1 text-sm text-[#444]">{correct ? `Assigned compartment: ${assignedCompartment}. Detected compartment: ${assignedCompartment}.` : "Place the item fully on the sensor platform. The kiosk will confirm automatically in the final system."}</p><SensorStatusCard status={correct ? "success" : "waiting"} title={correct ? "Load cell verified" : "Simulated load-cell monitoring"} detail={correct ? "Correct compartment detected in this prototype." : "No placement change simulated yet."} /><p className="mt-5 text-xs text-[#666]">Prototype only: no physical door or sensor has been activated.</p><div className="mt-auto pt-5">{correct ? <p className="rounded-lg border border-[#a4d5c5] bg-[#eff9f4] p-3 text-sm font-semibold text-[#0b474f]">Close the pocket-size door. The system will lock automatically in the final installation.</p> : <Button type="button" variant="outline" onClick={kiosk.requestCancel} className="w-full">Cancel</Button>}</div></section></div></>;
}
