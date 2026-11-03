import { NextRequest, NextResponse } from "next/server";
import { kioskBackendUrl, kioskCookieName } from "@/libs/api/kiosk-server";

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code") ?? "";
  if (!/^[A-Za-z0-9_-]{50,128}$/.test(code)) {
    return NextResponse.json({ error: "Invalid kiosk activation code." }, { status: 400 });
  }
  try {
    const backend = await fetch(kioskBackendUrl("/api/kiosk-devices/browser-redeem"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bootstrap_code: code }), cache: "no-store", signal: AbortSignal.timeout(8000),
    });
    if (!backend.ok) return NextResponse.json({ error: "Kiosk activation was denied or expired." }, { status: 403 });
    const result = await backend.json() as { session_token: string; expires_at: string };
    const response = NextResponse.redirect(new URL("/kiosk", request.url));
    response.cookies.set(kioskCookieName, result.session_token, {
      httpOnly: true, secure: request.nextUrl.protocol === "https:", sameSite: "lax", path: "/",
      expires: new Date(result.expires_at),
    });
    response.headers.set("Cache-Control", "no-store");
    response.headers.set("Referrer-Policy", "no-referrer");
    return response;
  } catch {
    return NextResponse.json({ error: "Kiosk activation is temporarily unavailable." }, { status: 503 });
  }
}
