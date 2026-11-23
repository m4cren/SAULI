"use client";

import { useState } from "react";
import { simulateHardwarePresence } from "@/libs/api/sauli";
import { mediumCodes, pocketCodes } from "@/libs/storage/slots";
import { useKiosk } from "../_hooks/useKioskFlow";

/** Optional operator panel. All actions go through backend -> authenticated Pi,
 * changing only the Pi's test sensor overlay, NEVER the DB/Next reducer directly.
 * Real GPIO, reed, solenoid, LEDs and the existing completion workflow remain.
 */
export default function SensorSimulationControls({ inModal = false, inFeedback = false }: {
  inModal?: boolean; inFeedback?: boolean;
}) {
  const kiosk = useKiosk();
  const { screen, modal } = kiosk.state;
  const itemId = screen.mode === "found" && screen.step === "placement"
    ? kiosk.state.assignment?.item_id : null;
  const sessionId = screen.mode === "retrieve" && (screen.step === "qrVerified" || screen.step === "itemLocation")
    ? kiosk.state.validatedRetrieval?.id : null;
  const assigned = itemId ? kiosk.state.assignment?.slot_code : sessionId ? kiosk.state.validatedRetrieval?.slot_code : null;
  const slots = assigned?.startsWith("P-") ? pocketCodes : mediumCodes;
  const alternatives = slots.filter((slot) => slot !== assigned);
  const [wrongSlot, setWrongSlot] = useState<string>("");
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState("");

  if (process.env.NEXT_PUBLIC_SENSOR_SIMULATION_ENABLED !== "true" || !assigned || !(itemId || sessionId)) return null;
  if (modal && !inModal) return null;
  if (inModal && modal !== "wrongPlacement" && modal !== "wrongItem") return null;
  if (kiosk.locallyCompleted || kiosk.syncPending) return null;
  const selected = (inModal && kiosk.state.wrongSlot && alternatives.includes(kiosk.state.wrongSlot))
    ? kiosk.state.wrongSlot : alternatives.includes(wrongSlot as typeof alternatives[number]) ? wrongSlot : alternatives[0];
  const canAct = kiosk.hardwareOnline === true && kiosk.hardwareDoor === "open" && !sending;

  async function simulate(slot: string, action: "target" | "disturb" | "restore" | "undo_target") {
    if (!assigned || !(itemId || sessionId) || !canAct) return;
    setSending(true);
    setMessage("");
    try {
      const result = await simulateHardwarePresence({ workflowId: (itemId || sessionId)!, assignedSlot: assigned, slot, action });
      setMessage(`${result.slot}: ${result.present ? "item present" : "item absent"}. Waiting for live Pi status...`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Simulation request failed.");
    } finally {
      setSending(false);
    }
  }

  return <details className={inModal || inFeedback
    ? "mt-4 max-h-[42vh] overflow-y-auto rounded-lg border border-dashed border-amber-500 bg-amber-50 p-3 text-left"
    : "fixed bottom-3 right-3 z-30 w-[min(390px,calc(100vw-24px))] rounded-lg border border-amber-500 bg-amber-50 p-3 shadow-xl"}>
    <summary className="cursor-pointer text-sm font-bold text-amber-900">Operator sensor simulation — TEST ONLY</summary>
    <div className="mt-3 grid gap-2 text-sm text-amber-950">
      <p>Simulates presence readings; the real door reed and the existing Pi completion checks still apply. Do not use for unattended public operation.</p>
      <p className="font-semibold">Assigned: {assigned} · {screen.mode === "found" ? "deposit" : "retrieval"}</p>
      {kiosk.hardwareDoor !== "open" && <p role="status">Open the authorized door before using the simulation buttons.</p>}
      {!inModal && <div className="grid grid-cols-2 gap-2">
        <button type="button" disabled={!canAct} onClick={() => void simulate(assigned, "target")}
          className="rounded bg-[#0b474f] px-2 py-3 font-semibold text-white disabled:opacity-50">
          {screen.mode === "found" ? "Simulate item placed" : "Simulate item retrieved"}
        </button>
        <button type="button" disabled={!canAct} onClick={() => void simulate(assigned, "undo_target")}
          className="rounded border border-amber-700 bg-white px-2 py-3 font-semibold disabled:opacity-50">Undo assigned change</button>
      </div>}
      <label className="grid gap-1">Other compartment (same door)
        <select value={selected} onChange={(e) => setWrongSlot(e.target.value)}
          className="rounded border border-amber-600 bg-white p-2">
          {alternatives.map((code) => <option key={code} value={code}>{code}</option>)}
        </select>
      </label>
      <div className="grid grid-cols-2 gap-2">
        <button type="button" disabled={!canAct} onClick={() => void simulate(selected, "disturb")}
          className="rounded bg-red-700 px-2 py-3 font-semibold text-white disabled:opacity-50">
          {screen.mode === "found" ? "Wrong placement" : "Wrong item lifted"}
        </button>
        <button type="button" disabled={!canAct} onClick={() => void simulate(selected, "restore")}
          className="rounded border border-amber-700 bg-white px-2 py-3 font-semibold disabled:opacity-50">Restore {selected}</button>
      </div>
      {message && <p role="status" className="text-sm">{message}</p>}
    </div>
  </details>;
}
