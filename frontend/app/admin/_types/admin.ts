export type CompartmentId = `P-${string}` | `M-${string}`;
export type HardwareStatus = "online" | "locked" | "unlocked" | "needs_attention" | "offline";

export interface RetrievalRecord {
  id: string;
  timestamp: string;
  retriever: string;
  item: string;
  compartment: CompartmentId;
  status: "Retrieved";
  verification: "QR code verified";
  completionSource: string;
}
