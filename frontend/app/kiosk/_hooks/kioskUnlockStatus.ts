import type { HardwareWorkflow } from "@/libs/api/sauli";

export type KioskUnlockStatus = "queued" | "unavailable" | null;

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
