import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import { maskEmail } from "../libs/claimant/maskEmail.ts";
import { normalizeNotificationEmail } from "../libs/claimant/notificationEmail.ts";

const require = createRequire(import.meta.url);
const root = new URL("../", import.meta.url);
const link = ({ href, children }) => React.createElement("a", { href }, children);
const button = ({ children, ...props }) => React.createElement("button", props, children);

function loadComponent(relativePath, mocks) {
  const source = readFileSync(fileURLToPath(new URL(relativePath, root)), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: {
    jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022, esModuleInterop: true,
  } }).outputText;
  const testModule = { exports: {} };
  vm.runInNewContext(code, {
    module: testModule, exports: testModule.exports,
    require: (name) => mocks[name] ?? require(name),
  });
  return testModule.exports.default;
}

test("the post form prefills account email and renders no phone or SMS controls", () => {
  const Form = loadComponent("app/(claimant)/missing/report/_components/MissingItemForm.tsx", {
    "next/link": link,
    "next/navigation": { useRouter: () => ({ push() {} }) },
    "@/app/components/BackButton": link,
    "@/app/components/Button": button,
    "@/hooks/useAuth": { useAuth: () => ({ user: { email: "auth@example.com" } }) },
    "@/hooks/useClaimant": { useClaimant: () => ({ state: {
      searchRequestId: "search-id", searchSummary: "Lost wallet",
      searchDraft: { description: "wallet" },
    }, postMissingReport: async () => {} }) },
    "@/libs/claimant/notificationEmail": { normalizeNotificationEmail },
  });
  const html = renderToStaticMarkup(React.createElement(Form));
  assert.match(html, /id="notification-email"[^>]*value="auth@example.com"/);
  assert.match(html, /type="email"/);
  assert.match(html, /Lost wallet/);
  assert.doesNotMatch(html, /SMS|phone number|type="tel"/i);
});

test("posted-report screen shows masked email, guidance, and accessible actions", () => {
  const Report = loadComponent("app/(claimant)/missing/active/_components/ActiveMissingReport.tsx", {
    "next/link": link,
    "@/app/components/Icon": () => React.createElement("span"),
    "@/hooks/useClaimant": { useClaimant: () => ({ state: { missingReport: {
      id: "report-id", summary: "Lost wallet", notificationEmail: "renren@example.com",
      emailEnabled: true, status: "active",
    } } }) },
    "@/libs/claimant/maskEmail": { maskEmail },
  });
  const html = renderToStaticMarkup(React.createElement(Report));
  assert.match(html, /role="status" aria-live="polite"/);
  assert.match(html, /Missing item report posted/);
  assert.match(html, /SAULI will email you when a possible match is found/);
  assert.match(html, /ren••••••@example.com/);
  assert.doesNotMatch(html, /renren@example.com|confirmation email/i);
  assert.match(html, /Spam or Promotions/);
  assert.match(html, /href="\/missing\/reports\/report-id"[^>]*>View my report/);
  assert.match(html, /href="\/"[^>]*>Back to home/);
});
