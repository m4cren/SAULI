import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { getSupabaseConfig } from "@/libs/supabase/config";
import { isFacebookClaimant } from "@/libs/auth/claimant";
import { safeLocalPath } from "@/libs/auth/redirect";

export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });
  const { url, key } = getSupabaseConfig();
  const supabase = createServerClient(url, key, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options),
        );
      },
    },
  });

  const { data } = await supabase.auth.getUser();
  const pathname = request.nextUrl.pathname;
  const claimantPage = pathname === "/" || /^(\/search|\/missing|\/retrieval|\/history)(\/|$)/.test(pathname);
  const facebookClaimant = isFacebookClaimant(data.user);

  function redirectWithAuthCookies(url: URL) {
    const redirect = NextResponse.redirect(url);
    response.cookies.getAll().forEach((cookie) => redirect.cookies.set(cookie));
    redirect.headers.set("Cache-Control", "private, no-store");
    return redirect;
  }

  if (claimantPage && !facebookClaimant) {
    const login = new URL("/auth/login", request.url);
    login.searchParams.set("next", `${request.nextUrl.pathname}${request.nextUrl.search}`);
    return redirectWithAuthCookies(login);
  }
  if (pathname === "/auth/login" && facebookClaimant) {
    const next = safeLocalPath(request.nextUrl.searchParams.get("next"));
    return redirectWithAuthCookies(new URL(next, request.url));
  }
  response.headers.set("Cache-Control", "private, no-store");
  return response;
}

export const config = {
  matcher: ["/", "/auth/:path*", "/admin/:path*", "/search/:path*", "/missing/:path*", "/retrieval/:path*", "/history/:path*"],
};
