import type { Compartment } from "../_types/kiosk";

export default function CompartmentMap({ slots, assignedCode, section }: { slots: readonly Compartment[]; assignedCode: string; section: string }) {
  const pockets = slots.filter((slot) => slot.size === "Pocket-size");
  const mediums = slots.filter((slot) => slot.size === "Medium-size");
  const cell = (slot: Compartment) => <div key={slot.id} className={`flex min-h-[clamp(44px,7vh,55px)] items-center justify-center rounded-lg border-2 text-xs font-semibold ${slot.id === assignedCode ? "border-[#0b474f] bg-[#d7efec] text-[#0b474f] ring-2 ring-[#9bcac4]" : "border-[#d5d5d5] bg-white"}`}>{slot.id}</div>;
  return <section className="rounded-2xl border border-[#d4d4d4] bg-white p-4 sm:p-5"><h2 className="text-lg font-semibold text-[#092a2f]">{section} section</h2><p className="mb-4 text-xs text-[#555]">Highlighted position: {assignedCode}</p><div role="img" aria-label={`SAULI compartment map. ${assignedCode} is highlighted.`} className="grid grid-cols-2 gap-3 sm:grid-cols-[1fr_.92fr_.55fr]"><div><h3 className="mb-1 text-xs font-semibold text-[#0b474f]">Pocket-size</h3><div className="grid grid-cols-2 gap-1.5">{pockets.map(cell)}</div></div><div><h3 className="mb-1 text-xs font-semibold text-[#0b474f]">Medium-size</h3><div className="grid gap-1.5">{mediums.map(cell)}</div></div><div className="col-span-2 rounded-lg border border-[#adc3c3] bg-[#eef5f4] p-2 sm:col-span-1"><h3 className="mb-1 text-xs font-semibold text-[#0b474f]">Station</h3><p className="text-xs text-[#36585b]">Kiosk and scanner</p></div></div></section>;
}
