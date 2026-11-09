import { NextResponse } from "next/server";

function buildHeaders(req: Request): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const authHeader = req.headers.get("authorization");
  const employeeId = req.headers.get("x-employee-id");
  if (authHeader) headers.Authorization = authHeader;
  if (employeeId) headers["X-Employee-Id"] = employeeId;
  return headers;
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const sessionId = url.searchParams.get("session_id");
  const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
  const target = sessionId
    ? `${backendUrl}/api/agent/history/${encodeURIComponent(sessionId)}`
    : `${backendUrl}/api/agent/history?${url.searchParams.toString()}`;

  try {
    const res = await fetch(target, { headers: buildHeaders(req) });
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

export async function DELETE(req: Request) {
  const url = new URL(req.url);
  const sessionId = url.searchParams.get("session_id");
  if (!sessionId) {
    return NextResponse.json({ error: "session_id is required" }, { status: 400 });
  }

  const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
  try {
    const res = await fetch(
      `${backendUrl}/api/agent/history/${encodeURIComponent(sessionId)}`,
      { method: "DELETE", headers: buildHeaders(req) },
    );
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
