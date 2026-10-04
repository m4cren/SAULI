"use client";

import Button from "@/app/components/Button";

// Temporary frontend controls used to simulate Raspberry Pi/load-cell events.
// Remove this component when real hardware event integration is available.
export default function PrototypeSensorControls({
  simulateWrongItemLifted,
  simulateCorrectItemLifted,
}: {
  simulateWrongItemLifted: () => void;
  simulateCorrectItemLifted: () => void;
}) {
  return (
    <section aria-label="Prototype controls" className="mt-6 rounded-[10px] border border-dashed border-[#8ba6a7] bg-[#f5f9f8] p-3">
      <h2 className="text-sm font-semibold text-[var(--sauli-brand)]">Prototype controls</h2>
      <p className="mt-1 text-xs text-[#555]">Hardware sensors are not connected in this frontend prototype.</p>
      <div className="mt-3 space-y-2"><Button type="button" variant="outline" className="w-full text-sm" onClick={simulateWrongItemLifted}>Simulate wrong item retrieved</Button><Button type="button" className="w-full text-sm" onClick={simulateCorrectItemLifted}>Simulate correct item retrieved</Button></div>
    </section>
  );
}
