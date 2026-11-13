import type { HardwareWorkflow } from "@/libs/api/sauli";

export type KioskUnlockStatus = "queued" | "unavailable" | null;

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
