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
  confidence: string;
  needs_review: boolean;
  uncertainty_notes: string[];
  extraction_summary: string;
  received_view_count: number;
  view_observations: { image_index: 1 | 2; visible_region: string; image_quality: string; damage_observations: string[]; notes: string[] }[];
}

export interface AnalysisResponse { analysis: FoundItemAnalysis; found_location: string; notes: string | null; summary: string; model: string }
export interface ConfirmedItem { item_id: string; status: "available"; summary: string; found_location: string; found_at: string }
export interface MatchResult { item_id: string; rank: number; rank_score: number; name: string; summary: string; found_location: string; found_at: string; front_image_url: string | null; matched_attributes: string[]; differences: string[]; explanation: string; score_breakdown: Record<string, number> }
export interface SearchResponse { search_request_id: string; query: { summary: string | null; last_seen_location: string | null }; results: MatchResult[] }
export interface FoundItemDetails { item_id: string; status: "available" | "claimed" | "retrieved" | "archived"; name: string; summary: string; category: string; colors: string[]; visible_markings: string[]; condition: string; found_location: string; found_at: string; front_image_url: string | null; back_image_url: string | null }

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try { response = await fetch(`${baseUrl}${path}`, { ...init, cache: "no-store" }); }
  catch { throw new Error("SAULI is unavailable. Check the backend connection and try again."); }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: { message?: string } } | null;
    throw new Error(body?.error?.message || `Request failed (${response.status}). Please try again.`);
  }
  return response.json() as Promise<T>;
}

function imageForm(front: File, back: File, location: string, notes: string): FormData {
  const form = new FormData();
  form.append("front_image", front);
  form.append("back_image", back);
  form.append("found_location", location);
  form.append("notes", notes);
  return form;
}

export function getBackendHealth() { return api<Record<string, string>>("/health"); }
export function analyzeFoundItem(front: File, back: File, location: string, notes: string) {
  return api<AnalysisResponse>("/api/found-items/analyze", { method: "POST", body: imageForm(front, back, location, notes) });
}
export function reconcileFoundItemReview(analysis: FoundItemAnalysis, location: string, notes: string, correction: string) {
  return api<AnalysisResponse>("/api/found-items/reconcile-review", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ analysis, found_location: location, notes: notes || null, correction_notes: correction }) });
}
export function confirmAndStoreFoundItem(front: File, back: File, location: string, notes: string, analysis: FoundItemAnalysis, key: string) {
  const form = imageForm(front, back, location, notes);
  form.append("analysis_json", JSON.stringify(analysis));
  return api<ConfirmedItem>("/api/found-items/confirm-and-store", { method: "POST", headers: { "X-Idempotency-Key": key }, body: form });
}
export function searchFoundItems(input: Record<string, unknown>, key: string) {
  return api<SearchResponse>("/api/matches/search", { method: "POST", headers: { "Content-Type": "application/json", "X-Idempotency-Key": key }, body: JSON.stringify(input) });
}
export function getFoundItem(id: string) { return api<FoundItemDetails>(`/api/found-items/${encodeURIComponent(id)}`); }
