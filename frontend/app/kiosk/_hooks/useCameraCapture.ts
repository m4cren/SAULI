"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { cameraErrorMessage, captureVideoFrame, stopCameraStream } from "./cameraCapture";

type CameraStatus = "idle" | "requesting" | "live" | "error";

export default function useCameraCapture() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const requestId = useRef(0);
  const [status, setStatus] = useState<CameraStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const release = useCallback(() => {
    requestId.current += 1;
    const stream = streamRef.current;
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    stopCameraStream(stream);
  }, []);

  const stop = useCallback(() => { release(); setStatus("idle"); }, [release]);

  const start = useCallback(async () => {
    release();
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser cannot access a camera. Use localhost or HTTPS, or upload the images instead.");
      setStatus("error");
      return;
    }
    const currentRequest = requestId.current;
    setStatus("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      if (currentRequest !== requestId.current) { stopCameraStream(stream); return; }
      streamRef.current = stream;
      for (const track of stream.getVideoTracks()) {
        track.addEventListener("ended", () => {
          if (streamRef.current !== stream) return;
          release();
          setError("The camera disconnected. Reconnect it and try again, or upload an image instead.");
          setStatus("error");
        }, { once: true });
      }
      if (!videoRef.current) throw new Error("Camera preview is unavailable.");
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      if (currentRequest === requestId.current) setStatus("live");
    } catch (cause) {
      if (currentRequest !== requestId.current) return;
      release();
      setError(cameraErrorMessage(cause));
      setStatus("error");
    }
  }, [release]);

  const capture = useCallback(async (side: "front" | "back") => {
    if (status !== "live" || !videoRef.current || !canvasRef.current)
      throw new Error("Wait for the live camera preview before capturing.");
    try { return await captureVideoFrame(videoRef.current, canvasRef.current, side); }
    finally { stop(); }
  }, [status, stop]);

  useEffect(() => () => release(), [release]);

  return { videoRef, canvasRef, status, error, start, stop, capture };
}
