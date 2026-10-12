import test from "node:test";
import assert from "node:assert/strict";
import { filterRetrievals, retrievalRecords, toCsv, manilaDateKey, hasPrototypeFootage } from "../_data/mockAdminData.ts";
import { setDoorUnlocked } from "../_lib/adminState.ts";

test("retrieval filters combine case-insensitive search, Manila date, and compartment", () => {
  assert.equal(filterRetrievals(retrievalRecords, "BLACK WALLET", "2026-09-09", "P-07")[0]?.id, "R-1086");
  assert.equal(filterRetrievals(retrievalRecords, "wallet", "2026-09-08", "P-07").length, 0);
  assert.equal(filterRetrievals(retrievalRecords, "", "2026-09-09", "").length, 2);
  assert.equal(manilaDateKey("2026-09-08T18:00:00Z"), "2026-09-09");
});

test("CSV exports only selected records and escapes values", () => {
  const csv = toCsv(filterRetrievals(retrievalRecords, "Angela", "", ""));
  assert.match(csv, /^Retrieval ID,Date and Time,Retriever,Item,Compartment,Status,Completion Source\r\n/);
  assert.match(csv, /"Web simulation"/);
  assert.match(csv, /"R-1087"/);
  assert.doesNotMatch(csv, /R-1086/);
  assert.match(toCsv([{ ...retrievalRecords[0], item: 'Wallet, "black"' }]), /"Wallet, ""black"""/);
});

test("door unlock and relock simulations are independent and idempotent", () => {
  const first = setDoorUnlocked([], "pocket-door", true);
  const both = setDoorUnlocked(first, "medium-door", true);
  assert.deepEqual(both, ["pocket-door", "medium-door"]);
  assert.deepEqual(setDoorUnlocked(both, "pocket-door", true), both);
  assert.deepEqual(setDoorUnlocked(both, "pocket-door", false), ["medium-door"]);
});

test("archive selection has a clear missing state", () => {
  assert.equal(hasPrototypeFootage("front", "2026-09-08", "15:30"), true);
  assert.equal(hasPrototypeFootage("rear", "2026-09-08", "15:30"), false);
  assert.equal(hasPrototypeFootage("front", "2026-09-09", "15:30"), false);
  assert.equal(hasPrototypeFootage("front", "2026-09-08", "15:40"), false);
});
