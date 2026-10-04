import type { RetrievalRecord, SearchResult } from "./types";

// Prototype-only fixtures. These percentages and records are not AI output.
export const claimantMockResults: SearchResult[] = [
  {
    id: "match-014",
    itemId: "SL-2026-0819-014",
    name: "Black leather wallet",
    matchPercent: 92,
    storageStatus: "stored",
    foundLocation: "LSPU Library, 2nd Floor",
    foundAt: "2026-08-19T12:45:00+08:00",
    compartmentId: "P-05",
  },
  {
    id: "match-015",
    itemId: "SL-2026-0819-015",
    name: "Black leather wallet",
    matchPercent: 89,
    storageStatus: "stored",
    foundLocation: "LSPU Library, Ground Floor",
    foundAt: "2026-08-19T13:10:00+08:00",
    compartmentId: "P-05",
  },
  {
    id: "match-016",
    itemId: "SL-2026-0819-016",
    name: "Black leather wallet",
    matchPercent: 84,
    storageStatus: "stored",
    foundLocation: "LSPU Canteen",
    foundAt: "2026-08-19T14:20:00+08:00",
    compartmentId: "P-05",
  },
];

export const claimantMockHistory: RetrievalRecord[] = [
  {
    id: "retrieved-demo-1",
    itemName: "Black leather wallet",
    compartmentId: "P-05",
    retriever: "Rainier Reyes",
    recordedAt: "2026-08-20T15:42:00+08:00",
  },
];
