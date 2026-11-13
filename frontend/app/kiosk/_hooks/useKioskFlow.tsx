"use client";

import { createContext, useContext, useEffect, useReducer, useRef, useState, type ReactNode } from "react";
import { analyzeFoundItem, confirmAndStoreFoundItem, getHardwareWorkflow, getSlotAvailability, reconcileFoundItemReview, requestFoundUnlock, requestRetrievalUnlock, SauliApiError, setCaptureLight, simulateItemPlacement, simulateRetrievalEvent, validateRetrievalQr, type FoundItemAnalysis, type HardwareWorkflow, type SlotAvailability } from "@/libs/api/sauli";
import { BrowserQRCodeReader } from "@zxing/browser";
import { mediumCodes, pocketCodes, type StorageSize } from "@/libs/storage/slots";
import type { Compartment } from "../_types/kiosk";
import type { ImageKind } from "../_types/kiosk";
import { initialKioskState, kioskReducer } from "./kioskReducer";
import { resolveUnlockStatus, type KioskUnlockStatus } from "./kioskUnlockStatus";

const allowedImageTypes = new Set(["image/png", "image/jpeg", "image/webp"]);
let lightQueue: Promise<void> = Promise.resolve();
function queueLight(enabled: boolean) {
  lightQueue = lightQueue.catch(() => {}).then(async () => {
    try { await setCaptureLight(enabled); } catch { /* The Pi also has a light timeout. */ }
  });
}

