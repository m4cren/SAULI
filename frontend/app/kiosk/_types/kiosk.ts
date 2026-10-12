export type ImageKind = "front" | "back" | "qr";
export type FoundStep = "captureFront" | "captureBack" | "foundLocation" | "identifying" | "summary" | "review" | "placement" | "placementCorrect" | "stored" | "noSlots";
export type RetrievalStep = "uploadQr" | "verifyingQr" | "qrVerified" | "invalidQr" | "itemLocation" | "retrieved";
export type KioskScreen = { mode: "home" } | { mode: "found"; step: FoundStep } | { mode: "retrieve"; step: RetrievalStep };
export type KioskModal = "cancel" | "wrongPlacement" | "wrongItem" | null;
export type CompartmentId = `P-${string}` | `M-${string}`;

export interface Compartment {
  id: CompartmentId;
  size: "Pocket-size" | "Medium-size";
  occupied: boolean;
}

export interface ReviewFields {
  name: string;
  summary: string;
  category: string;
  color: string;
  material: string;
  size: string;
}

export interface KioskState {
  screen: KioskScreen;
  modal: KioskModal;
  images: Record<ImageKind, string | null>;
  foundLocation: string;
  review: ReviewFields;
  correctionNote: string;
  error: string | null;
  qrErrorCode: string | null;
  storageSize: StorageSize | null;
  assignment: ConfirmedItem | null;
  fullSize: StorageSize | null;
  validatedRetrieval: ValidatedRetrieval | null;
}
import type { ConfirmedItem } from "@/libs/api/sauli";
import type { ValidatedRetrieval } from "@/libs/api/sauli";
import type { StorageSize } from "@/libs/storage/slots";
