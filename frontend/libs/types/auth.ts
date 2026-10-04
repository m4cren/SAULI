import type { User } from "@supabase/supabase-js";

export type AuthUser = User;

export function displayName(user: AuthUser): string {
  const metadata = user.user_metadata;
  const name = metadata?.full_name ?? metadata?.name ?? metadata?.first_name;
  return typeof name === "string" && name.trim() ? name.trim() : "SAULI user";
}

export function avatarUrl(user: AuthUser): string | null {
  const metadata = user.user_metadata;
  const value = metadata?.avatar_url ?? metadata?.picture;
  if (typeof value !== "string") return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}
