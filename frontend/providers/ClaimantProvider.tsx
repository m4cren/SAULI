"use client";

import { createContext, useEffect, useReducer, useRef, useSyncExternalStore, type ReactNode } from "react";
import { claimantReducer, initialClaimantState } from "@/libs/claimant/claimantReducer";
import { createMissingReport, createRetrievalSession, decideMatch, getRetrievalSession, replaceRetrievalSession, searchFoundItems, type IssuedRetrieval } from "@/libs/api/sauli";
import type {
  ClaimantState,
  MissingReport,
  SearchDraft,
  SearchFilters,
  SearchResult,
} from "@/libs/claimant/types";

interface ClaimantContextValue {
  state: ClaimantState;
  setDraft: (draft: SearchDraft) => void;
  setFilters: (filters: SearchFilters) => void;
  runSearch: (filters: SearchFilters) => Promise<void>;
  rejectCandidate: (item: SearchResult) => Promise<void>;
  confirmCandidate: (item: SearchResult) => Promise<void>;
  refreshRetrieval: () => Promise<void>;
  replaceRetrieval: () => Promise<void>;
  selectItem: (item: SearchResult) => void;
  postMissingReport: (input: { email: string; emailEnabled: boolean }) => Promise<MissingReport>;
}

export const ClaimantContext = createContext<ClaimantContextValue | null>(null);

const subscribeToBrowser = () => () => {};
const clientSnapshot = () => true;
const serverSnapshot = () => false;

function isStoredState(value: unknown): value is ClaimantState {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<ClaimantState>;
  return Boolean(
    candidate.searchDraft && typeof candidate.searchDraft.description === "string" &&
    candidate.filters && Array.isArray(candidate.searchResults) &&
    Array.isArray(candidate.rejectedCandidateIds) && Array.isArray(candidate.retrievalHistory),
  );
}

function loadInitialState(userId: string): ClaimantState {
  if (typeof window === "undefined") return initialClaimantState;
  try {
    const raw = sessionStorage.getItem(`sauli-claimant-integration-v4:${userId}`);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    if (isStoredState(parsed)) {
      const { lastSeenLocation, lastSeenAt } = parsed.filters;
      return { ...parsed, filters: {
        lastSeenLocation: typeof lastSeenLocation === "string" ? lastSeenLocation : "",
        lastSeenAt: typeof lastSeenAt === "string" ? lastSeenAt : "",
      }, searchRequestId: parsed.searchRequestId ?? null,
      searchSummary: parsed.searchSummary ?? null,
      retrievalSession: parsed.retrievalSession ? {
        ...parsed.retrievalSession,
        validatedAt: parsed.retrievalSession.validatedAt ?? null,
        completedAt: parsed.retrievalSession.completedAt ?? null,
        slotCode: parsed.retrievalSession.slotCode ?? null,
        section: parsed.retrievalSession.section ?? null,
        wrongItemOut: parsed.retrievalSession.wrongItemOut ?? false,
        retriever: parsed.retrievalSession.retriever ?? null,
      } : null };
    }
  } catch {
    // Prototype state is disposable; a corrupt value starts a fresh session.
  }
  return initialClaimantState;
}

