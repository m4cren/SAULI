"use client";

import { useKiosk } from "../_hooks/useKioskFlow";
import CompletionScreen from "./CompletionScreen";
import FoundLocationForm from "./FoundLocationForm";
import HomeActions from "./HomeActions";
import IdentificationReview from "./IdentificationReview";
import IdentificationSummary from "./IdentificationSummary";
import ItemCaptureStep from "./ItemCaptureStep";
import ItemLocationScreen from "./ItemLocationScreen";
import KioskHeader from "./KioskHeader";
import PlacementScreen from "./PlacementScreen";
import ProcessingScreen from "./ProcessingScreen";
import QrResultScreen from "./QrResultScreen";
import QrUploadPanel from "./QrUploadPanel";
import StatusModal from "./StatusModal";

export default function KioskShell() {
  const { state } = useKiosk();
  const { screen, modal } = state;
  let content;
  if (screen.mode === "home") content = <HomeActions />;
  else if (screen.mode === "found") {
    switch (screen.step) {
      case "captureFront": content = <ItemCaptureStep side={1} />; break;
      case "captureBack": content = <ItemCaptureStep side={2} />; break;
      case "foundLocation": content = <FoundLocationForm />; break;
      case "identifying": content = <ProcessingScreen kind="identify" />; break;
      case "summary": content = <IdentificationSummary />; break;
      case "review": content = <IdentificationReview />; break;
      case "placement": content = <PlacementScreen />; break;
      case "placementCorrect": content = <PlacementScreen />; break;
      case "stored": content = <CompletionScreen kind="stored" />; break;
      case "noSlots": content = <CompletionScreen kind="noSlots" />; break;
    }
  } else {
    switch (screen.step) {
      case "uploadQr": content = <QrUploadPanel />; break;
      case "verifyingQr": content = <ProcessingScreen kind="qr" />; break;
      case "qrVerified": content = <QrResultScreen valid />; break;
      case "invalidQr": content = <QrResultScreen valid={false} />; break;
      case "itemLocation": content = <ItemLocationScreen />; break;
      case "retrieved": content = <CompletionScreen kind="retrieved" />; break;
    }
  }
  const compactReview = screen.mode === "found" && screen.step === "review";
  const compactSummary = screen.mode === "found" && screen.step === "summary";
  return <div className="mx-auto min-h-dvh w-full max-w-[1280px] bg-white font-sans text-[#092a2f] shadow-[0_0_25px_rgba(0,0,0,0.06)]"><div inert={Boolean(modal)} aria-hidden={Boolean(modal)} className="min-h-dvh">{screen.mode === "home" ? content : <><KioskHeader /><main className={`mx-auto w-full max-w-[1180px] px-5 sm:px-10 ${compactReview ? "pb-0 pt-6" : compactSummary ? "pb-0 pt-9" : "pb-8 pt-9"}`}>{content}</main></>}</div>{modal && <StatusModal type={modal} />}</div>;
}
