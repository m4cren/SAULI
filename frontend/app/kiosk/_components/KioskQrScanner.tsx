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
      if (active) setError("Camera permission was denied or no webcam is available. You can upload a QR image instead.");
    });
    return () => {
      active = false;
      controls?.stop();
      stopMediaTracks(videoElement.srcObject as MediaStream | null);
    };
  }, []);

  return <div className="rounded-xl border border-[#9fc3c0] bg-[#eef6f5] p-3">
    <video ref={video} autoPlay muted playsInline aria-label="Webcam QR scanner" className="mx-auto max-h-80 w-full rounded-lg bg-black object-contain" />
    <p role="status" className="mt-2 text-sm">{error ? "Camera unavailable" : scanning ? "Scanning for a SAULI retrieval QR…" : "Requesting camera permission…"}</p>
    {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
  </div>;
}
