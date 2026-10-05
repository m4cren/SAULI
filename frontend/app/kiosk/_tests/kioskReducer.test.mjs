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
  state = move(state, { type: "EXTRA_NOTES_CHANGED", value: "Silver scratch near base" });
  assert.equal(state.extraNotes, "Silver scratch near base");
  state = move(state, { type: "IDENTIFY_STARTED" });
  state = move(state, { type: "IDENTIFIED", review });
  assert.equal(state.screen.step, "review");
  state = move(state, { type: "CORRECTION_NOTE_CHANGED", value: "Scratch near base" });
  state = move(state, { type: "SAVE_REVIEW" });
  assert.equal(state.screen.step, "summary");
  assert.deepEqual(state.review, review);
  assert.equal(state.correctionNote, "Scratch near base");
  state = move(state, { type: "RESET" });
  assert.equal(state.extraNotes, "");
});

test("wrong placement blocks correct placement until removal", () => {
  let state = { ...initialKioskState, screen: { mode: "found", step: "summary" }, review };
  state = move(state, { type: "FOUND_CONFIRMED" });
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
  state = move(state, { type: "IMAGE_SELECTED", kind: "qr", url: "blob:qr" });
  state = move(state, { type: "QR_CHECK_STARTED" });
  state = move(state, { type: "QR_VALID" });
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
  state = move(state, { type: "QR_INVALID" });
  assert.equal(state.screen.step, "invalidQr");
  state = move(state, { type: "TRY_ANOTHER_QR" });
  assert.equal(state.screen.step, "uploadQr");
  state = move(state, { type: "IMAGE_SELECTED", kind: "qr", url: "blob:qr" });
  state = move(state, { type: "RESET" });
  assert.deepEqual(state.images, { front: null, back: null, qr: null });
  assert.deepEqual(state.screen, { mode: "home" });
});
