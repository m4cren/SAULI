import type { HardwareWorkflow } from "@/libs/api/sauli";

export type KioskUnlockStatus = "queued" | "unavailable" | null;

export function hardwareWorkflowError(workflow: HardwareWorkflow): string | null {
  if (workflow.phase === "requires_review") {
    return "Final verification failed. Keep the door closed and ask SAULI staff to review the cabinet.";
  }
  if (!workflow.finalization_error) return null;
  if (workflow.finalization_error === "BACKEND_UNAVAILABLE") {
    return "The door is closed, but SAULI cannot reach the backend. Keep it closed while the connection recovers.";
  }
  if (["FINALIZATION_PENDING", "FRESH_POST_CLOSE_SENSOR_REQUIRED", "FRESH_SNAPSHOT_REQUIRED",
    "POST_CLOSE_SEQUENCE_REQUIRED", "SENSOR_DATA_INCOMPLETE"].includes(workflow.finalization_error)) {
    return "The door is closed, but final sensor verification is still pending. Keep the door closed and the item in its assigned position.";
  }
  return `Final verification stopped (${workflow.finalization_error}). Keep the door closed and ask SAULI staff for help.`;
}

export function isFinalizedPlacement(workflow: HardwareWorkflow): boolean {
  return workflow.placement_status === "placed"
    && workflow.phase === "completed"
    && workflow.wrong_slots.length === 0;
}

export function isFinalizedRetrieval(workflow: HardwareWorkflow): boolean {
  return workflow.retrieval_status === "completed"
    && workflow.phase === "completed"
    && workflow.wrong_slots.length === 0;
}

export function isResolvedWarning(workflow: HardwareWorkflow): boolean {
  return workflow.wrong_slots.length === 0
    && workflow.phase !== null
    && workflow.phase !== "warning_active"
    && workflow.phase !== "requires_review";
}

export function resolveUnlockStatus(
  current: KioskUnlockStatus,
  workflow: HardwareWorkflow,
): KioskUnlockStatus {
  if (workflow.phase === null || workflow.unlock_retry_available
    || workflow.unlock_command_status === "failed"
    || workflow.last_unlock?.status === "failed"
    || workflow.last_unlock?.status === "rejected") return "unavailable";
  if (workflow.phase === "awaiting_door_open"
    && ["pending", "claimed", "acked"].includes(workflow.unlock_command_status ?? "")) {
    // A lost POST response can still leave a committed command to observe.
    return "queued";
  }
  return current;
}
