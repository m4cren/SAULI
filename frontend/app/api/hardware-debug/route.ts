export const dynamic = "force-dynamic";

export async function GET() {
  const origin = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
  try {
    const response = await fetch(`${origin}/api/hardware/public`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) throw new Error("backend_unavailable");
    return Response.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Hardware status is unavailable." }, { status: 503 });
  }
}
