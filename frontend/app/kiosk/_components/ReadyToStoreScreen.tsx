"use client";

import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import CompartmentMap from "./CompartmentMap";
import FlowHeading from "./FlowHeading";

export default function ReadyToStoreScreen() {
  const kiosk = useKiosk();
  const assignment = kiosk.state.assignment;
  if (!assignment) return <p role="alert">No storage position has been assigned.</p>;
  const section = assignment.section === "medium" || assignment.section === "Medium-size" ? "Medium-size" : "Pocket-size";
  const { review } = kiosk.state;
  return <><FlowHeading flow="found" current={3} title="Item is identified" subtitle="Review the assigned position before unlocking the storage door." />
    <div className="kiosk-grid"><div className="flex min-w-0 flex-col gap-3"><section className="kiosk-card flex flex-1 flex-col p-4 sm:p-5"><span className="kiosk-pill w-fit">✓ READY TO STORE</span><h2 className="mt-3 text-[clamp(20px,2.4vw,30px)] font-bold leading-tight">{review.name}</h2><p className="mt-2 text-sm leading-snug text-[#53646c]">{assignment.summary || review.summary}</p>
      <div className="mt-2 flex flex-wrap gap-2">{[review.category, review.color, review.material].filter(Boolean).map((value, index) => <span key={`${index}-${value}`} className="rounded-md bg-[#d9efed] px-2 py-1 text-xs font-bold text-[#0b474f]">{value}</span>)}</div>
      <dl className="mt-auto grid gap-2 pt-3 text-sm"><div className="flex justify-between border-t border-[#d4e1e2] pt-2"><dt>Detected size</dt><dd className="font-bold">{section}</dd></div><div className="flex justify-between border-t border-[#d4e1e2] pt-2"><dt>Assigned position</dt><dd className="font-bold text-[#0b7778]">{assignment.slot_code}</dd></div><div className="flex justify-between border-t border-[#d4e1e2] pt-2"><dt>Door to unlock</dt><dd className="font-bold">{section} door</dd></div></dl></section>
      <Button type="button" onClick={kiosk.unlockDoor} className="kiosk-button kiosk-button-primary">Unlock {section.toLowerCase()} door →</Button></div>
      <CompartmentMap slots={kiosk.slots} assignedCode={assignment.slot_code} section={section} />
    </div></>;
}
