import assert from "node:assert/strict";
import test from "node:test";
import { cameraErrorMessage, captureVideoFrame, MAX_CAPTURE_BYTES, stopCameraStream } from "../_hooks/cameraCapture.ts";

test("camera frame becomes an unmapped JPEG file with the video aspect ratio", async () => {
  const calls = [];
  const canvas = {
    width: 0, height: 0,
    getContext: () => ({ drawImage: (...args) => calls.push(args) }),
    toBlob: (callback, mime, quality) => {
      calls.push([mime, quality]);
      callback(new Blob(["jpeg frame"], { type: mime }));
    },
  };
  const video = { videoWidth: 1920, videoHeight: 1080 };
  const front = await captureVideoFrame(video, canvas, "front");
  assert.equal(canvas.width, 1920);
  assert.equal(canvas.height, 1080);
  assert.deepEqual(calls[0], [video, 0, 0, 1920, 1080]);
  assert.deepEqual(calls[1], ["image/jpeg", 0.88]);
  assert.equal(front.name, "front-image.jpg");
  assert.equal(front.type, "image/jpeg");
  assert.equal((await captureVideoFrame(video, canvas, "back")).name, "back-image.jpg");
});

test("camera capture rejects missing frames and files beyond the existing upload limit", async () => {
  const canvas = {
    getContext: () => ({ drawImage() {} }),
    toBlob: (callback) => callback(new Blob([new Uint8Array(MAX_CAPTURE_BYTES + 1)], { type: "image/jpeg" })),
  };
  await assert.rejects(captureVideoFrame({ videoWidth: 0, videoHeight: 0 }, canvas, "front"), /live camera preview/);
  await assert.rejects(captureVideoFrame({ videoWidth: 6000, videoHeight: 4000 }, canvas, "front"), /too large/);
  await assert.rejects(captureVideoFrame({ videoWidth: 640, videoHeight: 480 }, canvas, "front"), /exceeds 10 MiB/);
});

test("camera cleanup stops every track and permission errors offer upload", () => {
  const stopped = [];
  stopCameraStream({ getTracks: () => [{ stop: () => stopped.push("video") }, { stop: () => stopped.push("audio") }] });
  assert.deepEqual(stopped, ["video", "audio"]);
  assert.match(cameraErrorMessage(Object.assign(new Error(), { name: "NotAllowedError" })), /Camera access was not allowed.*upload the images instead/);
  assert.match(cameraErrorMessage(Object.assign(new Error(), { name: "NotFoundError" })), /No camera was found/);
  assert.match(cameraErrorMessage(Object.assign(new Error(), { name: "NotReadableError" })), /already in use/);
});
