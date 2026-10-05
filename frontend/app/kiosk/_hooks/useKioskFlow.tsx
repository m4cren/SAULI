"use client";

import { createContext, useContext, useEffect, useReducer, useRef, useState, type ReactNode } from "react";
import { assignedCompartment, compartments, createMockReview } from "../_data/mockKioskData";
import type { ImageKind } from "../_types/kiosk";
import { initialKioskState, kioskReducer } from "./kioskReducer";

const allowedImageTypes = new Set(["image/png", "image/jpeg", "image/webp"]);

function useKioskFlow() {
  const [state, dispatch] = useReducer(kioskReducer, initialKioskState);
  const [allOccupied, setAllOccupied] = useState(false);
  const objectUrls = useRef<Record<ImageKind, string | null>>({ front: null, back: null, qr: null });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const slots = allOccupied ? compartments.map((slot) => ({ ...slot, occupied: true })) : compartments;
  const availableCount = slots.filter((slot) => !slot.occupied).length;
  const assignedAvailable = slots.some((slot) => slot.id === assignedCompartment && !slot.occupied);

  useEffect(() => {
    const urls = objectUrls;
    const pending = timer;
    return () => {
      if (pending.current) clearTimeout(pending.current);
      Object.values(urls.current).forEach((url) => { if (url) URL.revokeObjectURL(url); });
    };
  }, []);

  function clearTimer() {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  }

  function clearImage(kind: ImageKind) {
    const url = objectUrls.current[kind];
    if (url) URL.revokeObjectURL(url);
    objectUrls.current[kind] = null;
  }

  function selectFile(kind: ImageKind, file: File) {
    if (!allowedImageTypes.has(file.type) && !(file.type === "" && /\.(png|jpe?g|webp)$/i.test(file.name))) {
      dispatch({ type: "SET_ERROR", message: "Choose a PNG, JPG, JPEG, or WebP image." });
      return;
    }
    clearImage(kind);
    const url = URL.createObjectURL(file);
    objectUrls.current[kind] = url;
    dispatch({ type: "IMAGE_SELECTED", kind, url });
  }

  function reset() {
    clearTimer();
    (Object.keys(objectUrls.current) as ImageKind[]).forEach(clearImage);
    setAllOccupied(false);
    dispatch({ type: "RESET" });
  }

  function retakePhotos() {
    clearTimer();
    clearImage("front");
    clearImage("back");
    dispatch({ type: "RETAKE_PHOTOS" });
  }

  function identify() {
    if (!state.foundLocation.trim()) {
      dispatch({ type: "SET_ERROR", message: "Enter where the item was found." });
      return;
    }
    if (!state.images.front || !state.images.back) return;
    dispatch({ type: "IDENTIFY_STARTED" });
    clearTimer();
    timer.current = setTimeout(() => dispatch({ type: "IDENTIFIED", review: createMockReview(state.foundLocation, state.extraNotes) }), 850);
  }

  function confirmFound() {
    if (Object.values(state.review).some((value) => !value.trim())) {
      dispatch({ type: "SET_ERROR", message: "Complete the item name and all generated detail fields." });
      return;
    }
    if (!assignedAvailable) {
      dispatch({ type: "SET_ERROR", message: "The assigned compartment is unavailable in this simulation." });
      return;
    }
    dispatch({ type: "FOUND_CONFIRMED" });
  }

  function saveReview() {
    if (Object.values(state.review).some((value) => !value.trim())) {
      dispatch({ type: "SET_ERROR", message: "Complete the item name and all generated detail fields." });
      return;
    }
    dispatch({ type: "SAVE_REVIEW" });
  }

  function validateQr() {
    if (!state.images.qr) return;
    dispatch({ type: "QR_CHECK_STARTED" });
    clearTimer();
    timer.current = setTimeout(() => dispatch({ type: "QR_VALID" }), 850);
  }

  function simulateQr(result: "valid" | "invalid") {
    clearTimer();
    if (state.screen.mode === "retrieve" && state.screen.step === "uploadQr") {
      dispatch({ type: result === "valid" ? "QR_VALID" : "QR_INVALID" });
    } else if (state.screen.mode === "retrieve" && state.screen.step === "verifyingQr") {
      dispatch({ type: result === "valid" ? "QR_VALID" : "QR_INVALID" });
    }
  }

  function tryAnotherQr() {
    clearImage("qr");
    dispatch({ type: "TRY_ANOTHER_QR" });
  }

  function simulateNoSlots() {
    setAllOccupied(true);
    dispatch({ type: "NO_SLOTS" });
  }

  return {
    state, slots, availableCount,
    selectFile, reset, retakePhotos, identify, confirmFound, saveReview, validateQr, simulateQr, tryAnotherQr, simulateNoSlots,
    startFound: () => dispatch({ type: availableCount && assignedAvailable ? "START_FOUND" : "NO_SLOTS" }),
    startRetrieve: () => dispatch({ type: "START_RETRIEVE" }),
    acceptSide: (side: "front" | "back") => dispatch({ type: "SIDE_ACCEPTED", side }),
    setLocation: (value: string) => dispatch({ type: "LOCATION_CHANGED", value }),
    setExtraNotes: (value: string) => dispatch({ type: "EXTRA_NOTES_CHANGED", value }),
    setCorrectionNote: (value: string) => dispatch({ type: "CORRECTION_NOTE_CHANGED", value }),
    simulateWrongPlacement: () => dispatch({ type: "WRONG_PLACEMENT" }),
    simulatePlacementRemoved: () => dispatch({ type: "WRONG_PLACEMENT_REMOVED" }),
    simulateCorrectPlacement: () => dispatch({ type: "CORRECT_PLACEMENT" }),
    simulateDoorClosed: () => dispatch({ type: "DOOR_CLOSED" }),
    showItemLocation: () => dispatch({ type: "SHOW_ITEM_LOCATION" }),
    simulateWrongItem: () => dispatch({ type: "WRONG_ITEM" }),
    simulateItemReturned: () => dispatch({ type: "WRONG_ITEM_RETURNED" }),
    simulateCorrectItem: () => dispatch({ type: "CORRECT_ITEM" }),
    requestCancel: () => dispatch({ type: "CANCEL_REQUESTED" }),
    stay: () => dispatch({ type: "CANCEL_STAY" }),
  };
}

type KioskContextValue = ReturnType<typeof useKioskFlow>;
const KioskContext = createContext<KioskContextValue | null>(null);

export function KioskProvider({ children }: { children: ReactNode }) {
  const value = useKioskFlow();
  return <KioskContext.Provider value={value}>{children}</KioskContext.Provider>;
}

export function useKiosk() {
  const value = useContext(KioskContext);
  if (!value) throw new Error("Kiosk components must be inside KioskProvider");
  return value;
}
