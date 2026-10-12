import assert from "node:assert/strict";
import test from "node:test";
import { initialKioskState, kioskReducer } from "../_hooks/kioskReducer.ts";

const move = (state, action) => kioskReducer(state, action);
const review = { name: "Blue reusable water bottle with a loop handle", summary: "Blue metal bottle", category: "Drinkware", color: "Blue", material: "Metal", size: "Pocket-size" };

test("found item shows summary preview before identified result", () => {
  let state = move(initialKioskState, { type: "START_FOUND" });
  state = move(state, { type: "SIDE_ACCEPTED", side: "front" });
  assert.equal(state.screen.step, "captureFront");
  state = move(state, { type: "IMAGE_SELECTED", kind: "front", url: "blob:front" });
  state = move(state, { type: "SIDE_ACCEPTED", side: "front" });
  assert.equal(state.screen.step, "captureBack");
  state = move(state, { type: "IMAGE_SELECTED", kind: "back", url: "blob:back" });
  state = move(state, { type: "SIDE_ACCEPTED", side: "back" });
  state = move(state, { type: "IDENTIFY_STARTED" });
  assert.equal(state.screen.step, "foundLocation");
  state = move(state, { type: "LOCATION_CHANGED", value: "Library" });
  state = move(state, { type: "IDENTIFY_STARTED" });
  state = move(state, { type: "IDENTIFIED", review, size: "pocket" });
  assert.equal(state.screen.step, "review");
  assert.equal(state.storageSize, "pocket");
  state = move(state, { type: "CORRECTION_NOTE_CHANGED", value: "Scratch near base" });
  state = move(state, { type: "SAVE_REVIEW" });
  assert.equal(state.screen.step, "summary");
  assert.deepEqual(state.review, review);
  assert.equal(state.correctionNote, "Scratch near base");
  state = move(state, { type: "RESET" });
});

test("a corrected Qwen size replaces the original suggestion", () => {
  const state = move({ ...initialKioskState, screen: { mode: "found", step: "review" }, review, storageSize: "pocket" },
    { type: "REVIEW_RECONCILED", review: { ...review, size: "Medium-size" }, size: "medium" });
  assert.equal(state.screen.step, "summary");
  assert.equal(state.storageSize, "medium");
});

test("wrong placement blocks correct placement until removal", () => {
  let state = { ...initialKioskState, screen: { mode: "found", step: "summary" }, review };
  state = move(state, { type: "FOUND_CONFIRMED" });
  assert.equal(state.screen.step, "placement");
  state = move(state, { type: "WRONG_PLACEMENT" });
  assert.equal(state.modal, "wrongPlacement");
  state = move(state, { type: "CORRECT_PLACEMENT" });
  assert.equal(state.screen.step, "placement");
  state = move(state, { type: "WRONG_PLACEMENT_REMOVED" });
  assert.equal(state.screen.step, "placement");
  state = move(state, { type: "CORRECT_PLACEMENT" });
  assert.equal(state.screen.step, "placementCorrect");
  state = move(state, { type: "DOOR_CLOSED" });
  assert.equal(state.screen.step, "stored");
});

test("wrong retrieval returns to location without completing", () => {
  let state = move(initialKioskState, { type: "START_RETRIEVE" });
  state = move(state, { type: "QR_CHECK_STARTED" });
  state = move(state, { type: "QR_VALID", retrieval: { id: "session-1", status: "validated", item_summary: "Watch", slot_code: "M-04", section: "medium", slot_status: "occupied", action_token: "test" } });
  assert.equal(state.validatedRetrieval.slot_code, "M-04");
  state = move(state, { type: "SHOW_ITEM_LOCATION" });
  state = move(state, { type: "WRONG_ITEM" });
  state = move(state, { type: "CORRECT_ITEM" });
  assert.equal(state.modal, "wrongItem");
  assert.equal(state.screen.step, "itemLocation");
  state = move(state, { type: "WRONG_ITEM_RETURNED" });
  assert.equal(state.screen.step, "itemLocation");
  state = move(state, { type: "CORRECT_ITEM" });
  assert.equal(state.screen.step, "retrieved");
});

test("invalid QR can be retried and reset clears images", () => {
  let state = move(initialKioskState, { type: "START_RETRIEVE" });
  state = move(state, { type: "QR_CHECK_STARTED" });
  state = move(state, { type: "QR_INVALID", message: "Already used", code: "RETRIEVAL_QR_ALREADY_USED" });
  assert.equal(state.screen.step, "invalidQr");
  assert.equal(state.qrErrorCode, "RETRIEVAL_QR_ALREADY_USED");
  state = move(state, { type: "TRY_ANOTHER_QR" });
  assert.equal(state.screen.step, "uploadQr");
  state = move(state, { type: "IMAGE_SELECTED", kind: "qr", url: "blob:qr" });
  state = move(state, { type: "RESET" });
  assert.deepEqual(state.images, { front: null, back: null, qr: null });
  assert.deepEqual(state.screen, { mode: "home" });
});