function useKioskFlow() {
  const [state, dispatch] = useReducer(kioskReducer, initialKioskState);
  const [availability, setAvailability] = useState<Partial<Record<StorageSize, SlotAvailability>>>({});
  const [availabilityError, setAvailabilityError] = useState(false);
  const [analysis, setAnalysis] = useState<FoundItemAnalysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [hardwareOnline, setHardwareOnline] = useState<boolean | null>(null);
  const [hardwarePhase, setHardwarePhase] = useState<HardwareWorkflow["phase"] | null>(null);
  const [hardwareDoor, setHardwareDoor] = useState<HardwareWorkflow["door"]>("unknown");
  const [lastUnlock, setLastUnlock] = useState<HardwareWorkflow["last_unlock"]>(null);
  const [unlockCommandStatus, setUnlockCommandStatus] = useState<HardwareWorkflow["unlock_command_status"]>(null);
  const [unlockStatus, setUnlockStatus] = useState<KioskUnlockStatus>(null);
  const [lightFault, setLightFault] = useState(false);
  const lightOwned = useRef(false);
  const files = useRef<{ front: File | null; back: File | null }>({ front: null, back: null });
  const confirmationKey = useRef<string | null>(null);
  const confirmInFlight = useRef(false);
  const placementInFlight = useRef(false);
  const retrievalInFlight = useRef(false);
  const decodeInFlight = useRef(false);
  const qrFile = useRef<File | null>(null);
  const objectUrls = useRef<Record<ImageKind, string | null>>({ front: null, back: null, qr: null });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const slots: readonly Compartment[] = [...pocketCodes.map((id) => ({ id: id as Compartment["id"], size: "Pocket-size" as const, occupied: false })),
    ...mediumCodes.map((id) => ({ id: id as Compartment["id"], size: "Medium-size" as const, occupied: false }))];
  const availableCount = state.storageSize ? availability[state.storageSize]?.available ?? null : null;
  const captureActive = state.screen.mode === "found" &&
    (state.screen.step === "captureFront" || state.screen.step === "captureBack") &&
    !state.modal && !lightFault;

  useEffect(() => {
    if (!captureActive) {
      if (lightOwned.current) { lightOwned.current = false; queueLight(false); }
      return;
    }
    lightOwned.current = true;
    queueLight(true);
    const refresh = window.setInterval(() => queueLight(true), 5000);
    return () => window.clearInterval(refresh);
  }, [captureActive]);

  useEffect(() => {
    const stopLight = () => {
      if (lightOwned.current) { lightOwned.current = false; queueLight(false); }
    };
    window.addEventListener("pagehide", stopLight);
    return () => window.removeEventListener("pagehide", stopLight);
  }, []);

  useEffect(() => {
    if (state.screen.mode !== "found" || state.screen.step !== "summary") return;
    let active = true;
    Promise.all([getSlotAvailability("pocket"), getSlotAvailability("medium")])
      .then(([pocket, medium]) => { if (active) { setAvailability({ pocket, medium }); setAvailabilityError(false); } })
      .catch(() => { if (active) { setAvailability({}); setAvailabilityError(true); } });
    return () => { active = false; };
  }, [state.screen]);

  useEffect(() => {
    const urls = objectUrls;
    const pending = timer;
    return () => {
      if (pending.current) clearTimeout(pending.current);
      Object.values(urls.current).forEach((url) => { if (url) URL.revokeObjectURL(url); });
    };
  }, []);

  useEffect(() => {
    const assignment = state.screen.mode === "found" && state.screen.step === "placement" ? state.assignment : null;
    const retrieval = state.screen.mode === "retrieve" && (state.screen.step === "qrVerified" || state.screen.step === "itemLocation") ? state.validatedRetrieval : null;
    if (!assignment && !retrieval) return;
    let active = true;
    let polling = false;
    async function poll() {
      if (polling) return;
      polling = true;
      try {
        const workflow = await getHardwareWorkflow(assignment ? { itemId: assignment.item_id } : { sessionId: retrieval!.id });
        if (!active) return;
        setHardwareOnline(workflow.hardware_online);
        setHardwarePhase(workflow.phase);
        setHardwareDoor(workflow.door);
        setLastUnlock(workflow.last_unlock);
        setUnlockCommandStatus(workflow.unlock_command_status);
        setUnlockStatus((current) => resolveUnlockStatus(current, workflow));
        if (assignment) {
          if (workflow.wrong_slots.length) dispatch({ type: "WRONG_PLACEMENT", slot: workflow.wrong_slots[0] });
          else if (state.modal === "wrongPlacement") dispatch({ type: "WRONG_PLACEMENT_REMOVED" });
          else if (workflow.placement_status === "placed") dispatch({ type: "PLACEMENT_SUCCEEDED", assignment: { ...assignment, placement_status: "placed", slot_status: "occupied" } });
        } else if (retrieval) {
          if (workflow.wrong_slots.length) dispatch({ type: "WRONG_ITEM", slot: workflow.wrong_slots[0] });
          else if (state.modal === "wrongItem") dispatch({ type: "WRONG_ITEM_RETURNED" });
          else if (workflow.retrieval_status === "completed") dispatch({ type: "CORRECT_ITEM" });
        }
      } catch { if (active) { setHardwareOnline(false); setHardwarePhase(null); setHardwareDoor("unknown"); setLastUnlock(null); setUnlockCommandStatus(null); } }
      finally { polling = false; }
    }
    void poll();
    const interval = window.setInterval(() => void poll(), 1000);
    return () => { active = false; window.clearInterval(interval); };
  }, [state.screen, state.assignment, state.validatedRetrieval, state.modal]);

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
    const limit = kind === "qr" ? 5_000_000 : 10_485_760;
    if (file.size > limit) {
      dispatch({ type: "SET_ERROR", message: kind === "qr" ? "Choose a QR image smaller than 5 MB." : "Choose an item image no larger than 10 MiB." });
      return;
    }
    clearImage(kind);
    const url = URL.createObjectURL(file);
    objectUrls.current[kind] = url;
    if (kind === "front" || kind === "back") { files.current[kind] = file; confirmationKey.current = null; }
    if (kind === "qr") qrFile.current = file;
    dispatch({ type: "IMAGE_SELECTED", kind, url });
  }

  function reset() {
    clearTimer();
    (Object.keys(objectUrls.current) as ImageKind[]).forEach(clearImage);
    setAvailability({});
    setAvailabilityError(false);
    files.current = { front: null, back: null };
    qrFile.current = null;
    confirmationKey.current = null;
    setAnalysis(null);
    setHardwarePhase(null);
    setHardwareDoor("unknown");
    setLastUnlock(null);
    setUnlockStatus(null);
    setUnlockCommandStatus(null);
    setLightFault(false);
    dispatch({ type: "RESET" });
  }

  function retakePhotos() {
    clearTimer();
    clearImage("front");
    clearImage("back");
    files.current = { front: null, back: null };
    confirmationKey.current = null;
    setAnalysis(null);
    setLightFault(false);
    dispatch({ type: "RETAKE_PHOTOS" });
  }

  function retakeSide(side: "front" | "back") {
    clearImage(side);
    files.current[side] = null;
    confirmationKey.current = null;
    setAnalysis(null);
    setLightFault(false);
    dispatch({ type: "RETAKE_SIDE", side });
  }

  async function identify() {
    if (!state.foundLocation.trim()) {
      dispatch({ type: "SET_ERROR", message: "Enter where the item was found." });
      return;
    }
    if (!files.current.front || !files.current.back) {
      dispatch({ type: "SET_ERROR", message: "Capture or upload both the front and back images before analysis." });
      return;
    }
    if (busy) return;
    dispatch({ type: "IDENTIFY_STARTED" });
    setBusy(true);
    try {
      const result = await analyzeFoundItem(files.current.front, files.current.back, state.foundLocation);
      if (result.analysis.object_count < 1) { dispatch({ type: "CAPTURE_REJECTED", reason: "noItem" }); return; }
      if (!result.analysis.views_consistent) { dispatch({ type: "DIFFERENT_ITEM" }); return; }
      const explicitKind = [result.analysis.category, result.analysis.generic_name].map((value) => value.trim().toLowerCase());
      if (explicitKind.includes("loose money")) { dispatch({ type: "CAPTURE_REJECTED", reason: "looseMoney" }); return; }
      if (explicitKind.includes("hazardous item") || explicitKind.includes("unsafe item")) { dispatch({ type: "CAPTURE_REJECTED", reason: "hazardousItem" }); return; }
      setAnalysis(result.analysis);
      dispatch({ type: "IDENTIFIED", size: result.analysis.storage_size, review: { name: result.analysis.object_name, summary: result.summary,
        category: result.analysis.category, color: result.analysis.colors.join(", "),
        material: result.analysis.material.join(", "), size: result.analysis.storage_size === "pocket" ? "Pocket-size" : "Medium-size" } });
    } catch (error) {
      if (error instanceof SauliApiError && error.code === "VIEW_MISMATCH") { dispatch({ type: "DIFFERENT_ITEM" }); return; }
      const reason = error instanceof SauliApiError && ({ NO_ITEM_DETECTED: "noItem", HAZARDOUS_ITEM: "hazardousItem", LOOSE_MONEY: "looseMoney" } as const)[error.code as "NO_ITEM_DETECTED" | "HAZARDOUS_ITEM" | "LOOSE_MONEY"];
      if (reason) dispatch({ type: "CAPTURE_REJECTED", reason });
      else dispatch({ type: "IDENTIFY_FAILED", message: error instanceof Error ? error.message : "Analysis failed." });
    } finally { setBusy(false); }
  }

  async function confirmFound() {
    if (!analysis || !files.current.front || !files.current.back || busy || confirmInFlight.current) return;
    if (!state.storageSize) { dispatch({ type: "SET_ERROR", message: "The item needs a storage-size recommendation before confirming. Analyze it again." }); return; }
    confirmInFlight.current = true;
    setBusy(true);
    confirmationKey.current ??= crypto.randomUUID();
    try {
      const assigned = await confirmAndStoreFoundItem(files.current.front, files.current.back, state.foundLocation, analysis, state.storageSize, confirmationKey.current);
      clearImage("front"); clearImage("back");
      files.current = { front: null, back: null };
      setAnalysis(null);
      setUnlockStatus(assigned.unlock_status);
      dispatch({ type: "FOUND_CONFIRMED", assignment: assigned });
    } catch (error) {
      if (error instanceof SauliApiError && error.code === "NO_AVAILABLE_STORAGE_SLOT") dispatch({ type: "NO_SLOTS", size: error.requestedSize ?? state.storageSize });
      else dispatch({ type: "SET_ERROR", message: error instanceof Error ? error.message : "The item could not be saved." });
    } finally { confirmInFlight.current = false; setBusy(false); }
  }

  async function saveReview() {
    if (!analysis || busy) return;
    if (!state.correctionNote.trim()) { dispatch({ type: "SAVE_REVIEW" }); return; }
    setBusy(true);
    try {
      const result = await reconcileFoundItemReview(analysis, state.foundLocation, state.correctionNote);
      setAnalysis(result.analysis);
      dispatch({ type: "REVIEW_RECONCILED", size: result.analysis.storage_size, review: { name: result.analysis.object_name, summary: result.summary,
        category: result.analysis.category, color: result.analysis.colors.join(", "),
        material: result.analysis.material.join(", "), size: result.analysis.storage_size === "pocket" ? "Pocket-size" : "Medium-size" } });
    } catch (error) {
      dispatch({ type: "SET_ERROR", message: error instanceof Error ? error.message : "The correction could not be applied." });
    } finally { setBusy(false); }
  }

  async function validatePayload(payload: string) {
    if (retrievalInFlight.current) return;
    retrievalInFlight.current = true;
    setBusy(true);
    dispatch({ type: "QR_CHECK_STARTED" });
    try {
      const retrieval = await validateRetrievalQr(payload);
      clearImage("qr");
      qrFile.current = null;
      setUnlockStatus(retrieval.unlock_status);
      dispatch({ type: "QR_VALID", retrieval });
    } catch (cause) {
      dispatch({ type: "QR_INVALID", message: cause instanceof Error ? cause.message : "The QR could not be verified.",
        code: cause instanceof SauliApiError ? cause.code : undefined });
    } finally { retrievalInFlight.current = false; setBusy(false); }
  }

  async function validateQr() {
    if (!qrFile.current || retrievalInFlight.current || decodeInFlight.current) return;
    decodeInFlight.current = true;
    setBusy(true);
    const reader = new BrowserQRCodeReader();
    const url = URL.createObjectURL(qrFile.current);
    try {
      const decoded = await reader.decodeFromImageUrl(url);
      await validatePayload(decoded.getText());
    } catch {
      dispatch({ type: "SET_ERROR", message: "No readable QR was found in this image. Try a clear PNG, JPEG, or WebP file." });
    } finally { URL.revokeObjectURL(url); decodeInFlight.current = false; setBusy(false); }
  }

  function tryAnotherQr() {
    clearImage("qr");
    qrFile.current = null;
    dispatch({ type: "TRY_ANOTHER_QR" });
  }

  async function retryUnlock() {
    if (busy || unlockStatus !== "unavailable" || unlockCommandStatus === "failed" || lastUnlock?.status === "failed" || lastUnlock?.status === "rejected") return;
    const assignment = state.screen.mode === "found" ? state.assignment : null;
    const retrieval = state.screen.mode === "retrieve" ? state.validatedRetrieval : null;
    if (!assignment && !retrieval) return;
    setBusy(true);
    try {
      const result = assignment ? await requestFoundUnlock(assignment.item_id) : await requestRetrievalUnlock(retrieval!.id);
      if (["pending", "claimed", "acked"].includes(result.status)) setUnlockStatus("queued");
    } catch (cause) {
      dispatch({ type: "SET_ERROR", message: cause instanceof Error ? cause.message : "The door could not be requested. Please ask staff for help." });
    } finally { setBusy(false); }
  }

  async function simulateRetrieval(event: "completion" | "wrong-item" | "item-returned") {
    const retrieval = state.validatedRetrieval;
    if (!retrieval || busy || retrievalInFlight.current) return;
    retrievalInFlight.current = true;
    setBusy(true);
    try {
      await simulateRetrievalEvent(retrieval.id, retrieval.action_token, event);
      dispatch({ type: event === "completion" ? "CORRECT_ITEM" : event === "wrong-item" ? "WRONG_ITEM" : "WRONG_ITEM_RETURNED" });
      if (event === "completion" && typeof BroadcastChannel !== "undefined") {
        const channel = new BroadcastChannel("sauli-storage-slots");
        channel.postMessage("retrieval-completed"); channel.close();
      }
    } catch (cause) {
      dispatch({ type: "SET_ERROR", message: cause instanceof Error ? cause.message : "The simulation could not be recorded." });
    } finally { retrievalInFlight.current = false; setBusy(false); }
  }

  async function simulateCorrectPlacement() {
    const assignment = state.assignment;
    if (!assignment || busy || placementInFlight.current) return;
    placementInFlight.current = true;
    setBusy(true);
    try {
      const placed = await simulateItemPlacement(assignment.item_id, assignment.slot_code);
      dispatch({ type: "PLACEMENT_SUCCEEDED", assignment: placed });
      if (typeof BroadcastChannel !== "undefined") {
        const channel = new BroadcastChannel("sauli-storage-slots");
        channel.postMessage("placement-updated");
        channel.close();
      }
    } catch (error) {
      dispatch({ type: "SET_ERROR", message: error instanceof Error ? error.message : "Placement could not be recorded." });
    } finally { placementInFlight.current = false; setBusy(false); }
  }

  return {
    state, slots, availableCount, availability, availabilityError, hardwareOnline, hardwarePhase, hardwareDoor, lastUnlock, unlockCommandStatus, unlockStatus, busy, analysis,
    setCaptureLightFault: setLightFault,
    selectFile, reset, retakePhotos, retakeSide, identify, confirmFound, saveReview, validateQr, validatePayload, tryAnotherQr, retryUnlock,
    startFound: () => dispatch({ type: "START_FOUND" }),
    startRetrieve: () => dispatch({ type: "START_RETRIEVE" }),
    acceptSide: (side: "front" | "back") => dispatch({ type: "SIDE_ACCEPTED", side }),
    setLocation: (value: string) => dispatch({ type: "LOCATION_CHANGED", value }),
    setCorrectionNote: (value: string) => dispatch({ type: "CORRECTION_NOTE_CHANGED", value }),
    setStorageSize: (size: StorageSize) => dispatch({ type: "SIZE_SELECTED", size }),
    simulateWrongPlacement: () => dispatch({ type: "WRONG_PLACEMENT" }),
    simulatePlacementRemoved: () => dispatch({ type: "WRONG_PLACEMENT_REMOVED" }),
    simulateCorrectPlacement,
    simulateDoorClosed: () => dispatch({ type: "DOOR_CLOSED" }),
    showItemLocation: () => dispatch({ type: "SHOW_ITEM_LOCATION" }),
    simulateWrongItem: () => void simulateRetrieval("wrong-item"),
    simulateItemReturned: () => void simulateRetrieval("item-returned"),
    simulateCorrectItem: () => void simulateRetrieval("completion"),
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
