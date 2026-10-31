"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Button from "@/app/components/Button";
import Icon from "@/app/components/Icon";
import { useKiosk } from "../_hooks/useKioskFlow";
import useCameraCapture from "../_hooks/useCameraCapture";
import FlowHeading from "./FlowHeading";

type CaptureMode = "camera" | "review";

export default function ItemCaptureStep({ side }: { side: 1 | 2 }) {
  const kiosk = useKiosk();
  const kind = side === 1 ? "front" : "back";
  const image = kiosk.state.images[kind];
  const { videoRef, canvasRef, status, error: cameraError, start, stop, capture } = useCameraCapture();
  const [mode, setMode] = useState<CaptureMode>("camera");
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => { void start(); }, 0);
    return () => window.clearTimeout(timer);
  }, [side, start]);
  useEffect(() => { if (kiosk.state.modal) stop(); }, [kiosk.state.modal, stop]);

  function startCamera() { setCaptureError(null); setMode("camera"); void start(); }
  async function takePhoto() {
    if (capturing) return;
    setCapturing(true); setCaptureError(null);
    try { const file = await capture(kind); kiosk.selectFile(kind, file); setMode("review"); }
    catch (cause) { setCaptureError(cause instanceof Error ? cause.message : "Capture failed. Try again."); }
    finally { setCapturing(false); }
  }

  const isLive = mode === "camera" && status === "live";
  const showPhoto = mode === "review" && image;
  const visibleError = captureError || (mode === "camera" ? cameraError : null) || kiosk.state.error;
  const title = mode === "review" ? `Review the ${side === 1 ? "first" : "second"} side` : `Capture the ${side === 1 ? "first" : "second"} side`;
  const subtitle = mode === "review" ? "Make sure the item is clear before continuing." : side === 1 ? "Place the entire item inside the camera frame." : "Turn the same item over and place it inside the camera frame.";

  return <><FlowHeading flow="found" current={1} compact title={title} subtitle={subtitle} />
    <div className="kiosk-grid"><section className="kiosk-card min-w-0 bg-[#edf8f6] p-3">
      <div className="relative flex h-[min(49vh,380px)] min-h-[230px] items-center justify-center overflow-hidden rounded-xl bg-[#133d42]">
        <video ref={videoRef} autoPlay muted playsInline aria-label={`${kind} image live camera preview`} className={`${isLive ? "block" : "hidden"} h-full w-full object-contain`} />
        {isLive && <div aria-hidden="true" className="pointer-events-none absolute inset-[7%] rounded-xl border-2 border-dashed border-[#b7f1e9]" />}
        {showPhoto ? <><Image src={image} alt={`Captured side ${side} of the item`} fill unoptimized sizes="(max-width: 900px) 90vw, 650px" className="object-contain" /><span className="kiosk-pill absolute left-3 top-3">✓ Photo captured</span></> :
          !isLive && <div className="px-5 text-center text-white"><Icon name="camera" size={50} className="mx-auto mb-2" /><p className="text-lg font-bold">{status === "requesting" ? "Requesting camera permission…" : status === "error" ? "Camera unavailable" : "Place item inside the frame"}</p></div>}
      </div><canvas ref={canvasRef} className="hidden" aria-hidden="true" />
    </section>
    <section className="kiosk-card flex min-w-0 flex-col p-3 sm:p-4"><div className="grid grid-cols-2 gap-2" aria-label="Capture progress"><div className={`rounded-xl border p-1 text-center ${side === 1 || kiosk.state.images.front ? "border-[#28b5a7] bg-[#e4f8f4]" : "border-[#d3dce0]"}`}><strong className="block text-lg">Side 1 {side === 2 ? "✓" : ""}</strong><span className="text-sm">{side === 2 ? "Captured" : mode === "review" ? "Captured" : "Ready"}</span></div><div className={`rounded-xl border p-1 text-center ${side === 2 ? "border-[#28b5a7] bg-[#e4f8f4]" : "border-[#d3dce0] text-[#87929a]"}`}><strong className="block text-lg">Side 2</strong><span className="text-sm">{side === 2 ? mode === "review" ? "Captured" : "Ready" : "Waiting"}</span></div></div>
      <h2 className="mt-3 text-[clamp(20px,2.2vw,28px)] font-bold">{mode === "review" ? "Check this photo" : "Before capturing"}</h2>
      <ul className="mt-2 grid gap-1 text-[clamp(14px,1.4vw,17px)]">{(mode === "review" ? ["The entire item is visible.", "The photo is clear and in focus.", "No hands are inside the frame."] : ["Remove your hands from the frame.", "Make the brand, color, and marks visible.", "Do not scan loose money or unsafe items."]).map((item, index) => <li key={item} className="flex items-center gap-2"><span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-[#d6f4ee] font-bold text-[#0b474f]">{mode === "review" ? "✓" : index + 1}</span>{item}</li>)}</ul>
      {visibleError && <p role="alert" className="mt-2 max-h-12 overflow-y-auto text-sm text-red-700">{visibleError}</p>}
      <div className="mt-auto grid gap-2 pt-2">
        {mode === "camera" && status === "live" && <Button type="button" disabled={capturing} onClick={() => void takePhoto()} className="kiosk-button kiosk-button-primary">{capturing ? "Capturing…" : `Capture side ${side}`}</Button>}
        {mode === "camera" && status !== "live" && status !== "requesting" && <Button type="button" onClick={startCamera} className="kiosk-button kiosk-button-primary">Try camera again</Button>}
        {mode === "review" && <><Button type="button" onClick={() => { stop(); kiosk.acceptSide(kind); }} className="kiosk-button kiosk-button-primary">Confirm</Button><Button type="button" variant="outline" onClick={startCamera} className="kiosk-button">Retake</Button></>}
        {mode !== "review" && <Button type="button" variant="outline" onClick={kiosk.requestCancel} className="kiosk-button">Cancel</Button>}
      </div>
    </section></div></>;
}
