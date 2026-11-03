import "server-only";

export const kioskCookieName = "sauli_kiosk_session";

export function kioskBackendUrl(path: string): string {
  const origin = process.env.SAULI_API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  return `${origin.replace(/\/$/, "")}${path}`;
}

export async function kioskSession(token: string): Promise<boolean> {
  try {
    const response = await fetch(kioskBackendUrl("/api/kiosk-devices/session"), {
      headers: { "X-Kiosk-Session": token }, cache: "no-store", signal: AbortSignal.timeout(5000),
    });
    return response.ok;
  } catch {
    return false;
  }
}
