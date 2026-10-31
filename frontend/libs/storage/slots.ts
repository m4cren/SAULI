export const pocketCount = 8;
export const mediumCount = 4;
export const pocketCodes = Array.from({ length: pocketCount }, (_, index) => `P-${String(index + 1).padStart(2, "0")}`);
export const mediumCodes = Array.from({ length: mediumCount }, (_, index) => `M-${String(index + 1).padStart(2, "0")}`);
export const slotCodes = [...pocketCodes, ...mediumCodes] as const;

export type StorageSize = "pocket" | "medium";
export type SlotStatus = "available" | "reserved" | "occupied" | "out_of_service";

export function slotTotals(slots: readonly { status: SlotStatus; is_active?: boolean }[]) {
  const active = slots.filter((slot) => slot.is_active !== false);
  const reserved = active.filter((slot) => slot.status === "reserved").length;
  const out_of_service = active.filter((slot) => slot.status === "out_of_service").length;
  return {
    total: active.length,
    available: active.filter((slot) => slot.status === "available").length,
    reserved,
    occupied: active.filter((slot) => slot.status === "occupied").length,
    out_of_service,
    unavailable: reserved + out_of_service,
  };
}

export function sectionLabel(size: StorageSize): string {
  return size === "pocket" ? "Pocket-size section" : "Medium-size section";
}

export function isSlotCode(value: string): boolean {
  return slotCodes.includes(value);
}
