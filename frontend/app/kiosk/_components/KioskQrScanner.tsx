"use client";

import { useEffect, useRef, useState } from "react";
import { BrowserQRCodeReader, type IScannerControls } from "@zxing/browser";
import { createScanLatch, stopMediaTracks } from "@/libs/retrieval/scanner";

export default function KioskQrScanner({ onDecoded }: { onDecoded: (payload: string) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const callback = useRef(onDecoded);
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);

  useEffect(() => { callback.current = onDecoded; }, [onDecoded]);
  useEffect(() => {
    let active = true;
    let controls: IScannerControls | null = null;
    const latch = createScanLatch();
    const reader = new BrowserQRCodeReader();
    if (!video.current) return;
    const videoElement = video.current;
    void reader.decodeFromVideoDevice(undefined, videoElement, (result) => {
      if (!active || !result || !latch.accept()) return;
      controls?.stop();
      stopMediaTracks(videoElement.srcObject as MediaStream | null);
      callback.current(result.getText());
    }).then((value) => {
      if (!active || latch.hasAccepted()) { value.stop(); return; }
      controls = value; setScanning(true);
    }).catch(() => {
      stopMediaTracks(videoElement.srcObject as MediaStream | null);
      if (active) setError("Camera permission was denied or no webcam is available.");
    });
    return () => { active = false; controls?.stop(); stopMediaTracks(videoElement.srcObject as MediaStream | null); };
  }, []);

  return <div className="kiosk-card min-w-0 overflow-hidden bg-[#0b474f] p-3 text-white">
    <div className="relative flex h-[min(52vh,390px)] min-h-[245px] items-center justify-center overflow-hidden rounded-xl bg-[#0b343a]">
      <video ref={video} autoPlay muted playsInline aria-label="Webcam QR scanner" className="h-full w-full object-contain" />
      <span className="kiosk-scan-corner tl" aria-hidden="true" /><span className="kiosk-scan-corner tr" aria-hidden="true" /><span className="kiosk-scan-corner bl" aria-hidden="true" /><span className="kiosk-scan-corner br" aria-hidden="true" />
      {scanning && <span className="kiosk-scan-line" aria-hidden="true" />}
      <p className="absolute left-3 top-3 rounded-full border border-[#53c7b5] bg-[#0b474f]/90 px-3 py-1 text-sm font-bold">{error ? "CAMERA UNAVAILABLE" : scanning ? "● CAMERA READY" : "REQUESTING CAMERA"}</p>
    </div>
    <p role="status" className="mt-2 text-center text-sm">{error ? "Camera unavailable" : scanning ? "Keep the entire QR code inside the frame" : "Requesting camera permission…"}</p>
    {error && <p role="alert" className="mt-2 text-sm text-red-200">{error}</p>}
  </div>;
}
