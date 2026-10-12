import { createClient } from "@/libs/supabase/browser";
import type { StorageSize, SlotStatus } from "@/libs/storage/slots";

const baseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export interface FoundItemAnalysis {
  views_consistent: boolean;
  generic_name: string;
  object_name: string;
  alternative_names: string[];
  object_count: number;
  component_counts: { component: string; count: number; count_is_estimate: boolean }[];
  count_is_estimate: boolean;
  count_confidence: string;
  counting_notes: string[];
  category: string;
  subcategory: string;
  document_kind: string;
  document_owner_name: string | null;
  colors: string[];
  material: string[];
  brand: string | null;
  model_or_variant: string | null;
  visible_markings: string[];
  functional_components: string[];
  condition: string;
  condition_visibility: string;
  condition_confidence: string;
  surface_assessments: { component: string; status: string; damage_types: string[]; location: string; severity: string | null; certainty: string; evidence: string }[];
  condition_details: string[];
  patterns: string[];
  distinctive_features: string[];
  likely_use: string;
  short_description: string;
  storage_size: StorageSize;
  confidence: string;
  needs_review: boolean;
  uncertainty_notes: string[];
  extraction_summary: string;
  received_view_count: number;
  view_observations: { image_index: 1 | 2; visible_region: string; image_quality: string; damage_observations: string[]; notes: string[] }[];
}

export interface AnalysisResponse { analysis: FoundItemAnalysis; found_location: string; notes: string | null; summary: string; model: string }
export interface ConfirmedItem { item_id: string; status: "available"; summary: string; found_location: string; found_at: string; storage_size: StorageSize; slot_code: string; section: string; slot_status: "reserved" | "occupied"; placement_status: "reserved" | "placed" }
export interface StorageSlot { id: string; code: string; size_class: StorageSize; ordinal: number; status: SlotStatus; current_found_item_id: string | null; item_summary: string | null; reserved_at: string | null; occupied_at: string | null; updated_at: string }
export interface StorageSlotImages { item_id: string; front_image_url: string | null; back_image_url: string | null }
export interface SlotAvailability { size_class: StorageSize; available: number; reserved: number; occupied: number; can_assign: boolean }
export interface ClaimDecision { match_candidate_id: string; decision: "accepted" | "rejected"; item_id: string | null; slot_code: string | null; section: string | null }
export interface MatchResult { item_id: string; match_candidate_id: string; rank: number; rank_score: number; name: string; summary: string; found_location: string; found_at: string; front_image_url: string | null; matched_attributes: string[]; differences: string[]; explanation: string; score_breakdown: Record<string, number> }
export interface SearchResponse { search_request_id: string; query: { summary: string | null; last_seen_location: string | null }; results: MatchResult[] }
export interface MissingReportApi { id: string; search_request_id: string; summary: string; notification_email: string; email_notifications_enabled: boolean; status: "active" | "matched" | "resolved" | "cancelled"; created_at: string }
export interface MissingReportDetail extends MissingReportApi { candidate: MatchResult | null; candidate_decision: "pending" | "accepted" | "rejected" | null }
export interface FoundItemDetails { item_id: string; status: "available" | "claimed" | "retrieved" | "archived"; name: string; summary: string; category: string; colors: string[]; visible_markings: string[]; condition: string; found_location: string; found_at: string; front_image_url: string | null; back_image_url: string | null }
export type RetrievalStatus = "issued" | "validated" | "completed" | "expired" | "cancelled";
export interface IssuedRetrieval { id: string; raw_token: string; qr_payload: string; issued_at: string; expires_at: string; status: RetrievalStatus; item_summary: string }
export interface RetrievalSessionStatus { id: string; status: RetrievalStatus; issued_at: string; expires_at: string; item_summary: string; validated_at: string | null; completed_at: string | null; slot_code: string | null; section: StorageSize | null; wrong_item_out: boolean; retriever: string | null; can_replace: boolean; completed: boolean }
export interface ValidatedRetrieval { id: string; status: "validated"; item_summary: string; slot_code: string; section: StorageSize; slot_status: "occupied"; action_token: string }
export interface SimulatedRetrieval { id: string; status: "validated" | "completed"; wrong_item_out: boolean; completed_at: string | null }
export interface RetrievalLog { id: string; retrieval_session_id: string; retriever: string; item_summary: string; slot_code: string; retrieved_at: string; completion_source: string }

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try { response = await fetch(`${baseUrl}${path}`, { ...init, cache: "no-store" }); }
  catch { throw new Error("SAULI is unavailable. Check the backend connection and try again."); }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string; error?: { code?: string; message?: string; requested_size?: StorageSize } } | null;
    throw new SauliApiError(body?.error?.message || body?.detail || `Request failed (${response.status}). Please try again.`, body?.error?.code, body?.error?.requested_size, response.status);
  }
  return response.json() as Promise<T>;
}

export class SauliApiError extends Error {
  constructor(message: string, public readonly code?: string, public readonly requestedSize?: StorageSize, public readonly status?: number) { super(message); }
}

