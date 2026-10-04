import { claimantMockHistory, claimantMockResults } from "./claimantMockData";
import type {
  ClaimantService,
  MissingReport,
  MissingReportInput,
  RetrievalPass,
  RetrievalRecord,
  SearchInput,
  SearchResult,
} from "./types";

const delay = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

// Prototype-only adapter. Replace these methods with existing FastAPI contracts
// when those endpoints are available; do not use this for real retrieval passes.
export const claimantService: ClaimantService = {
  async searchItems(input: SearchInput): Promise<SearchResult[]> {
    await delay(450);
    if (input.description.toLowerCase().includes("[error]")) {
      throw new Error("Prototype search is unavailable.");
    }
    if (input.description.toLowerCase().includes("[empty]") || input.filters.category === "electronics") {
      return [];
    }
    return claimantMockResults.map((result) => ({ ...result }));
  },

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

  async createRetrievalRequest(item: SearchResult): Promise<RetrievalPass> {
    await delay(300);
    const createdAt = new Date();
    return {
      itemId: item.itemId,
      itemName: item.name,
      compartmentId: item.compartmentId,
      createdAt: createdAt.toISOString(),
      expiresAt: new Date(createdAt.getTime() + 10 * 60 * 1000).toISOString(),
      prototype: true,
    };
  },

  async getRetrievalHistory(): Promise<RetrievalRecord[]> {
    await delay(150);
    return claimantMockHistory.map((record) => ({ ...record }));
  },
};
