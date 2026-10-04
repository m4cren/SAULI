import type {
  ClaimantState,
  MissingReport,
  RetrievalPass,
  RetrievalRecord,
  SearchDraft,
  SearchFilters,
  SearchResult,
} from "./types";

export const initialClaimantState: ClaimantState = {
  searchDraft: { description: "", photoName: null },
  filters: { category: "", color: "", size: "", brand: "", lastSeenLocation: "", lastSeenAt: "" },
  searchStatus: "idle",
  searchError: null,
  searchResults: [],
  rejectedCandidateIds: [],
  missingReport: null,
  selectedItem: null,
  retrievalPass: null,
  retrievalStatus: "idle",
  wrongCompartmentId: null,
  incident: null,
  retrievalHistory: [],
};

export type ClaimantAction =
  | { type: "HYDRATE"; state: ClaimantState }
  | { type: "DRAFT_UPDATED"; draft: SearchDraft }
  | { type: "FILTERS_UPDATED"; filters: SearchFilters }
  | { type: "SEARCH_STARTED" }
  | { type: "SEARCH_SUCCEEDED"; results: SearchResult[] }
  | { type: "SEARCH_FAILED"; message: string }
  | { type: "CANDIDATE_REJECTED"; itemId: string }
  | { type: "ITEM_SELECTED"; item: SearchResult }
  | { type: "MISSING_REPORT_CREATED"; report: MissingReport }
  | { type: "RETRIEVAL_PASS_CREATED"; item: SearchResult; pass: RetrievalPass }
  | { type: "PASS_EXPIRED" }
  | { type: "STATION_SCAN_SIMULATED"; at: number }
  | { type: "WRONG_ITEM_LIFTED" }
  | { type: "WRONG_ITEM_RETURNED"; at: string }
  | { type: "CORRECT_ITEM_LIFTED"; retriever: string; at: string }
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
        rejectedCandidateIds: [],
        searchError: null,
      };
    case "FILTERS_UPDATED":
      return { ...state, filters: action.filters };
    case "SEARCH_STARTED":
      return { ...state, searchStatus: "searching", searchError: null, rejectedCandidateIds: [] };
    case "SEARCH_SUCCEEDED":
      return {
        ...state,
        searchStatus: action.results.length ? "results" : "empty",
        searchResults: action.results,
        rejectedCandidateIds: [],
        selectedItem: null,
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
    case "MISSING_REPORT_CREATED":
      return { ...state, missingReport: action.report };
    case "RETRIEVAL_PASS_CREATED":
      return {
        ...state,
        selectedItem: action.item,
        retrievalPass: action.pass,
        retrievalStatus: "waitingForQrScan",
        wrongCompartmentId: null,
        incident: null,
      };
    case "PASS_EXPIRED":
      return state.retrievalStatus === "waitingForQrScan"
        ? { ...state, retrievalStatus: "qrExpired" }
        : state;
    case "STATION_SCAN_SIMULATED":
      if (state.retrievalStatus !== "waitingForQrScan" || !state.retrievalPass) return state;
      return action.at >= Date.parse(state.retrievalPass.expiresAt)
        ? { ...state, retrievalStatus: "qrExpired" }
        : { ...state, retrievalStatus: "waitingForCorrectItem" };
    case "WRONG_ITEM_LIFTED":
      if (state.retrievalStatus !== "waitingForCorrectItem") return state;
      return {
        ...state,
        retrievalStatus: "waitingForWrongItemReturn",
        wrongCompartmentId: "P-06",
        incident: { wrongCompartmentId: "P-06", wrongItemName: "Keychain", returnedAt: null },
      };
    case "WRONG_ITEM_RETURNED":
      if (state.retrievalStatus !== "waitingForWrongItemReturn" || !state.incident) return state;
      return {
        ...state,
        retrievalStatus: "waitingForCorrectItem",
        wrongCompartmentId: null,
        incident: { ...state.incident, returnedAt: action.at },
      };
    case "CORRECT_ITEM_LIFTED": {
      if (state.retrievalStatus !== "waitingForCorrectItem" || !state.selectedItem) return state;
      const record: RetrievalRecord = {
        id: `prototype-retrieval-${action.at}`,
        itemName: state.selectedItem.name,
        compartmentId: "P-05",
        retriever: action.retriever,
        recordedAt: action.at,
      };
      return {
        ...state,
        retrievalStatus: "retrieved",
        retrievalHistory: [record, ...state.retrievalHistory],
      };
    }
    case "HISTORY_LOADED":
      return { ...state, retrievalHistory: action.records };
  }
}
