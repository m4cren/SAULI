import test from "node:test";
import assert from "node:assert/strict";
import { pocketCodes, mediumCodes, slotCodes, slotTotals, isSlotCode } from "../libs/storage/slots.ts";
import { initialKioskState, kioskReducer } from "../app/kiosk/_hooks/kioskReducer.ts";
import { initialClaimantState, claimantReducer } from "../libs/claimant/claimantReducer.ts";

const assigned = { item_id: "item-1", status: "available", storage_size: "medium", section: "Medium-size", slot_code: "M-02", slot_status: "reserved", placement_status: "reserved" };

test("shared cabinet layout contains exactly the supported unique positions", () => {
  assert.equal(pocketCodes.length, 10);
  assert.equal(mediumCodes.length, 5);
  assert.equal(new Set(slotCodes).size, 15);
  assert.equal(slotCodes[0], "P-01");
  assert.equal(slotCodes.at(-1), "M-05");
  assert.ok(isSlotCode("M-02"));
  assert.ok(!isSlotCode("C3"));
});

test("kiosk uses the assigned API position and requires placement before success", () => {
  assert.equal(initialKioskState.storageSize, null);
  let state = { ...initialKioskState, screen: { mode: "found", step: "summary" } };
  state = kioskReducer(state, { type: "SIZE_SELECTED", size: "medium" });
  assert.equal(state.storageSize, "medium");
  state = kioskReducer(state, { type: "FOUND_CONFIRMED", assignment: assigned });
  assert.equal(state.assignment.slot_code, "M-02");
  assert.equal(state.screen.step, "placement");
  state = kioskReducer(state, { type: "PLACEMENT_SUCCEEDED", assignment: { ...assigned, slot_status: "occupied", placement_status: "placed" } });
  assert.equal(state.screen.step, "stored");
  assert.equal(state.assignment.slot_status, "occupied");
});

test("full section does not create an assignment", () => {
  const state = kioskReducer({ ...initialKioskState, screen: { mode: "found", step: "summary" } }, { type: "NO_SLOTS", size: "pocket" });
  assert.equal(state.screen.step, "noSlots");
  assert.equal(state.fullSize, "pocket");
  assert.equal(state.assignment, null);
});

test("claimant confirmation does not reveal a storage position", () => {
  const item = { id: "item-1", itemId: "item-1", name: "Watch" };
  const state = claimantReducer(initialClaimantState, { type: "CLAIM_CONFIRMED", item, session: { id: "session-1", qrPayload: "SAULI:RETRIEVAL:v1:example", issuedAt: "2026-10-11T00:00:00Z", expiresAt: "2026-10-11T03:00:00Z", status: "issued", itemSummary: item.name } });
  assert.equal(state.confirmedSlot, undefined);
  assert.equal(state.retrievalSession.itemSummary, item.name);
  assert.equal(state.selectedItem.id, "item-1");
});

test("admin totals change when a polled slot changes state", () => {
  const first = [{ status: "available" }, { status: "reserved" }, { status: "occupied" }];
  assert.deepEqual(slotTotals(first), { available: 1, reserved: 1, occupied: 1, out_of_service: 0 });
  assert.deepEqual(slotTotals([{ status: "occupied" }, ...first.slice(1)]), { available: 0, reserved: 1, occupied: 2, out_of_service: 0 });
});
