"use client";

import { useKiosk } from "../_hooks/useKioskFlow";
import CompletionScreen from "./CompletionScreen";
import CircuitBackground from "./CircuitBackground";
import CaptureRejectionScreen from "./CaptureRejectionScreen";
import DifferentItemScreen from "./DifferentItemScreen";
import FoundLocationForm from "./FoundLocationForm";
import HomeActions from "./HomeActions";
import IdentificationReview from "./IdentificationReview";
import IdentificationSummary from "./IdentificationSummary";
import ItemCaptureStep from "./ItemCaptureStep";
import ItemLocationScreen from "./ItemLocationScreen";
import PlacementScreen from "./PlacementScreen";
import ProcessingScreen from "./ProcessingScreen";
import QrResultScreen from "./QrResultScreen";
import QrScanPanel from "./QrScanPanel";
import StatusModal from "./StatusModal";

export default function KioskShell() {
  const { state } = useKiosk();
  const { screen, modal } = state;
  let content;
  if (screen.mode === "home") content = <HomeActions />;
  else if (screen.mode === "found") {
    switch (screen.step) {
      case "captureFront": content = <ItemCaptureStep key="front" side={1} />; break;
      case "captureBack": content = <ItemCaptureStep key="back" side={2} />; break;
      case "foundLocation": content = <FoundLocationForm />; break;
      case "identifying": content = <ProcessingScreen kind="identify" />; break;
      case "differentItem": content = <DifferentItemScreen />; break;
      case "noItem": content = <CaptureRejectionScreen reason="noItem" />; break;
      case "hazardousItem": content = <CaptureRejectionScreen reason="hazardousItem" />; break;
      case "looseMoney": content = <CaptureRejectionScreen reason="looseMoney" />; break;
      case "summary": content = <IdentificationSummary />; break;
      case "review": content = <IdentificationReview />; break;
      case "placement": content = <PlacementScreen />; break;
      case "placementCorrect": content = <PlacementScreen />; break;
      case "stored": content = <CompletionScreen kind="stored" />; break;
      case "noSlots": content = <CompletionScreen kind="noSlots" />; break;
    }
  } else {
    switch (screen.step) {
      case "uploadQr": content = <QrScanPanel />; break;
      case "verifyingQr": content = <ProcessingScreen kind="qr" />; break;
      case "qrVerified": content = <QrResultScreen valid />; break;
      case "invalidQr": content = <QrResultScreen valid={false} />; break;
      case "itemLocation": content = <ItemLocationScreen />; break;
      case "retrieved": content = <CompletionScreen kind="retrieved" />; break;
    }
  }
  return <div className="kiosk-shell font-sans"><CircuitBackground showTop={screen.mode === "home"} /><div inert={Boolean(modal)} aria-hidden={Boolean(modal)} className="min-h-dvh">{screen.mode === "home" ? content : <main className="kiosk-main">{content}</main>}</div>{modal && <StatusModal type={modal} />}</div>;
}
