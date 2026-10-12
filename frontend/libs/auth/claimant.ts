export function isFacebookClaimant(user: { app_metadata?: { provider?: unknown; sauli_role?: unknown } | null } | null | undefined): boolean {
  return user?.app_metadata?.provider === "facebook" && user.app_metadata.sauli_role !== "admin";
}
