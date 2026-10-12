"use client";

import { useState } from "react";
import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import FlowHeading from "./FlowHeading";
import ImageDropzone from "./ImageDropzone";
import KioskQrScanner from "./KioskQrScanner";

export default function QrUploadPanel() {
  const kiosk = useKiosk();
  const [camera, setCamera] = useState(false);
  return <><FlowHeading flow="retrieve" current={1} title="Scan your retrieval QR" subtitle="Use a webcam or upload the QR image downloaded from SAULI." />
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(310px,1fr)]">
      <div>{camera ? <KioskQrScanner onDecoded={(payload) => void kiosk.validatePayload(payload)} /> :
        <ImageDropzone kind="qr" qr title="Upload a retrieval QR" hint="Choose a PNG, JPEG, or WebP image (up to 5 MB)." />}</div>
      <section className="flex flex-col rounded-2xl border border-[#d4d4d4] bg-white p-5 sm:p-6">
        <h2 className="text-xl font-semibold">Choose a scanning method</h2>
        <p className="mt-2 text-sm">The QR is checked by SAULI before any position is shown.</p>
        <div className="mt-5 grid gap-2">
          <Button type="button" variant="outline" disabled={kiosk.busy} onClick={() => setCamera(!camera)}>{camera ? "Stop webcam" : "Scan using webcam"}</Button>
          {camera && <Button type="button" variant="outline" disabled={kiosk.busy} onClick={() => setCamera(false)}>Upload QR image instead</Button>}
          {!camera && <Button type="button" disabled={!kiosk.state.images.qr || kiosk.busy} onClick={() => void kiosk.validateQr()}>Validate uploaded QR</Button>}
        </div>
        {kiosk.state.error && <p role="alert" className="mt-3 text-sm text-red-700">{kiosk.state.error}</p>}
        <Button type="button" variant="outline" disabled={kiosk.busy} onClick={kiosk.reset} className="mt-auto w-full">Return to kiosk home</Button>
      </section>
    </div></>;
}
