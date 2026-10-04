import { createClient } from "@/libs/supabase/browser";
import type { ApiUser, OllamaStatus } from "@/libs/types/api";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function authenticatedGet<T>(path: string): Promise<T> {
  const { data, error } = await createClient().auth.getSession();
  if (error || !data.session?.access_token) {
    throw new Error("Please sign in before contacting the API.");
  }

  const response = await fetch(new URL(path, apiBaseUrl), {
    headers: { Authorization: `Bearer ${data.session.access_token}` },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`API request failed (${response.status}).`);
  }
  return (await response.json()) as T;
}

export const getMe = () => authenticatedGet<ApiUser>("/api/v1/me");
export const getOllamaStatus = () =>
  authenticatedGet<OllamaStatus>("/api/v1/ollama/status");
