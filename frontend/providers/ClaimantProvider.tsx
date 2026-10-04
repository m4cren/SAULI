"use client";

import { createContext, useEffect, useReducer, useSyncExternalStore, type ReactNode } from "react";
import { claimantReducer, initialClaimantState } from "@/libs/claimant/claimantReducer";
import { claimantService } from "@/libs/claimant/claimantService";
import { claimantMockHistory } from "@/libs/claimant/claimantMockData";
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
  rejectCandidate: (itemId: string) => void;
  selectItem: (item: SearchResult) => void;
  postMissingReport: (input: { phone: string; smsEnabled: boolean; inAppEnabled: boolean }) => Promise<MissingReport>;
  requestRetrievalPass: (item: SearchResult) => Promise<void>;
  markPassExpired: () => void;
  simulateStationQrScan: () => boolean;
  simulateWrongItemLifted: () => void;
  simulateWrongItemReturned: () => void;
  simulateCorrectItemLifted: (retriever: string) => void;
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
    const raw = sessionStorage.getItem(`sauli-claimant-prototype-v1:${userId}`);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    if (isStoredState(parsed)) return parsed;
  } catch {
    // Prototype state is disposable; a corrupt value starts a fresh session.
  }
  return { ...initialClaimantState, retrievalHistory: claimantMockHistory };
}

export default function ClaimantProvider({ children, userId }: { children: ReactNode; userId: string }) {
  const [state, dispatch] = useReducer(claimantReducer, userId, loadInitialState);
  const ready = useSyncExternalStore(subscribeToBrowser, clientSnapshot, serverSnapshot);
  const storageKey = `sauli-claimant-prototype-v1:${userId}`;

  useEffect(() => {
    if (ready) sessionStorage.setItem(storageKey, JSON.stringify(state));
  }, [ready, state, storageKey]);

  async function runSearch(filters: SearchFilters) {
    dispatch({ type: "FILTERS_UPDATED", filters });
    dispatch({ type: "SEARCH_STARTED" });
    try {
      const results = await claimantService.searchItems({ ...state.searchDraft, filters });
      dispatch({ type: "SEARCH_SUCCEEDED", results });
    } catch {
      dispatch({ type: "SEARCH_FAILED", message: "Search is unavailable. Please try again." });
    }
  }

  async function postMissingReport(input: { phone: string; smsEnabled: boolean; inAppEnabled: boolean }) {
    const report = await claimantService.createMissingReport({
      search: { ...state.searchDraft, filters: state.filters },
      ...input,
    });
    dispatch({ type: "MISSING_REPORT_CREATED", report });
    return report;
  }

  async function requestRetrievalPass(item: SearchResult) {
    const pass = await claimantService.createRetrievalRequest(item);
    dispatch({ type: "RETRIEVAL_PASS_CREATED", item, pass });
  }

  function simulateStationQrScan(): boolean {
    const valid = state.retrievalStatus === "waitingForQrScan" &&
      Boolean(state.retrievalPass && Date.now() < Date.parse(state.retrievalPass.expiresAt));
    dispatch({ type: "STATION_SCAN_SIMULATED", at: Date.now() });
    return valid;
  }

  const value: ClaimantContextValue = {
    state,
    setDraft: (draft) => dispatch({ type: "DRAFT_UPDATED", draft }),
    setFilters: (filters) => dispatch({ type: "FILTERS_UPDATED", filters }),
    runSearch,
    rejectCandidate: (itemId) => dispatch({ type: "CANDIDATE_REJECTED", itemId }),
    selectItem: (item) => dispatch({ type: "ITEM_SELECTED", item }),
    postMissingReport,
    requestRetrievalPass,
    markPassExpired: () => dispatch({ type: "PASS_EXPIRED" }),
    simulateStationQrScan,
    simulateWrongItemLifted: () => dispatch({ type: "WRONG_ITEM_LIFTED" }),
    simulateWrongItemReturned: () => dispatch({ type: "WRONG_ITEM_RETURNED", at: new Date().toISOString() }),
    simulateCorrectItemLifted: (retriever) => dispatch({ type: "CORRECT_ITEM_LIFTED", retriever, at: new Date().toISOString() }),
  };

  if (!ready) {
    return <div role="status" className="flex min-h-dvh items-center justify-center bg-[#eaeaea] text-[#0B474F]">Loading SAULI…</div>;
  }
  return <ClaimantContext.Provider value={value}>{children}</ClaimantContext.Provider>;
}
