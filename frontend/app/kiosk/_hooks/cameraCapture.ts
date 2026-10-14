export const MAX_CAPTURE_BYTES = 10_485_760;
const MAX_CAPTURE_PIXELS = 20_000_000;

export function stopCameraStream(stream: MediaStream | null): void {
  stream?.getTracks().forEach((track) => track.stop());
}

export function cameraErrorMessage(cause: unknown): string {
  const name = cause instanceof Error ? cause.name : "";
  if (name === "NotAllowedError" || name === "PermissionDeniedError")
    return "Camera access was not allowed. Enable camera permission in your browser settings or upload the images instead.";
  if (name === "NotFoundError" || name === "DevicesNotFoundError")
    return "No camera was found. Connect a webcam or upload the images instead.";
  if (name === "NotReadableError" || name === "TrackStartError")
    return "The camera is already in use or could not start. Close other camera apps or upload the images instead.";
  return "The camera could not start. Use localhost or HTTPS, check your webcam, or upload the images instead.";
}

export async function captureVideoFrame(video: HTMLVideoElement, canvas: HTMLCanvasElement, side: "front" | "back"): Promise<File> {
  const { videoWidth: width, videoHeight: height } = video;
  if (!width || !height) throw new Error("Wait for the live camera preview before capturing.");
  if (width * height > MAX_CAPTURE_PIXELS) throw new Error("The camera image is too large. Choose a lower camera resolution or upload an image instead.");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("The camera frame could not be captured. Try again or upload an image.");
  context.drawImage(video, 0, 0, width, height);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.88));
  if (!blob?.size) throw new Error("The camera frame could not be saved. Try again or upload an image.");
  if (blob.size > MAX_CAPTURE_BYTES) throw new Error("The captured image exceeds 10 MiB. Try a lower camera resolution or upload an image.");
  return new File([blob], `${side}-image.jpg`, { type: "image/jpeg" });
}
