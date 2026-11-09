import { cookies } from "next/headers";
import { kioskBackendUrl, kioskCookieName } from "@/libs/api/kiosk-server";

const allowed = [
  /^found-items\/(analyze|reconcile-review|confirm-and-store)$/,
  /^found-items\/[0-9a-f-]{36}\/simulate-placement$/,
  /^storage-slots\/availability$/,
  /^retrieval-sessions\/validate$/,
  /^retrieval-sessions\/[0-9a-f-]{36}\/simulate-(completion|wrong-item|item-returned)$/,
  /^hardware\/(workflow|capture-light)$/,
];

async function forward(request: Request, context: { params: Promise<{ path: string[] }> }) {
  if (request.method === "POST" && request.headers.get("origin") !== new URL(request.url).origin) {
    return Response.json({ error: { code: "KIOSK_ORIGIN_DENIED", message: "Kiosk request was denied." } }, { status: 403 });
  }
  const path = (await context.params).path.join("/");
  if (!allowed.some((rule) => rule.test(path))) return Response.json({ error: "Unknown kiosk action." }, { status: 404 });
  const token = (await cookies()).get(kioskCookieName)?.value;
  if (!token) return Response.json({ error: { code: "KIOSK_ACCESS_DENIED", message: "Kiosk registration required." } }, { status: 403 });
  const incoming = new URL(request.url);
  const headers = new Headers({ "X-Kiosk-Session": token });
  for (const name of ["content-type", "x-idempotency-key", "x-retrieval-action"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const backend = await fetch(kioskBackendUrl(`/api/${path}${incoming.search}`), {
      method: request.method, headers,
      body: request.method === "POST" ? await request.arrayBuffer() : undefined,
      cache: "no-store", signal: AbortSignal.timeout(120000),
    });
    return new Response(backend.body, { status: backend.status,
      headers: { "Content-Type": backend.headers.get("content-type") ?? "application/json", "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: { code: "BACKEND_UNAVAILABLE", message: "SAULI is unavailable. Please try again." } }, { status: 503 });
  }
}

export const GET = forward;
export const POST = forward;
