import type {
  ClaimantState,
  MissingReport,
  RetrievalRecord,
  SearchDraft,
  SearchFilters,
  SearchResult,
} from "./types";
import type { RetrievalSessionStatus } from "@/libs/api/sauli";

export const initialClaimantState: ClaimantState = {
  searchDraft: { description: "", photoName: null },
  filters: { lastSeenLocation: "", lastSeenAt: "" },
  searchRequestId: null,
  searchSummary: null,
  searchStatus: "idle",
  searchError: null,
  searchResults: [],
  rejectedCandidateIds: [],
  missingReport: null,
  selectedItem: null,
  retrievalSession: null,
  retrievalHistory: [],
};

export type ClaimantAction =
  | { type: "HYDRATE"; state: ClaimantState }
  | { type: "DRAFT_UPDATED"; draft: SearchDraft }
  | { type: "FILTERS_UPDATED"; filters: SearchFilters }
  | { type: "SEARCH_STARTED" }
  | { type: "SEARCH_SUCCEEDED"; results: SearchResult[]; searchRequestId: string; searchSummary: string | null }
  | { type: "SEARCH_FAILED"; message: string }
  | { type: "CANDIDATE_REJECTED"; itemId: string }
  | { type: "ITEM_SELECTED"; item: SearchResult }
  | { type: "CLAIM_CONFIRMED"; item: SearchResult; session: NonNullable<ClaimantState["retrievalSession"]> }
  | { type: "RETRIEVAL_STATUS"; result: RetrievalSessionStatus }
  | { type: "RETRIEVAL_REPLACED"; session: NonNullable<ClaimantState["retrievalSession"]> }
  | { type: "MISSING_REPORT_CREATED"; report: MissingReport }
  | { type: "HISTORY_LOADED"; records: RetrievalRecord[] };

export function claimantReducer(state: ClaimantState, action: ClaimantAction): ClaimantState {
  switch (action.type) {
    case "HYDRATE":
      return action.state;
    case "DRAFT_UPDATED":
      return {
        ...state,
        searchDraft: action.draft,
        searchStatus: "idle",
        searchResults: [],
        searchRequestId: null,
        searchSummary: null,
        rejectedCandidateIds: [],
        searchError: null,
      };
    case "FILTERS_UPDATED":
      return { ...state, filters: action.filters, searchRequestId: null,
        searchSummary: null, searchResults: [], searchStatus: "idle" };
    case "SEARCH_STARTED":
      return { ...state, searchStatus: "searching", searchError: null,
        searchRequestId: null, searchSummary: null, searchResults: [], rejectedCandidateIds: [] };
    case "SEARCH_SUCCEEDED":
      return {
        ...state,
        searchStatus: action.results.length ? "results" : "empty",
        searchResults: action.results,
        searchRequestId: action.searchRequestId,
        searchSummary: action.searchSummary,
        rejectedCandidateIds: [],
        selectedItem: null,
        retrievalSession: null,
      };
    case "SEARCH_FAILED":
      return { ...state, searchStatus: "error", searchError: action.message, searchResults: [] };
    case "CANDIDATE_REJECTED":
      return {
        ...state,
        rejectedCandidateIds: state.rejectedCandidateIds.includes(action.itemId)
          ? state.rejectedCandidateIds
          : [...state.rejectedCandidateIds, action.itemId],
        selectedItem: state.selectedItem?.id === action.itemId ? null : state.selectedItem,
      };
    case "ITEM_SELECTED":
      return state.rejectedCandidateIds.includes(action.item.id)
        ? state
        : { ...state, selectedItem: action.item };
    case "CLAIM_CONFIRMED":
      return { ...state, selectedItem: action.item, retrievalSession: action.session };
    case "RETRIEVAL_STATUS":
      if (!state.retrievalSession || state.retrievalSession.id !== action.result.id || Date.parse(state.retrievalSession.issuedAt) !== Date.parse(action.result.issued_at)) return state;
      if (state.retrievalSession.status === "completed" && action.result.status !== "completed") return state;
      if (state.retrievalSession.status === "validated" && action.result.status === "issued") return state;
      return { ...state, retrievalSession: {
        ...state.retrievalSession,
        status: action.result.status,
        itemSummary: action.result.item_summary,
        qrPayload: action.result.status === "issued" ? state.retrievalSession.qrPayload : null,
        validatedAt: action.result.validated_at,
        completedAt: action.result.completed_at,
        slotCode: action.result.slot_code,
        section: action.result.section,
        wrongItemOut: action.result.wrong_item_out,
        retriever: action.result.retriever,
      } };
    case "RETRIEVAL_REPLACED":
      return { ...state, retrievalSession: action.session };
    case "MISSING_REPORT_CREATED":
      return { ...state, missingReport: action.report };
    case "HISTORY_LOADED":
      return { ...state, retrievalHistory: action.records };
  }
}
