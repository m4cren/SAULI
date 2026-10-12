import type { ImageKind, KioskState, ReviewFields } from "../_types/kiosk";
import type { ConfirmedItem, ValidatedRetrieval } from "@/libs/api/sauli";
import type { StorageSize } from "@/libs/storage/slots";

const emptyReview: ReviewFields = { name: "", summary: "", category: "", color: "", material: "", size: "" };

export const initialKioskState: KioskState = {
  screen: { mode: "home" },
  modal: null,
  images: { front: null, back: null, qr: null },
  foundLocation: "",
  review: emptyReview,
  correctionNote: "",
  error: null,
  qrErrorCode: null,
  storageSize: null,
  assignment: null,
  fullSize: null,
  validatedRetrieval: null,
};

export type KioskAction =
  | { type: "RESET" }
  | { type: "START_FOUND" }
  | { type: "START_RETRIEVE" }
  | { type: "NO_SLOTS"; size?: StorageSize }
  | { type: "SIZE_SELECTED"; size: StorageSize }
  | { type: "IMAGE_SELECTED"; kind: ImageKind; url: string }
  | { type: "SET_ERROR"; message: string | null }
  | { type: "SIDE_ACCEPTED"; side: "front" | "back" }
  | { type: "LOCATION_CHANGED"; value: string }
  | { type: "IDENTIFY_STARTED" }
  | { type: "IDENTIFIED"; review: ReviewFields; size: StorageSize }
  | { type: "IDENTIFY_FAILED"; message: string }
  | { type: "REVIEW_RECONCILED"; review: ReviewFields; size: StorageSize }
  | { type: "CORRECTION_NOTE_CHANGED"; value: string }
  | { type: "SAVE_REVIEW" }
  | { type: "RETAKE_PHOTOS" }
  | { type: "FOUND_CONFIRMED"; assignment?: ConfirmedItem }
  | { type: "PLACEMENT_SUCCEEDED"; assignment: ConfirmedItem }
  | { type: "WRONG_PLACEMENT" }
  | { type: "WRONG_PLACEMENT_REMOVED" }
  | { type: "CORRECT_PLACEMENT" }
  | { type: "DOOR_CLOSED" }
  | { type: "QR_CHECK_STARTED" }
  | { type: "QR_VALID"; retrieval: ValidatedRetrieval }
  | { type: "QR_INVALID"; message: string; code?: string }
  | { type: "TRY_ANOTHER_QR" }
  | { type: "SHOW_ITEM_LOCATION" }
  | { type: "WRONG_ITEM" }
  | { type: "WRONG_ITEM_RETURNED" }
  | { type: "CORRECT_ITEM" }
  | { type: "CANCEL_REQUESTED" }
  | { type: "CANCEL_STAY" };

