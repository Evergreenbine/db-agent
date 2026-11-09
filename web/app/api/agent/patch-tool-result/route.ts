import { NextResponse } from "next/server";

export async function POST(req: Request) {
  const body = await req.text();
  const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

  const authHeader = req.headers.get("authorization") ?? "";
  const xEmployeeId = req.headers.get("x-employee-id") ?? "";

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (authHeader) headers["Authorization"] = authHeader;
  if (xEmployeeId) headers["X-Employee-Id"] = xEmployeeId;

  try {
    const res = await fetch(`${backendUrl}/api/agent/patch-tool-result`, {
      method: "POST",
      headers,
      body,
    });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (e) {
    return NextResponse.json(
      { error: "BACKEND_UNAVAILABLE", detail: String(e) },
      { status: 502 },
    );
  }
}
