export function maskEmail(address: string): string {
  const [local, domain] = address.trim().split("@");
  if (!local || !domain) return "Email unavailable";
  return `${local.slice(0, 3)}••••••@${domain}`;
}
