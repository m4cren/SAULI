import test from "node:test";
import assert from "node:assert/strict";
import { pocketCodes, mediumCodes, slotCodes, slotTotals, isSlotCode } from "../libs/storage/slots.ts";
import { initialKioskState, kioskReducer } from "../app/kiosk/_hooks/kioskReducer.ts";
import { initialClaimantState, claimantReducer } from "../libs/claimant/claimantReducer.ts";
import { isAllowedKioskAction } from "../libs/api/kiosk-actions.ts";
import { resolveUnlockStatus } from "../app/kiosk/_hooks/kioskUnlockStatus.ts";

test("kiosk observes a committed unlock and does not show a failed command as waiting", () => {
  const waiting = { phase: "awaiting_door_open", unlock_retry_available: false,
    unlock_command_status: "pending", last_unlock: null };
  assert.equal(resolveUnlockStatus("unavailable", waiting), "queued");
  assert.equal(resolveUnlockStatus("queued", { ...waiting, unlock_command_status: "failed" }), "unavailable");
  assert.equal(resolveUnlockStatus("queued", { ...waiting, unlock_command_status: "acked",
    last_unlock: { status: "rejected" } }), "unavailable");
  assert.equal(resolveUnlockStatus("queued", { ...waiting, phase: null,
    unlock_command_status: null }), "unavailable");
  assert.equal(resolveUnlockStatus("queued", { ...waiting, unlock_retry_available: true }), "unavailable");
});

test("kiosk proxy permits both guarded unlock requests and rejects unrelated actions", () => {
  const id = "a74c1c56-650a-407e-b946-f2c25482093c";
  assert.equal(isAllowedKioskAction(`found-items/${id}/request-unlock`), true);
  assert.equal(isAllowedKioskAction(`retrieval-sessions/${id}/request-unlock`), true);
  assert.equal(isAllowedKioskAction(`found-items/${id}/simulate-placement`), true);
  assert.equal(isAllowedKioskAction(`found-items/${id}/delete`), false);
  assert.equal(isAllowedKioskAction("found-items/not-a-uuid/request-unlock"), false);
});

const assigned = { item_id: "item-1", status: "available", storage_size: "medium", section: "Medium-size", slot_code: "M-02", slot_status: "reserved", placement_status: "reserved" };

test("shared cabinet layout contains exactly the supported unique positions", () => {
  assert.equal(pocketCodes.length, 8);
  assert.equal(mediumCodes.length, 4);
  assert.equal(new Set(slotCodes).size, 12);
  assert.equal(slotCodes[0], "P-01");
  assert.equal(pocketCodes.at(-1), "P-08");
  assert.equal(slotCodes.at(-1), "M-04");
  assert.ok(isSlotCode("M-02"));
  for (const removed of ["P-09", "P-10", "M-05"]) assert.ok(!isSlotCode(removed));
  assert.ok(!isSlotCode("C3"));
  const allRows = [...slotCodes.map(() => ({ status: "available", is_active: true })),
    ...["P-09", "P-10", "M-05"].map(() => ({ status: "available", is_active: false }))];
  assert.equal(slotTotals(allRows).total, 12);
  assert.equal(slotTotals(allRows).available, 12);
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
  const first = [{ status: "available" }, { status: "reserved" }, { status: "occupied" }, { status: "out_of_service" }];
  assert.deepEqual(slotTotals(first), { total: 4, available: 1, reserved: 1, occupied: 1, out_of_service: 1, unavailable: 2 });
  assert.deepEqual(slotTotals([{ status: "occupied" }, ...first.slice(1), { status: "occupied", is_active: false }]),
    { total: 4, available: 0, reserved: 1, occupied: 2, out_of_service: 1, unavailable: 2 });
});
