import type { NextRequest } from "next/server";

export async function GET(req: NextRequest) {
  const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
  const qs = req.nextUrl.search;
  try {
    const res = await fetch(`${backendUrl}/api/forms/detail${qs}`, {
      cache: "no-store",
    });
    if (!res.ok || !res.body) {
      return new Response("Backend unavailable", { status: 502 });
    }
    return new Response(res.body, {
      status: res.status,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return new Response("Backend unavailable", { status: 502 });
  }
}
