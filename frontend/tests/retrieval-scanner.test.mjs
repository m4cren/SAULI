import assert from "node:assert/strict";
import test from "node:test";
import { createScanLatch, stopMediaTracks } from "../libs/retrieval/scanner.ts";

test("duplicate webcam QR callbacks are accepted only once", () => {
  const latch = createScanLatch();
  assert.equal(latch.accept(), true);
  assert.equal(latch.accept(), false);
  assert.equal(latch.hasAccepted(), true);
  assert.equal(latch.accept(), false);
});

test("scanner cleanup stops every webcam media track", () => {
  const stopped = [];
  stopMediaTracks({ getTracks: () => [
    { stop: () => stopped.push("video") },
    { stop: () => stopped.push("audio") },
  ] });
  assert.deepEqual(stopped, ["video", "audio"]);
});
