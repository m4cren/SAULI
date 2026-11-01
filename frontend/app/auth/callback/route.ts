import { NextResponse, type NextRequest } from "next/server";
import { OAUTH_CALLBACK_PATH, OAUTH_NEXT_COOKIE, safeLocalPath } from "@/libs/auth/redirect";
import { createClient } from "@/libs/supabase/server";

export async function GET(request: NextRequest) {
  const next = safeLocalPath(request.cookies.get(OAUTH_NEXT_COOKIE)?.value);
  const code = request.nextUrl.searchParams.get("code");
  const oauthError = request.nextUrl.searchParams.get("error");

  if (code && !oauthError) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      const response = NextResponse.redirect(new URL(next, request.url));
      response.cookies.set(OAUTH_NEXT_COOKIE, "", { path: OAUTH_CALLBACK_PATH, maxAge: 0 });
      response.headers.set("Cache-Control", "private, no-store");
      return response;
    }
  }

  const reason = oauthError === "access_denied" ? "denied" : "callback";
  const response = NextResponse.redirect(new URL(`/auth/login?error=${reason}`, request.url));
  response.cookies.set(OAUTH_NEXT_COOKIE, "", { path: OAUTH_CALLBACK_PATH, maxAge: 0 });
  response.headers.set("Cache-Control", "private, no-store");
  return response;
}
