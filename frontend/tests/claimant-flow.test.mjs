import assert from "node:assert/strict";
import test from "node:test";
import { claimantReducer, initialClaimantState } from "../libs/claimant/claimantReducer.ts";

const item = { id: "item-1", itemId: "item-1", matchCandidateId: "candidate-1", name: "Watch", matchPercent: 92,
  storageStatus: "stored", foundLocation: "Library", foundAt: "2026-10-11T12:00:00+08:00" };
const other = { ...item, id: "item-2", itemId: "item-2", matchCandidateId: "candidate-2" };

test("rejecting one candidate leaves the next search result available", () => {
  let state = claimantReducer(initialClaimantState, { type: "SEARCH_SUCCEEDED", results: [item, other] });
  state = claimantReducer(state, { type: "ITEM_SELECTED", item });
  state = claimantReducer(state, { type: "CANDIDATE_REJECTED", itemId: item.id });
  assert.equal(state.selectedItem, null);
  assert.deepEqual(state.rejectedCandidateIds, [item.id]);
  state = claimantReducer(state, { type: "ITEM_SELECTED", item: other });
  assert.equal(state.selectedItem.id, other.id);
});

test("confirmed claim stores only the QR session until kiosk validation", () => {
  let state = claimantReducer(initialClaimantState, { type: "SEARCH_SUCCEEDED", results: [item] });
  const session = { id: "session-1", qrPayload: "SAULI:RETRIEVAL:v1:example", issuedAt: "2026-10-11T00:00:00Z", expiresAt: "2026-10-11T03:00:00Z", status: "issued", itemSummary: "Watch", validatedAt: null, completedAt: null, slotCode: null, section: null, wrongItemOut: false, retriever: null };
  state = claimantReducer(state, { type: "CLAIM_CONFIRMED", item, session });
  assert.deepEqual(state.retrievalSession, session);
  assert.equal(state.confirmedSlot, undefined);
  assert.equal(state.retrievalHistory.length, 0);
  const result = { id: session.id, issued_at: session.issuedAt, expires_at: session.expiresAt, item_summary: "Watch", status: "validated", validated_at: "2026-10-11T00:10:00Z", completed_at: null, slot_code: "P-07", section: "pocket", wrong_item_out: false, retriever: "Claimant", can_replace: false, completed: false };
  state = claimantReducer(state, { type: "RETRIEVAL_STATUS", result });
  assert.equal(state.retrievalSession.qrPayload, null);
  assert.equal(state.retrievalSession.slotCode, "P-07");
  assert.equal(state.retrievalSession.status, "validated");
  state = claimantReducer(state, { type: "RETRIEVAL_STATUS", result: { ...result, wrong_item_out: true } });
  assert.equal(state.retrievalSession.wrongItemOut, true);
  state = claimantReducer(state, { type: "RETRIEVAL_STATUS", result: { ...result, wrong_item_out: false } });
  assert.equal(state.retrievalSession.wrongItemOut, false);
  state = claimantReducer(state, { type: "RETRIEVAL_STATUS", result: { ...result, status: "completed", completed: true, completed_at: "2026-10-11T00:13:00Z" } });
  assert.equal(state.retrievalSession.status, "completed");
  assert.equal(state.retrievalSession.slotCode, "P-07");
  state = claimantReducer(state, { type: "RETRIEVAL_STATUS", result });
  assert.equal(state.retrievalSession.status, "completed");
});

test("a changed search clears the report source until new results arrive", () => {
  let state = claimantReducer(initialClaimantState, {
    type: "SEARCH_SUCCEEDED", results: [item],
    searchRequestId: "search-one", searchSummary: "Black watch",
  });
  assert.equal(state.searchRequestId, "search-one");
  state = claimantReducer(state, { type: "FILTERS_UPDATED", filters: {
    lastSeenLocation: "Canteen", lastSeenAt: "2026-10-12T08:00",
  } });
  assert.equal(state.searchRequestId, null);
  assert.equal(state.searchSummary, null);
  assert.equal(state.searchResults.length, 0);
  state = claimantReducer(state, {
    type: "SEARCH_SUCCEEDED", results: [],
    searchRequestId: "search-two", searchSummary: "Watch near canteen",
  });
  assert.equal(state.searchRequestId, "search-two");
  assert.equal(state.searchSummary, "Watch near canteen");
});
