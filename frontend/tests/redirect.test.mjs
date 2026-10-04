import assert from "node:assert/strict";
import test from "node:test";
import { safeLocalPath } from "../libs/auth/redirect.ts";

test("keeps application paths", () => {
  assert.equal(safeLocalPath("/"), "/");
  assert.equal(safeLocalPath("/home?tab=recent"), "/home?tab=recent");
});

test("rejects external and protocol-relative destinations", () => {
  for (const input of ["https://evil.example", "//evil.example", "\\evil.example", "/\\evil.example", "javascript:alert(1)", "/safe\nLocation: evil", ["/", "//evil.example"], "/auth/login#again", "/auth/callback", "/admin", "/kiosk-test?from=login"]) {
    assert.equal(safeLocalPath(input), "/");
  }
});
