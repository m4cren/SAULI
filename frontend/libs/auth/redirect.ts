export const OAUTH_CALLBACK_PATH = "/auth/callback";
export const OAUTH_NEXT_COOKIE = "sauli_oauth_next";

export function oauthCallbackUrl(origin: string) {
  return new URL(OAUTH_CALLBACK_PATH, origin).toString();
}

export function safeLocalPath(value: unknown, fallback = "/") {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) {
    return fallback;
  }
  if (/[\\\u0000-\u001f\u007f]/.test(value)) {
    return fallback;
  }
  const path = value.split(/[?#]/, 1)[0];
  if (path === "/auth/login" || path === "/auth/callback" || /^\/(admin|kiosk|kiosk-test)(?:\/|$)/.test(path)) {
    return fallback;
  }
  return value;
}
