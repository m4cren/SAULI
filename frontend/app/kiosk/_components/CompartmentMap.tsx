import type { Compartment } from "../_types/kiosk";
import { isSlotCode } from "@/libs/storage/slots";

export default function CompartmentMap({ slots, assignedCode, section }: { slots: readonly Compartment[]; assignedCode?: string; section: string }) {
  if (assignedCode && !isSlotCode(assignedCode)) return <p role="alert" className="kiosk-card border-amber-500 bg-amber-50 p-5 text-base text-[#6d4c0c]">Position {assignedCode} is retired from the current cabinet map. Ask SAULI staff to handle this item.</p>;
  const pockets = slots.filter((slot) => slot.size === "Pocket-size");
  const mediums = slots.filter((slot) => slot.size === "Medium-size");
  const assignedPocket = assignedCode ? assignedCode.startsWith("P-") : section === "Pocket-size";
  const cell = (slot: Compartment) => <div key={slot.id} className={`flex min-h-12 items-center justify-center rounded-lg border text-sm font-semibold ${slot.id === assignedCode ? "border-[#40e2d5] bg-gradient-to-b from-[#167e7c] to-[#0b474f] text-white shadow-[0_0_0_3px_#c5f5ef]" : slot.occupied ? "border-[#a9c2c4] bg-[#d9e7e8] text-[#48626a]" : "border-[#d1dbdf] bg-white text-[#223747]"}`}>
    {slot.id === assignedCode && <span aria-hidden="true" className="mr-2">●</span>}{slot.id}
  </div>;
  return <section className="kiosk-card flex min-w-0 flex-col p-4 sm:p-5"><div className="mb-3"><h2 className="text-[clamp(20px,2vw,26px)] font-bold">{section} section</h2><p className="text-sm text-[#53646c]">{assignedCode ? `Highlighted position: ${assignedCode}` : "Position assigned when you confirm"}</p></div>
    <div role="img" aria-label={`SAULI compartment map with 8 pocket-size and 4 medium-size positions. ${assignedCode ? `${assignedCode} is highlighted.` : `${section} selected; position assigned on confirmation.`}`} className="grid min-h-0 flex-1 grid-cols-[1.2fr_.8fr] gap-3">
      <div className={assignedPocket ? "" : "opacity-70"}><h3 className="mb-2 text-sm font-bold text-[#0b474f]">Pocket-size (P)</h3><div className="grid grid-cols-2 gap-2">{pockets.map(cell)}</div></div>
      <div className={assignedPocket ? "opacity-70" : ""}><h3 className="mb-2 text-sm font-bold text-[#0b474f]">Medium-size (M)</h3><div className="grid gap-2">{mediums.map(cell)}</div></div>
    </div>
  </section>;
}
