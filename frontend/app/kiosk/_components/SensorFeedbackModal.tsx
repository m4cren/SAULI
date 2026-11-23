"use client";

import Icon from "@/app/components/Icon";
import SensorSimulationControls from "./SensorSimulationControls";

/** Live, provisional sensor confirmation. The modal disappears automatically
 * if an incorrect switch change triggers the higher-priority warning modal,
 * if the assigned item is removed/returned, or when the door is closed. */
export default function SensorFeedbackModal({
  kind, slotCode,
}: { kind: "deposit" | "retrieval"; slotCode: string }) {
  const isDeposit = kind === "deposit";
  return <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/45 p-4">
    <section role="status" aria-live="polite" aria-label="Correct item detected"
      className="w-full max-w-[580px] rounded-xl bg-white p-6 text-center shadow-xl sm:p-8">
      <span className="mx-auto flex size-16 items-center justify-center rounded-full bg-[#d3e6e3] text-[#0b474f]">
        <Icon name="check" size={36} />
      </span>
      <h2 className="mt-4 text-2xl font-semibold text-[#092a2f]">
        {isDeposit ? "Correct item detected!" : "Correct item retrieved!"}
      </h2>
      <p className="mt-3 text-base text-[#444]">
        {isDeposit ? `SAULI detected the item in ${slotCode}.` : `SAULI detected removal from ${slotCode}.`}
        {" "}<strong>Please close the door carefully to finish.</strong>
      </p>
      <p className="mt-3 text-sm text-[#52676a]">
        This is placement confirmation only. Final success appears after the closed door is verified and the record is saved.
      </p>
      <p className="mt-3 text-sm text-[#a26b13]">
        If another compartment is disturbed, a warning will replace this message until corrected.
      </p>
      <SensorSimulationControls inFeedback />
    </section>
  </div>;
}
