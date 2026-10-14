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

test("home report shortcut appears only after the account has a submitted report", () => {
  function renderShortcut(reports) {
    const Shortcut = loadComponent("app/(claimant)/_components/MissingReportsShortcut.tsx", {
      "next/link": link,
      "@/hooks/useMissingReports": { __esModule: true, default: () => ({ reports, loading: false, error: false, refresh() {} }) },
    });
    return renderToStaticMarkup(React.createElement(Shortcut));
  }
  assert.equal(renderShortcut([]), "");
  assert.match(renderShortcut([{ id: "report-one", status: "active" }]), /href="\/missing\/reports\/report-one"/);
  assert.match(renderShortcut([{ id: "report-one", status: "active" }, { id: "report-two", status: "matched" }]), /href="\/missing\/reports"/);
  assert.equal(renderShortcut([{ id: "report-one", status: "resolved" }]), "");
  assert.match(renderShortcut([{ id: "report-one", status: "resolved" }, { id: "report-two", status: "matched" }]), /href="\/missing\/reports\/report-two"/);
});

test("report list links to each submitted report and shows its stored status", () => {
  const Reports = loadComponent("app/(claimant)/missing/reports/_components/MissingReportsPage.tsx", {
    "next/link": link,
    "@/app/components/BackButton": link,
    "@/hooks/useMissingReports": { __esModule: true, default: () => ({
      reports: [{ id: "report-one", summary: "Lost blue bottle", status: "active", created_at: "2026-10-12T00:00:00Z" }],
      loading: false, error: false, refresh() {},
    }) },
    "@/libs/claimant/format": { formatDateTime: () => "Oct 12, 2026" },
  });
  const html = renderToStaticMarkup(React.createElement(Reports));
  assert.match(html, /My missing item reports/);
  assert.match(html, /href="\/missing\/reports\/report-one"/);
  assert.match(html, /Lost blue bottle/);
  assert.match(html, /active/);
});

test("a retrieved report shows completion even when its match was accepted", () => {
  function renderReview(status) {
    const state = [
      { id: "report-one", summary: "Lost blue bottle", status,
        candidate: null, candidate_decision: "accepted" },
      false, false, null, false, 0,
    ];
    const Review = loadComponent("app/(claimant)/missing/reports/[reportId]/_components/MissingReportReview.tsx", {
      react: { ...React, useState: () => [state.shift(), () => {}], useEffect: () => {} },
      "next/image": () => React.createElement("span"),
      "next/navigation": { useRouter: () => ({ push() {} }) },
      "@/app/components/BackButton": link,
      "@/app/components/Button": button,
      "@/app/components/ItemImagePlaceholder": () => React.createElement("span"),
      "@/libs/api/sauli": { getMissingReport: async () => {} },
      "@/libs/claimant/format": { formatDateTime: () => "Oct 12, 2026" },
      "@/hooks/useClaimant": { useClaimant: () => ({ confirmCandidate() {}, rejectCandidate() {} }) },
    });
    return renderToStaticMarkup(React.createElement(Review, { reportId: "report-one" }));
  }
  const resolved = renderReview("resolved");
  assert.match(resolved, /Item retrieved\. Your missing-item report is closed\./);
  assert.match(resolved, /Your item was retrieved successfully/);
  assert.doesNotMatch(resolved, /Open your retrieval pass/);

  assert.match(renderReview("matched"), /Open your retrieval pass/);
});
