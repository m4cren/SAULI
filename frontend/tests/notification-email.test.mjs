import assert from "node:assert/strict";
import test from "node:test";
import { maskEmail } from "../libs/claimant/maskEmail.ts";
import { normalizeNotificationEmail } from "../libs/claimant/notificationEmail.ts";

test("claimant can edit a prefilled email and invalid addresses cannot be posted", () => {
  assert.equal(normalizeNotificationEmail("  New.Address@Example.com  "), "new.address@example.com");
  assert.equal(normalizeNotificationEmail(""), null);
  assert.equal(normalizeNotificationEmail("name@"), null);
  assert.equal(normalizeNotificationEmail("a".repeat(250) + "@example.com"), null);
});

test("report success masks the local part without exposing the full address", () => {
  assert.equal(maskEmail("renren@example.com"), "ren••••••@example.com");
  assert.notEqual(maskEmail("renren@example.com"), "renren@example.com");
});
