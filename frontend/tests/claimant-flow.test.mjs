import assert from "node:assert/strict";
import test from "node:test";
import { claimantReducer, initialClaimantState } from "../libs/claimant/claimantReducer.ts";

const item = {
  id: "match-014",
  itemId: "SL-2026-0819-014",
  name: "Black leather wallet",
  matchPercent: 92,
  storageStatus: "stored",
  foundLocation: "LSPU Library, 2nd Floor",
  foundAt: "2026-08-19T12:45:00+08:00",
  compartmentId: "P-05",
};
const pass = {
  itemId: item.itemId,
  itemName: item.name,
  compartmentId: "P-05",
  createdAt: "2026-08-21T00:00:00Z",
  expiresAt: "2026-08-21T00:10:00Z",
  prototype: true,
};
const update = (state, action) => claimantReducer(state, action);

test("a wrong lift blocks completion until the item is returned", () => {
  let state = update(initialClaimantState, { type: "RETRIEVAL_PASS_CREATED", item, pass });
  state = update(state, { type: "STATION_SCAN_SIMULATED", at: Date.parse("2026-08-21T00:05:00Z") });
  assert.equal(state.retrievalStatus, "waitingForCorrectItem");

  state = update(state, { type: "WRONG_ITEM_LIFTED" });
  assert.equal(state.retrievalStatus, "waitingForWrongItemReturn");
  assert.equal(state.wrongCompartmentId, "P-06");
  assert.equal(state.incident.returnedAt, null);

  state = update(state, { type: "CORRECT_ITEM_LIFTED", retriever: "Rainier Reyes", at: "2026-08-21T00:06:00Z" });
  assert.equal(state.retrievalStatus, "waitingForWrongItemReturn");
  assert.equal(state.retrievalHistory.length, 0);

  state = update(state, { type: "WRONG_ITEM_RETURNED", at: "2026-08-21T00:07:00Z" });
  assert.equal(state.retrievalStatus, "waitingForCorrectItem");
  assert.equal(state.incident.returnedAt, "2026-08-21T00:07:00Z");

  state = update(state, { type: "CORRECT_ITEM_LIFTED", retriever: "Rainier Reyes", at: "2026-08-21T00:08:00Z" });
  assert.equal(state.retrievalStatus, "retrieved");
  assert.equal(state.retrievalHistory[0].compartmentId, "P-05");
  assert.equal(state.retrievalHistory[0].retriever, "Rainier Reyes");
});

test("an expired pass cannot be scanned", () => {
  let state = update(initialClaimantState, { type: "RETRIEVAL_PASS_CREATED", item, pass });
  state = update(state, { type: "STATION_SCAN_SIMULATED", at: Date.parse(pass.expiresAt) });
  assert.equal(state.retrievalStatus, "qrExpired");
  state = update(state, { type: "WRONG_ITEM_LIFTED" });
  assert.equal(state.retrievalStatus, "qrExpired");
});

test("rejecting one candidate leaves other matches available", () => {
  const other = { ...item, id: "match-015", itemId: "SL-2026-0819-015" };
  let state = update(initialClaimantState, { type: "SEARCH_SUCCEEDED", results: [item, other] });
  state = update(state, { type: "ITEM_SELECTED", item });
  state = update(state, { type: "CANDIDATE_REJECTED", itemId: item.id });
  assert.equal(state.selectedItem, null);
  assert.deepEqual(state.rejectedCandidateIds, [item.id]);
  state = update(state, { type: "ITEM_SELECTED", item });
  assert.equal(state.selectedItem, null);
  state = update(state, { type: "ITEM_SELECTED", item: other });
  assert.equal(state.selectedItem.id, other.id);
});
