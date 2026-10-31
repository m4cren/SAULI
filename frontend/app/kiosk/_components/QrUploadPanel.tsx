"use client";

import { useState } from "react";
import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import FlowHeading from "./FlowHeading";
import ImageDropzone from "./ImageDropzone";
import KioskQrScanner from "./KioskQrScanner";

export default function QrUploadPanel() {
  const kiosk = useKiosk();
  const [camera, setCamera] = useState(true);
  return <><FlowHeading flow="retrieve" current={1} title="Scan your retrieval QR code" subtitle="Hold the QR code from your phone inside the camera frame." />
    <div className="kiosk-grid"><div className="min-w-0">{camera ? <KioskQrScanner onDecoded={(payload) => void kiosk.validatePayload(payload)} /> : <ImageDropzone kind="qr" qr title="Upload a retrieval QR" hint="Choose a PNG, JPEG, or WebP image." />}</div>
      <section className="kiosk-card flex flex-col p-4 sm:p-5"><h2 className="text-[clamp(21px,2vw,29px)] font-bold">How to scan</h2>
        <ol className="mt-4 grid gap-3 text-base"><li><strong className="mr-3 text-[#299f93]">1</strong>Open the retrieval QR on your phone.</li><li><strong className="mr-3 text-[#299f93]">2</strong>Increase your screen brightness.</li><li><strong className="mr-3 text-[#299f93]">3</strong>Hold the code steady inside the frame.</li></ol>
        <p role="status" className="mt-4 rounded-xl bg-[#ddf5f1] p-3 text-sm font-semibold text-[#0b474f]">{camera ? "Ready to scan · QR codes are detected automatically" : "Desktop QR image fallback"}</p>
        {kiosk.state.error && <p role="alert" className="mt-2 text-sm text-red-700">{kiosk.state.error}</p>}
        <div className="mt-auto grid gap-2 pt-3"><Button type="button" variant="outline" disabled={kiosk.busy} onClick={() => setCamera(!camera)}>{camera ? "Upload QR image instead" : "Scan using webcam"}</Button>{!camera && <Button type="button" disabled={!kiosk.state.images.qr || kiosk.busy} onClick={() => void kiosk.validateQr()}>Validate uploaded QR</Button>}
          <Button type="button" variant="outline" disabled={kiosk.busy} onClick={kiosk.reset}>Cancel</Button></div>
      </section></div></>;
}
