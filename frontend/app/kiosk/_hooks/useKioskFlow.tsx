"use client";

import { createContext, useContext, useEffect, useReducer, useRef, useState, type ReactNode } from "react";
import { compartments } from "../_data/mockKioskData";
import { analyzeFoundItem, confirmAndStoreFoundItem, reconcileFoundItemReview, type FoundItemAnalysis } from "@/libs/api/sauli";
import type { ImageKind } from "../_types/kiosk";
import { initialKioskState, kioskReducer } from "./kioskReducer";

const allowedImageTypes = new Set(["image/png", "image/jpeg", "image/webp"]);

function useKioskFlow() {
  const [state, dispatch] = useReducer(kioskReducer, initialKioskState);
  const [allOccupied, setAllOccupied] = useState(false);
  const [analysis, setAnalysis] = useState<FoundItemAnalysis | null>(null);
  const [busy, setBusy] = useState(false);
  const files = useRef<{ front: File | null; back: File | null }>({ front: null, back: null });
  const confirmationKey = useRef<string | null>(null);
  const confirmInFlight = useRef(false);
  const objectUrls = useRef<Record<ImageKind, string | null>>({ front: null, back: null, qr: null });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const slots = allOccupied ? compartments.map((slot) => ({ ...slot, occupied: true })) : compartments;
  const availableCount = slots.filter((slot) => !slot.occupied).length;

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
    if (kind === "front" || kind === "back") { files.current[kind] = file; confirmationKey.current = null; }
    dispatch({ type: "IMAGE_SELECTED", kind, url });
  }

  function reset() {
    clearTimer();
    (Object.keys(objectUrls.current) as ImageKind[]).forEach(clearImage);
    setAllOccupied(false);
    files.current = { front: null, back: null };
    confirmationKey.current = null;
    setAnalysis(null);
    dispatch({ type: "RESET" });
  }

  function retakePhotos() {
    clearTimer();
    clearImage("front");
    clearImage("back");
    files.current = { front: null, back: null };
    confirmationKey.current = null;
    setAnalysis(null);
    dispatch({ type: "RETAKE_PHOTOS" });
  }

  async function identify() {
    if (!state.foundLocation.trim()) {
      dispatch({ type: "SET_ERROR", message: "Enter where the item was found." });
      return;
    }
    if (!files.current.front || !files.current.back || busy) return;
    dispatch({ type: "IDENTIFY_STARTED" });
    setBusy(true);
    try {
      const result = await analyzeFoundItem(files.current.front, files.current.back, state.foundLocation, state.extraNotes);
      setAnalysis(result.analysis);
      dispatch({ type: "IDENTIFIED", review: { name: result.analysis.object_name, summary: result.summary,
        category: result.analysis.category, color: result.analysis.colors.join(", "),
        material: result.analysis.material.join(", "), size: "Not assigned" } });
    } catch (error) {
      dispatch({ type: "IDENTIFY_FAILED", message: error instanceof Error ? error.message : "Analysis failed." });
    } finally { setBusy(false); }
  }

  async function confirmFound() {
    if (!analysis || !files.current.front || !files.current.back || busy || confirmInFlight.current) return;
    confirmInFlight.current = true;
    setBusy(true);
    confirmationKey.current ??= crypto.randomUUID();
    try {
      await confirmAndStoreFoundItem(files.current.front, files.current.back, state.foundLocation, state.extraNotes, analysis, confirmationKey.current);
      clearImage("front"); clearImage("back");
      files.current = { front: null, back: null };
      setAnalysis(null);
      dispatch({ type: "FOUND_CONFIRMED" });
    } catch (error) {
      dispatch({ type: "SET_ERROR", message: error instanceof Error ? error.message : "The item could not be saved." });
    } finally { confirmInFlight.current = false; setBusy(false); }
  }

  async function saveReview() {
    if (!analysis || busy) return;
    if (!state.correctionNote.trim()) { dispatch({ type: "SAVE_REVIEW" }); return; }
    setBusy(true);
    try {
      const result = await reconcileFoundItemReview(analysis, state.foundLocation, state.extraNotes, state.correctionNote);
      setAnalysis(result.analysis);
      dispatch({ type: "REVIEW_RECONCILED", review: { name: result.analysis.object_name, summary: result.summary,
        category: result.analysis.category, color: result.analysis.colors.join(", "),
        material: result.analysis.material.join(", "), size: "Not assigned" } });
    } catch (error) {
      dispatch({ type: "SET_ERROR", message: error instanceof Error ? error.message : "The correction could not be applied." });
    } finally { setBusy(false); }
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
    state, slots, availableCount, busy, analysis,
    selectFile, reset, retakePhotos, identify, confirmFound, saveReview, validateQr, simulateQr, tryAnotherQr, simulateNoSlots,
    startFound: () => dispatch({ type: "START_FOUND" }),
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