export default function ClaimantProvider({ children, userId }: { children: ReactNode; userId: string }) {
  const [state, dispatch] = useReducer(claimantReducer, userId, loadInitialState);
  const ready = useSyncExternalStore(subscribeToBrowser, clientSnapshot, serverSnapshot);
  const storageKey = `sauli-claimant-integration-v4:${userId}`;
  const retrievalRefreshInFlight = useRef(false);
  const missingReportKey = useRef<{ searchId: string; key: string } | null>(null);
  const reportInFlight = useRef(false);

  function savedSession(issued: IssuedRetrieval): NonNullable<ClaimantState["retrievalSession"]> {
    return { id: issued.id, qrPayload: issued.qr_payload, issuedAt: issued.issued_at,
      expiresAt: issued.expires_at, status: issued.status, itemSummary: issued.item_summary,
      validatedAt: null, completedAt: null, slotCode: null, section: null, wrongItemOut: false, retriever: null };
  }

  useEffect(() => {
    if (ready) sessionStorage.setItem(storageKey, JSON.stringify(state));
  }, [ready, state, storageKey]);

  async function runSearch(filters: SearchFilters) {
    dispatch({ type: "FILTERS_UPDATED", filters });
    dispatch({ type: "SEARCH_STARTED" });
    try {
      const input = { description: state.searchDraft.description,
        last_seen_location: filters.lastSeenLocation || null,
        last_seen_at: filters.lastSeenAt ? new Date(filters.lastSeenAt).toISOString() : null };
      const response = await searchFoundItems(input, crypto.randomUUID());
      const results: SearchResult[] = response.results.map((item) => ({
        id: item.item_id, itemId: item.item_id, matchCandidateId: item.match_candidate_id, name: item.name, matchPercent: item.rank_score,
        storageStatus: "stored", foundLocation: item.found_location, foundAt: item.found_at,
        rank: item.rank, summary: item.summary, explanation: item.explanation,
        matchedAttributes: item.matched_attributes, differences: item.differences, imageUrl: item.front_image_url,
      }));
      dispatch({ type: "SEARCH_SUCCEEDED", results, searchRequestId: response.search_request_id,
        searchSummary: response.query.summary });
    } catch (error) {
      dispatch({ type: "SEARCH_FAILED", message: error instanceof Error ? error.message : "Search is unavailable. Please try again." });
    }
  }

  async function postMissingReport(input: { email: string; emailEnabled: boolean }) {
    if (!state.searchRequestId) throw new Error("Search for your item before posting a report.");
    if (reportInFlight.current) throw new Error("Your report is already being posted.");
    reportInFlight.current = true;
    if (missingReportKey.current?.searchId !== state.searchRequestId) {
      missingReportKey.current = { searchId: state.searchRequestId, key: crypto.randomUUID() };
    }
    let saved;
    try {
      saved = await createMissingReport(state.searchRequestId, input.email, input.emailEnabled, missingReportKey.current.key);
    } finally { reportInFlight.current = false; }
    missingReportKey.current = null;
    const report: MissingReport = { id: saved.id, summary: saved.summary,
      notificationEmail: saved.notification_email, emailEnabled: saved.email_notifications_enabled,
      status: saved.status };
    dispatch({ type: "MISSING_REPORT_CREATED", report });
    return report;
  }

  async function rejectCandidate(item: SearchResult) {
    if (!item.matchCandidateId) throw new Error("This result cannot be rejected. Run the search again.");
    await decideMatch(item.matchCandidateId, "reject");
    dispatch({ type: "CANDIDATE_REJECTED", itemId: item.id });
  }

  async function confirmCandidate(item: SearchResult) {
    if (!item.matchCandidateId) throw new Error("This result cannot be confirmed. Run the search again.");
    const decision = await decideMatch(item.matchCandidateId, "confirm");
    if (decision.item_id !== item.itemId) throw new Error("The confirmed item could not be verified.");
    const issued = await createRetrievalSession(item.matchCandidateId);
    dispatch({ type: "CLAIM_CONFIRMED", item, session: savedSession(issued) });
  }

  async function refreshRetrieval() {
    if (!state.retrievalSession || retrievalRefreshInFlight.current) return;
    retrievalRefreshInFlight.current = true;
    try {
      const result = await getRetrievalSession(state.retrievalSession.id);
      dispatch({ type: "RETRIEVAL_STATUS", result });
    } finally { retrievalRefreshInFlight.current = false; }
  }

  async function replaceRetrieval() {
    if (!state.retrievalSession) throw new Error("No retrieval session is available.");
    const issued = await replaceRetrievalSession(state.retrievalSession.id);
    dispatch({ type: "RETRIEVAL_REPLACED", session: savedSession(issued) });
  }

  const value: ClaimantContextValue = {
    state,
    setDraft: (draft) => dispatch({ type: "DRAFT_UPDATED", draft }),
    setFilters: (filters) => dispatch({ type: "FILTERS_UPDATED", filters }),
    runSearch,
    rejectCandidate,
    confirmCandidate,
    refreshRetrieval,
    replaceRetrieval,
    selectItem: (item) => dispatch({ type: "ITEM_SELECTED", item }),
    postMissingReport,
  };

  if (!ready) {
    return <div role="status" className="flex min-h-dvh items-center justify-center bg-[#eaeaea] text-[#0B474F]">Loading SAULI…</div>;
  }
  return <ClaimantContext.Provider value={value}>{children}</ClaimantContext.Provider>;
}
