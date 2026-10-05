import type { Compartment, ReviewFields } from "../_types/kiosk";

export const assignedCompartment = "P-07" as const;
export const wrongCompartment = "P-06" as const;
export const retrievedItem = "Black leather wallet";

export const compartments: readonly Compartment[] = [
  { id: "P-01", size: "Pocket-size", occupied: false },
  { id: "P-02", size: "Pocket-size", occupied: true },
  { id: "P-03", size: "Pocket-size", occupied: false },
  { id: "P-04", size: "Pocket-size", occupied: false },
  { id: "P-05", size: "Pocket-size", occupied: false },
  { id: "P-06", size: "Pocket-size", occupied: false },
  { id: "P-07", size: "Pocket-size", occupied: false },
  { id: "P-08", size: "Pocket-size", occupied: false },
  { id: "P-09", size: "Pocket-size", occupied: false },
  { id: "P-10", size: "Pocket-size", occupied: false },
  { id: "M-01", size: "Medium-size", occupied: false },
  { id: "M-02", size: "Medium-size", occupied: false },
  { id: "M-03", size: "Medium-size", occupied: false },
  { id: "M-04", size: "Medium-size", occupied: true },
  { id: "M-05", size: "Medium-size", occupied: false },
];

export function createMockReview(foundLocation: string, extraNotes: string): ReviewFields {
  const note = extraNotes.trim();
  return {
    name: "Blue reusable water bottle with a loop handle",
    summary: `Blue reusable metal water bottle with a matching screw cap, a loop handle, and a small dent near the lower edge. Found at ${foundLocation.trim()}.${note ? ` Finder's notes: ${note}` : ""}`,
    category: "Drinkware",
    color: "Blue",
    material: "Metal",
    size: "Pocket-size",
  };
}
