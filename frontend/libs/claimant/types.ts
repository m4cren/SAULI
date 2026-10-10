export type CompartmentId = "P-05";

export interface SearchDraft {
  description: string;
  photoName: string | null;
}

export interface SearchFilters {
  category: string;
  color: string;
  size: string;
  brand: string;
  lastSeenLocation: string;
  lastSeenAt: string;
}

export interface SearchInput extends SearchDraft {
  filters: SearchFilters;
}

export interface SearchResult {
  id: string;
  itemId: string;
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

export interface MissingReportInput {
  search: SearchInput;
  phone: string;
  smsEnabled: boolean;
  inAppEnabled: boolean;
}

export interface MissingReport {
  id: string;
  summary: string;
  phone: string;
  smsEnabled: boolean;
  inAppEnabled: boolean;
  status: "active";
}

export interface RetrievalPass {
  itemId: string;
  itemName: string;
  compartmentId: CompartmentId;
  createdAt: string;
  expiresAt: string;
  prototype: true;
}

export interface RetrievalRecord {
  id: string;
  itemName: string;
  compartmentId: CompartmentId;
  retriever: string;
  recordedAt: string;
}

export interface MockIncident {
  wrongCompartmentId: "P-06";
  wrongItemName: "Keychain";
  returnedAt: string | null;
}

export interface ClaimantService {
  createMissingReport(input: MissingReportInput): Promise<MissingReport>;
  getRetrievalHistory(): Promise<RetrievalRecord[]>;
}

export type SearchStatus = "idle" | "searching" | "results" | "empty" | "error";
export type RetrievalStatus =
  | "idle"
  | "waitingForQrScan"
  | "qrExpired"
  | "waitingForCorrectItem"
  | "waitingForWrongItemReturn"
  | "retrieved";

export interface ClaimantState {
  searchDraft: SearchDraft;
  filters: SearchFilters;
  searchStatus: SearchStatus;
  searchError: string | null;
  searchResults: SearchResult[];
  rejectedCandidateIds: string[];
  missingReport: MissingReport | null;
  selectedItem: SearchResult | null;
  retrievalPass: RetrievalPass | null;
  retrievalStatus: RetrievalStatus;
  wrongCompartmentId: "P-06" | null;
  incident: MockIncident | null;
  retrievalHistory: RetrievalRecord[];
}
