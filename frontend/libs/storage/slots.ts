export const pocketCodes = Array.from({ length: 10 }, (_, index) => `P-${String(index + 1).padStart(2, "0")}`);
export const mediumCodes = Array.from({ length: 5 }, (_, index) => `M-${String(index + 1).padStart(2, "0")}`);
export const slotCodes = [...pocketCodes, ...mediumCodes] as const;

export type StorageSize = "pocket" | "medium";
export type SlotStatus = "available" | "reserved" | "occupied" | "out_of_service";

export function slotTotals(slots: readonly { status: SlotStatus }[]) {
  return {
    available: slots.filter((slot) => slot.status === "available").length,
    reserved: slots.filter((slot) => slot.status === "reserved").length,
    occupied: slots.filter((slot) => slot.status === "occupied").length,
    out_of_service: slots.filter((slot) => slot.status === "out_of_service").length,
  };
}

export function sectionLabel(size: StorageSize): string {
  return size === "pocket" ? "Pocket-size section" : "Medium-size section";
}

export function isSlotCode(value: string): boolean {
  return slotCodes.includes(value);
}
