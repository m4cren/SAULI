import { NextResponse, type NextRequest } from "next/server";
import { safeLocalPath } from "@/libs/auth/redirect";
import { createClient } from "@/libs/supabase/server";

export async function GET(request: NextRequest) {
  const next = safeLocalPath(request.nextUrl.searchParams.get("next"));
  const code = request.nextUrl.searchParams.get("code");
  const oauthError = request.nextUrl.searchParams.get("error");

  if (code && !oauthError) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      const response = NextResponse.redirect(new URL(next, request.url));
      response.headers.set("Cache-Control", "private, no-store");
      return response;
    }
  }

  const reason = oauthError === "access_denied" ? "denied" : "callback";
  const response = NextResponse.redirect(new URL(`/auth/login?error=${reason}`, request.url));
  response.headers.set("Cache-Control", "private, no-store");
  return response;
}
