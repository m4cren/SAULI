import type { Compartment, ReviewFields } from "../_types/kiosk";
import { mediumCodes, pocketCodes } from "@/libs/storage/slots";

export const assignedCompartment = "P-07" as const;
export const wrongCompartment = "P-06" as const;
export const retrievedItem = "Black leather wallet";

export const compartments: readonly Compartment[] = [
  ...pocketCodes.map((id) => ({ id: id as Compartment["id"], size: "Pocket-size" as const, occupied: id === "P-02" })),
  ...mediumCodes.map((id) => ({ id: id as Compartment["id"], size: "Medium-size" as const, occupied: id === "M-04" })),
];

export function createMockReview(foundLocation: string): ReviewFields {
  return {
    name: "Blue reusable water bottle with a loop handle",
    summary: `Blue reusable metal water bottle with a matching screw cap, a loop handle, and a small dent near the lower edge. Found at ${foundLocation.trim()}.`,
    category: "Drinkware",
    color: "Blue",
    material: "Metal",
    size: "Pocket-size",
  };
}
