"use client";

import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import FlowHeading from "./FlowHeading";
import KioskQrScanner from "./KioskQrScanner";

export default function QrScanPanel() {
  const kiosk = useKiosk();
  return <div className="kiosk-qr-page"><FlowHeading flow="retrieve" current={1} title="Scan your retrieval QR code" subtitle="Hold the QR code from your phone inside the camera frame." />
    <div className="kiosk-grid kiosk-qr-grid"><KioskQrScanner onDecoded={(payload) => void kiosk.validatePayload(payload)} />
      <section className="kiosk-card flex min-w-0 flex-col p-4 sm:p-5"><h2 className="text-2xl font-bold">How to scan</h2>
        <ol className="mt-4 grid gap-4 text-base sm:text-lg"><li><strong className="mr-3 text-[#299f93]">1</strong>Open the retrieval QR on your phone.</li><li><strong className="mr-3 text-[#299f93]">2</strong>Increase your screen brightness.</li><li><strong className="mr-3 text-[#299f93]">3</strong>Hold the code steady inside the frame.</li></ol>
        <p role="status" className="mt-auto rounded-xl bg-[#ddf5f1] p-3 text-base font-semibold text-[#0b474f]">QR codes are detected automatically when the camera is ready.</p>
        {kiosk.state.error && <p role="alert" className="mt-2 text-base text-red-700">{kiosk.state.error}</p>}
        <div className="pt-3"><Button type="button" variant="outline" disabled={kiosk.busy} onClick={kiosk.reset} className="kiosk-button">Cancel</Button></div>
      </section></div></div>;
}
