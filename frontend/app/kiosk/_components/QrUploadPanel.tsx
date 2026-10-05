"use client";

import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import FlowHeading from "./FlowHeading";
import ImageDropzone from "./ImageDropzone";
import SensorStatusCard from "./SensorStatusCard";

export default function QrUploadPanel() {
  const kiosk = useKiosk();
  return <><FlowHeading flow="retrieve" current={1} title="Scan the QR code on your phone" subtitle="Upload a picture of the one-time retrieval QR to test this kiosk." /><div className="grid gap-5 lg:grid-cols-[minmax(0,1.7fr)_minmax(310px,1fr)]"><ImageDropzone kind="qr" qr title="Keep the complete code visible" hint="Click to upload or drop a QR image here." /><section className="flex flex-col rounded-2xl border border-[#d4d4d4] bg-white p-5 sm:p-6"><h2 className="text-xl font-semibold text-[#092a2f]">QR scanning instructions</h2><ol className="mt-5 space-y-3 text-sm"><li><strong className="mr-3 text-lg">1</strong> Open the retrieval QR from the SAULI mobile app.</li><li><strong className="mr-3 text-lg">2</strong> Keep the complete code visible in your image.</li><li><strong className="mr-3 text-lg">3</strong> Upload PNG, JPG, JPEG, or WebP.</li></ol><SensorStatusCard title="Camera substitute ready" detail="The uploaded image triggers local simulated validation only." />{kiosk.state.error && <p role="alert" className="mt-2 text-sm text-red-700">{kiosk.state.error}</p>}<div className="mt-auto grid gap-2 pt-6"><Button type="button" disabled={!kiosk.state.images.qr} onClick={kiosk.validateQr}>Validate uploaded QR</Button><Button type="button" variant="outline" onClick={kiosk.requestCancel}>Cancel</Button></div></section></div></>;
}
