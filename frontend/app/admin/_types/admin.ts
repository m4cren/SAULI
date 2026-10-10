export type CompartmentId = `P-${string}` | `M-${string}`;
export type CompartmentStatus = "available" | "occupied";
export type SensorHealth = "active" | "needs_attention" | "disconnected";
export type HardwareStatus = "online" | "locked" | "unlocked" | "needs_attention" | "offline";

export interface Compartment {
  id: CompartmentId;
  size: "Pocket-size" | "Medium-size";
  status: CompartmentStatus;
  sensor: SensorHealth;
  weightGrams: number;
  storedItem: string | null;
  lastActivity: string;
}

export interface RetrievalRecord {
  id: string;
  timestamp: string;
  retriever: string;
  item: string;
  compartment: CompartmentId;
  status: "Retrieved";
  verification: "QR code verified";
}

export interface UnrecognizedCapture {
  id: string;
  title: string;
  timestamp: string;
  source: string;
  reason: string;
  confidence?: number;
}
