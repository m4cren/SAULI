import { claimantMockHistory } from "./claimantMockData";
import type {
  ClaimantService,
  MissingReport,
  MissingReportInput,
  RetrievalRecord,
} from "./types";

const delay = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

// Prototype-only adapter. Replace these methods with existing FastAPI contracts
// when those endpoints are available; do not use this for real retrieval passes.
export const claimantService: ClaimantService = {
  async createMissingReport(input: MissingReportInput): Promise<MissingReport> {
    await delay(300);
    const details = [
      input.search.description.trim(),
      input.search.filters.lastSeenLocation && `Last seen near ${input.search.filters.lastSeenLocation}.`,
      input.search.filters.brand && `Brand or label: ${input.search.filters.brand}.`,
    ].filter(Boolean);
    return {
      id: `prototype-report-${Date.now()}`,
      summary: details.join(" "),
      phone: input.phone,
      smsEnabled: input.smsEnabled,
      inAppEnabled: input.inAppEnabled,
      status: "active",
    };
  },

  async getRetrievalHistory(): Promise<RetrievalRecord[]> {
    await delay(150);
    return claimantMockHistory.map((record) => ({ ...record }));
  },
};