async function authHeaders(): Promise<HeadersInit> {
  const { data, error } = await createClient().auth.getSession();
  if (error || !data.session?.access_token) throw new Error("Please sign in before continuing.");
  return { Authorization: `Bearer ${data.session.access_token}` };
}

function imageForm(front: File, back: File, location: string): FormData {
  const form = new FormData();
  form.append("front_image", front);
  form.append("back_image", back);
  form.append("found_location", location);
  return form;
}

export function getBackendHealth() { return api<Record<string, string>>("/health"); }
export function analyzeFoundItem(front: File, back: File, location: string) {
  return api<AnalysisResponse>("/api/found-items/analyze", { method: "POST", body: imageForm(front, back, location) });
}
export function reconcileFoundItemReview(analysis: FoundItemAnalysis, location: string, correction: string) {
  return api<AnalysisResponse>("/api/found-items/reconcile-review", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ analysis, found_location: location, correction_notes: correction }) });
}
export function confirmAndStoreFoundItem(front: File, back: File, location: string, analysis: FoundItemAnalysis, size: StorageSize, key: string) {
  const form = imageForm(front, back, location);
  form.append("analysis_json", JSON.stringify(analysis));
  form.append("storage_size", size);
  return api<ConfirmedItem>("/api/found-items/confirm-and-store", { method: "POST", headers: { "X-Idempotency-Key": key }, body: form });
}
export function simulateItemPlacement(itemId: string, slotCode: string) {
  return api<ConfirmedItem>(`/api/found-items/${encodeURIComponent(itemId)}/simulate-placement`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ slot_code: slotCode }),
  });
}
export function getSlotAvailability(size: StorageSize) {
  return api<SlotAvailability>(`/api/storage-slots/availability?size_class=${size}`);
}
export async function getStorageSlots() {
  return api<StorageSlot[]>("/api/storage-slots", { headers: await authHeaders() });
}
export async function getStorageSlotImages(itemId: string) {
  return api<StorageSlotImages>(`/api/storage-slots/items/${encodeURIComponent(itemId)}/images`, { headers: await authHeaders() });
}
export async function searchFoundItems(input: Record<string, unknown>, key: string) {
  return api<SearchResponse>("/api/matches/search", { method: "POST",
    headers: { "Content-Type": "application/json", "X-Idempotency-Key": key, ...await authHeaders() }, body: JSON.stringify(input) });
}
export async function createMissingReport(searchRequestId: string, email: string, enabled: boolean, key: string) {
  return api<MissingReportApi>("/api/missing-reports", { method: "POST",
    headers: { "Content-Type": "application/json", "X-Idempotency-Key": key, ...await authHeaders() },
    body: JSON.stringify({ search_request_id: searchRequestId, notification_email: email, email_notifications_enabled: enabled }) });
}
export async function getMissingReport(id: string) {
  return api<MissingReportDetail>(`/api/missing-reports/${encodeURIComponent(id)}`, { headers: await authHeaders() });
}
export async function listMissingReports() {
  return api<MissingReportApi[]>("/api/missing-reports", { headers: await authHeaders() });
}
export async function decideMatch(candidateId: string, decision: "confirm" | "reject") {
  return api<ClaimDecision>(`/api/matches/${encodeURIComponent(candidateId)}/${decision}`, {
    method: "POST", headers: await authHeaders(),
  });
}
export function getFoundItem(id: string) { return api<FoundItemDetails>(`/api/found-items/${encodeURIComponent(id)}`); }
export async function createRetrievalSession(candidateId: string) {
  return api<IssuedRetrieval>("/api/retrieval-sessions", { method: "POST", headers: { "Content-Type": "application/json", ...await authHeaders() },
    body: JSON.stringify({ match_candidate_id: candidateId }) });
}
export async function getRetrievalSession(id: string) {
  return api<RetrievalSessionStatus>(`/api/retrieval-sessions/${encodeURIComponent(id)}`, { headers: await authHeaders() });
}
export async function getClaimantRetrievalHistory() {
  return api<RetrievalLog[]>("/api/retrieval-sessions/history", { headers: await authHeaders() });
}
export async function replaceRetrievalSession(id: string) {
  return api<IssuedRetrieval>(`/api/retrieval-sessions/${encodeURIComponent(id)}/replace`, { method: "POST", headers: await authHeaders() });
}
export function validateRetrievalQr(qrPayload: string) {
  return api<ValidatedRetrieval>("/api/retrieval-sessions/validate", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ qr_payload: qrPayload }) });
}
export function simulateRetrievalEvent(id: string, actionToken: string, event: "completion" | "wrong-item" | "item-returned") {
  return api<SimulatedRetrieval>(`/api/retrieval-sessions/${encodeURIComponent(id)}/simulate-${event}`, {
    method: "POST", headers: { "X-Retrieval-Action": actionToken },
  });
}
export async function getRetrievalLogs() {
  return api<RetrievalLog[]>("/api/retrieval-sessions/admin/logs", { headers: await authHeaders() });
}
