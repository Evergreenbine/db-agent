import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
  const url = new URL(req.url);
  const table = url.searchParams.get("table") ?? "";
  try {
    const res = await fetch(`${backendUrl}/api/forms/track?table=${encodeURIComponent(table)}`, {
      method: "POST",
    });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (e) {
    return NextResponse.json({ error: "BACKEND_UNAVAILABLE" }, { status: 502 });
  }
}
