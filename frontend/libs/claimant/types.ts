export type CompartmentId = `P-${string}` | `M-${string}`;

export interface SearchDraft {
  description: string;
  photoName: string | null;
}

export interface SearchFilters {
  lastSeenLocation: string;
  lastSeenAt: string;
}

export interface SearchResult {
  id: string;
  itemId: string;
  matchCandidateId?: string;
  name: string;
  matchPercent: number;
  storageStatus: "stored";
  foundLocation: string;
  foundAt: string;
  compartmentId?: CompartmentId;
  rank?: number;
  summary?: string;
  explanation?: string;
  matchedAttributes?: string[];
  differences?: string[];
  imageUrl?: string | null;
}

export interface MissingReport {
  id: string;
  summary: string;
  notificationEmail: string;
  emailEnabled: boolean;
  status: "active" | "matched" | "resolved" | "cancelled";
}

export interface RetrievalRecord {
  id: string;
  itemName: string;
  compartmentId: CompartmentId;
  retriever: string;
  recordedAt: string;
}

export interface ClaimantRetrievalSession {
  id: string;
  qrPayload: string | null;
  issuedAt: string;
  expiresAt: string;
  status: "issued" | "validated" | "completed" | "expired" | "cancelled";
  itemSummary: string;
  validatedAt: string | null;
  completedAt: string | null;
  slotCode: string | null;
  section: "pocket" | "medium" | null;
  wrongItemOut: boolean;
  retriever: string | null;
}

export type SearchStatus = "idle" | "searching" | "results" | "empty" | "error";
export interface ClaimantState {
  searchDraft: SearchDraft;
  filters: SearchFilters;
  searchRequestId: string | null;
  searchSummary: string | null;
  searchStatus: SearchStatus;
  searchError: string | null;
  searchResults: SearchResult[];
  rejectedCandidateIds: string[];
  missingReport: MissingReport | null;
  selectedItem: SearchResult | null;
  retrievalSession: ClaimantRetrievalSession | null;
  retrievalHistory: RetrievalRecord[];
}
