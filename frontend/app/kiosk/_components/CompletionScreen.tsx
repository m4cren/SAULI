"use client";

import Button from "@/app/components/Button";
import Icon from "@/app/components/Icon";
import { assignedCompartment } from "../_data/mockKioskData";
import { useKiosk } from "../_hooks/useKioskFlow";

export default function CompletionScreen({ kind }: { kind: "stored" | "retrieved" | "noSlots" }) {
  const kiosk = useKiosk();
  const noSlots = kind === "noSlots";
  return <div className="flex min-h-[calc(100dvh-170px)] items-center justify-center"><section className="flex min-h-[330px] w-full max-w-[670px] flex-col items-center justify-center rounded-2xl border-2 border-[#d6d6d6] bg-white p-8 text-center"><span className={`flex size-20 items-center justify-center rounded-full ${noSlots ? "bg-[#ffedcc] text-[#aa7018]" : "bg-[#d3e6e3] text-[#0b474f]"}`}><Icon name={noSlots ? "warning" : "check"} size={42} /></span><p className="mt-3 text-xs font-bold uppercase tracking-[0.08em] text-[#0b474f]">{noSlots ? "Storage unavailable" : "Prototype flow complete"}</p><h1 className="mt-4 text-2xl font-semibold text-[#092a2f]">{kind === "stored" ? "Item stored successfully" : kind === "retrieved" ? "Item retrieved successfully" : "No available compartments"}</h1><p className="mt-2 max-w-[480px] text-sm text-[#444]">{kind === "stored" ? "The found-item record is ready for submission. It has not been saved to Supabase." : kind === "retrieved" ? `The correct item was removed from ${assignedCompartment} in this simulation. Your prototype retrieval is complete.` : "All 15 positions are occupied in this simulation. Please try again later."}</p>{kind === "retrieved" && <p className="mt-3 text-sm font-semibold text-[#0b474f]">Please close the pocket-size door. The final system will lock automatically.</p>}<Button type="button" onClick={kiosk.reset} className="mt-8 min-w-64">Return to home</Button></section></div>;
}
