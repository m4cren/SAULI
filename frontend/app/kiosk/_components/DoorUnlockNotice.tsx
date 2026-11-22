"use client";

import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";

export default function DoorUnlockNotice() {
  const kiosk = useKiosk();
  if (kiosk.hardwareOnline && kiosk.hardwareDoor === "open") return null;
  const pulseFailed = kiosk.unlockCommandStatus === "failed" || kiosk.lastUnlock?.status === "failed" || kiosk.lastUnlock?.status === "rejected";
  const needsReview = kiosk.hardwarePhase === "requires_review" || kiosk.hardwarePhase === "warning_active";
  return <div role="status" className="mt-3 w-full rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
    <p>{needsReview ? "The door workflow requires staff review. Do not force a new unlock." : kiosk.unlockStatus === "unavailable" ? (kiosk.unlockError || "Unlock was not acknowledged. Use Retry to request a new authorized attempt.") : pulseFailed ? "The previous unlock was rejected. Retry only after the door and switches are ready." : "Waiting for the door sensor to confirm that the door is open."}</p>
    {kiosk.unlockStatus === "unavailable" && !needsReview && <Button type="button" variant="outline" disabled={kiosk.busy} onClick={kiosk.retryUnlock} className="mt-2 w-full">{kiosk.busy ? "Requesting unlock..." : "Retry door unlock"}</Button>}
  </div>;
}