export function kioskReducer(state: KioskState, action: KioskAction): KioskState {
  const { screen, modal } = state;
  switch (action.type) {
    case "RESET": return { ...initialKioskState, images: { front: null, back: null, qr: null } };
    case "START_FOUND": return screen.mode === "home" ? { ...state, screen: { mode: "found", step: "captureFront" } } : state;
    case "START_RETRIEVE": return screen.mode === "home" ? { ...state, screen: { mode: "retrieve", step: "uploadQr" } } : state;
    case "NO_SLOTS": return { ...state, screen: { mode: "found", step: "noSlots" }, fullSize: action.size ?? state.storageSize, error: null };
    case "SIZE_SELECTED": return screen.mode === "found" && screen.step === "summary" ? { ...state, storageSize: action.size, error: null } : state;
    case "IMAGE_SELECTED": return { ...state, images: { ...state.images, [action.kind]: action.url }, error: null };
    case "SET_ERROR": return { ...state, error: action.message };
    case "SIDE_ACCEPTED":
      if (screen.mode !== "found" || modal) return state;
      if (action.side === "front" && screen.step === "captureFront" && state.images.front) return { ...state, screen: { mode: "found", step: "captureBack" } };
      if (action.side === "back" && screen.step === "captureBack" && state.images.back) return { ...state, screen: { mode: "found", step: "foundLocation" } };
      return state;
    case "LOCATION_CHANGED": return { ...state, foundLocation: action.value, error: null };
    case "IDENTIFY_STARTED": return screen.mode === "found" && screen.step === "foundLocation" && state.images.front && state.images.back && state.foundLocation.trim()
      ? { ...state, screen: { mode: "found", step: "identifying" }, error: null } : state;
    case "IDENTIFIED": return screen.mode === "found" && screen.step === "identifying" ? { ...state, screen: { mode: "found", step: "review" }, review: action.review, storageSize: action.size } : state;
    case "IDENTIFY_FAILED": return screen.mode === "found" && screen.step === "identifying" ? { ...state, screen: { mode: "found", step: "foundLocation" }, error: action.message } : state;
    case "REVIEW_RECONCILED": return screen.mode === "found" && screen.step === "review" ? { ...state, screen: { mode: "found", step: "summary" }, review: action.review, storageSize: action.size, error: null } : state;
    case "CORRECTION_NOTE_CHANGED": return screen.mode === "found" && screen.step === "review" ? { ...state, correctionNote: action.value } : state;
    case "SAVE_REVIEW": return screen.mode === "found" && screen.step === "review"
      ? { ...state, screen: { mode: "found", step: "summary" }, error: null } : state;
    case "RETAKE_PHOTOS": return screen.mode === "found" && !modal ? { ...state, screen: { mode: "found", step: "captureFront" }, images: { ...state.images, front: null, back: null }, storageSize: null, error: null } : state;
    case "FOUND_CONFIRMED": return screen.mode === "found" && screen.step === "summary"
      ? { ...state, screen: { mode: "found", step: "placement" }, assignment: action.assignment ?? null, images: { ...state.images, front: null, back: null }, error: null } : state;
    case "PLACEMENT_SUCCEEDED": return screen.mode === "found" && screen.step === "placement"
      ? { ...state, screen: { mode: "found", step: "stored" }, assignment: action.assignment, error: null } : state;
    case "WRONG_PLACEMENT": return screen.mode === "found" && screen.step === "placement" && !modal ? { ...state, modal: "wrongPlacement" } : state;
    case "WRONG_PLACEMENT_REMOVED": return modal === "wrongPlacement" ? { ...state, modal: null } : state;
    case "CORRECT_PLACEMENT": return screen.mode === "found" && screen.step === "placement" && !modal ? { ...state, screen: { mode: "found", step: "placementCorrect" } } : state;
    case "DOOR_CLOSED": return screen.mode === "found" && screen.step === "placementCorrect" ? { ...state, screen: { mode: "found", step: "stored" } } : state;
    case "QR_CHECK_STARTED": return screen.mode === "retrieve" && screen.step === "uploadQr" ? { ...state, screen: { mode: "retrieve", step: "verifyingQr" }, error: null } : state;
    case "QR_VALID": return screen.mode === "retrieve" && screen.step === "verifyingQr" ? { ...state, screen: { mode: "retrieve", step: "qrVerified" }, images: { ...state.images, qr: null }, validatedRetrieval: action.retrieval } : state;
    case "QR_INVALID": return screen.mode === "retrieve" && screen.step === "verifyingQr" ? { ...state, screen: { mode: "retrieve", step: "invalidQr" }, error: action.message, qrErrorCode: action.code ?? null } : state;
    case "TRY_ANOTHER_QR": return screen.mode === "retrieve" && screen.step === "invalidQr" ? { ...state, screen: { mode: "retrieve", step: "uploadQr" }, images: { ...state.images, qr: null }, error: null, qrErrorCode: null } : state;
    case "SHOW_ITEM_LOCATION": return screen.mode === "retrieve" && screen.step === "qrVerified" ? { ...state, screen: { mode: "retrieve", step: "itemLocation" } } : state;
    case "WRONG_ITEM": return screen.mode === "retrieve" && screen.step === "itemLocation" && !modal ? { ...state, modal: "wrongItem" } : state;
    case "WRONG_ITEM_RETURNED": return modal === "wrongItem" ? { ...state, modal: null } : state;
    case "CORRECT_ITEM": return screen.mode === "retrieve" && screen.step === "itemLocation" && !modal ? { ...state, screen: { mode: "retrieve", step: "retrieved" }, validatedRetrieval: null } : state;
    case "CANCEL_REQUESTED": return screen.mode !== "home" && !modal ? { ...state, modal: "cancel" } : state;
    case "CANCEL_STAY": return modal === "cancel" ? { ...state, modal: null } : state;
  }
}
