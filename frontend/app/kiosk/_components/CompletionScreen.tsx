"use client";

import Button from "@/app/components/Button";
import Icon from "@/app/components/Icon";
import { useKiosk } from "../_hooks/useKioskFlow";

export default function CompletionScreen({ kind }: { kind: "stored" | "retrieved" | "noSlots" }) {
  const kiosk = useKiosk();
  const noSlots = kind === "noSlots";
  const size = kiosk.state.fullSize === "medium" ? "medium-size" : "pocket-size";
  const title = kind === "stored" ? "Item placed successfully" : kind === "retrieved" ? "Item retrieved successfully" : `${size === "medium-size" ? "Medium-size" : "Pocket-size"} section is full`;
  const detail = kind === "stored" ? `Position ${kiosk.state.assignment?.slot_code ?? "—"} is now occupied. The item is available for search matching.` :
    kind === "retrieved" ? "The retrieval was recorded and the storage position is available again." :
      `The item cannot currently be accepted. No position was assigned in the ${size} section.`;
  return <div className="flex min-h-[calc(100dvh-170px)] items-center justify-center"><section className="flex min-h-[330px] w-full max-w-[670px] flex-col items-center justify-center rounded-2xl border-2 border-[#d6d6d6] bg-white p-8 text-center">
    <span className={`flex size-20 items-center justify-center rounded-full ${noSlots ? "bg-[#ffedcc] text-[#aa7018]" : "bg-[#d3e6e3] text-[#0b474f]"}`}><Icon name={noSlots ? "warning" : "check"} size={42} /></span>
    <h1 className="mt-4 text-2xl font-semibold text-[#092a2f]">{title}</h1><p className="mt-2 max-w-[480px] text-sm text-[#444]">{detail}</p>
    <Button type="button" onClick={kiosk.reset} className="mt-8 min-w-64">Return to kiosk home</Button>
  </section></div>;
}
