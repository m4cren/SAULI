"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Button from "@/app/components/Button";
import { useKiosk } from "../_hooks/useKioskFlow";
import useCameraCapture from "../_hooks/useCameraCapture";
import FlowHeading from "./FlowHeading";
import ImageDropzone from "./ImageDropzone";

type CaptureMode = "camera" | "review" | "upload";

export default function ItemCaptureStep({ side }: { side: 1 | 2 }) {
  const kiosk = useKiosk();
  const kind = side === 1 ? "front" : "back";
  const image = kiosk.state.images[kind];
  const { videoRef, canvasRef, status, error: cameraError, start, stop, capture } = useCameraCapture();
  const [mode, setMode] = useState<CaptureMode>(() => kiosk.captureSource.current);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);

  useEffect(() => {
    if (kiosk.captureSource.current !== "camera") return;
    // Defer startup so React's development effect replay cannot request the
    // same webcam twice before the first permission request settles.
    const timer = window.setTimeout(() => { if (kiosk.captureSource.current === "camera") void start(); }, 0);
    return () => window.clearTimeout(timer);
  }, [side, start, kiosk.captureSource]);
  useEffect(() => {
    if (kiosk.state.modal) stop();
  }, [kiosk.state.modal, stop]);

  function startCamera() {
    kiosk.chooseCaptureSource("camera");
    setCaptureError(null);
    setMode("camera");
    void start();
  }

  function chooseUpload() {
    stop();
    kiosk.chooseCaptureSource("upload");
    setCaptureError(null);
    setMode("upload");
  }

  async function takePhoto() {
    if (capturing) return;
    setCapturing(true);
    setCaptureError(null);
    try {
      const file = await capture(kind);
      kiosk.selectFile(kind, file);
      setMode("review");
    } catch (cause) {
      setCaptureError(cause instanceof Error ? cause.message : "Capture failed. Try again or upload an image.");
    } finally { setCapturing(false); }
  }

  const instruction = side === 1
    ? "Place the front side of the item facing the camera."
    : "Turn the item over and place the back side facing the camera.";
  const isLive = mode === "camera" && status === "live";
  const showPhoto = (mode === "review" || mode === "upload") && image;
  const visibleError = captureError || (mode === "camera" ? cameraError : null) || kiosk.state.error;

  return <>
    <FlowHeading flow="found" current={1} compact title={side === 1 ? "Capture the front image" : "Capture the back image"}
      subtitle="Place the item on the SAULI scanning platform. Capture both sides before analysis." />
    <nav aria-label="Image capture progress" className="mb-3 grid grid-cols-3 gap-2 text-center text-xs font-semibold sm:text-sm">
      {(["Front", "Back", "Review"] as const).map((label, index) => <span key={label}
        aria-current={index + 1 === side ? "step" : undefined}
        className={`rounded-lg border px-2 py-2 ${index + 1 === side ? "border-[#0B474F] bg-[#d7e6e6] text-[#0B474F]" : "border-[#d5d5d5] text-[#555]"}`}>{index + 1}. {label}</span>)}
    </nav>
    <div className="grid gap-4 sm:grid-cols-[minmax(0,1.7fr)_minmax(270px,1fr)]">
      <section className="rounded-2xl border border-[#d3d7d7] bg-[#e8eeee] p-3 sm:p-4">
        <div className={`relative flex min-h-[220px] items-center justify-center overflow-hidden rounded-xl sm:min-h-[260px] ${mode === "upload" ? "bg-[#e8eeee]" : "bg-[#102c30]"}`}>
          <video ref={videoRef} autoPlay muted playsInline aria-label={`${kind} image live camera preview`}
            className={`${isLive ? "block" : "hidden"} max-h-[min(45vh,330px)] w-full object-contain`} />
          {isLive && <div aria-hidden="true" className="pointer-events-none absolute inset-[8%] rounded-xl border-2 border-dashed border-white/85" />}
          {mode === "upload" ? <div className="w-full"><ImageDropzone kind={kind} compact title={`Upload ${kind} image`} hint="Choose or drop a PNG, JPEG, or WebP image." /></div> :
            showPhoto ? <div className="relative h-[min(45vh,330px)] min-h-[220px] w-full"><Image src={image} alt={`${kind} side captured image`} fill unoptimized sizes="(max-width: 900px) 90vw, 650px" className="object-contain" /></div> :
            !isLive && <p className="px-6 text-center text-base font-semibold text-white">{mode === "camera" && status === "requesting" ? "Requesting camera permission…" :
              mode === "camera" && status === "error" ? "Camera unavailable" : "Camera preview is paused"}</p>}
        </div>
        <canvas ref={canvasRef} className="hidden" aria-hidden="true" />
      </section>
      <section className="flex flex-col rounded-2xl border border-[#d4d4d4] bg-white p-4">
        <h2 className="text-xl font-semibold text-[#092a2f]">{side === 1 ? "1. Front" : "2. Back"}</h2>
        <p className="mt-2 text-base font-medium leading-snug text-[#092a2f]">{instruction}</p>
        <p className="mt-2 text-sm text-[#444]">Center the whole item and show any marks.</p>
        {visibleError && <p role="alert" className="mt-4 text-sm text-red-700">{visibleError}</p>}
        <div className="mt-auto grid gap-2 pt-3">
          {mode === "camera" && status === "live" && <Button type="button" disabled={capturing} onClick={() => void takePhoto()} className="w-full">{capturing ? "Capturing…" : `Capture ${kind} image`}</Button>}
          {mode === "camera" && status !== "live" && status !== "requesting" && <Button type="button" onClick={startCamera} className="w-full">Try camera again</Button>}
          {mode === "review" && <><Button type="button" onClick={() => { stop(); kiosk.acceptSide(kind); }} className="w-full">Use this image</Button><Button type="button" variant="outline" onClick={startCamera} className="w-full">Retake</Button></>}
          {mode === "upload" && <Button type="button" disabled={!image} onClick={() => kiosk.acceptSide(kind)} className="w-full">Use this image</Button>}
          {mode !== "upload" && <Button type="button" variant="outline" onClick={chooseUpload} className="w-full">Upload image instead</Button>}
          {mode === "upload" && <Button type="button" variant="outline" onClick={startCamera} className="w-full">Use PC webcam instead</Button>}
          <Button type="button" variant="outline" onClick={kiosk.requestCancel} className="w-full">Cancel</Button>
        </div>
      </section>
    </div>
  </>;
}
