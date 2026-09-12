import { NextResponse } from "next/server";

type RouteContext = { params: { path: string[] } };

async function forward(request: Request, { params }: RouteContext) {
  const backendUrl = process.env.NEXT_PUBLIC_ASTERIA_API_URL || "http://localhost:8000";
  const incoming = new URL(request.url);
  const path = params.path.map((part) => encodeURIComponent(part)).join("/");
  const headers: Record<string, string> = {};
  const authorization = request.headers.get("authorization");
  const contentType = request.headers.get("content-type");
  if (authorization) headers.Authorization = authorization;
  if (contentType) headers["Content-Type"] = contentType;

  const response = await fetch(`${backendUrl}/api/workspace/${path}${incoming.search}`, {
    method: request.method,
    cache: "no-store",
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.text(),
  });

  const content = await response.text();
  if (response.status === 204) return new NextResponse(null, { status: 204 });
  return new NextResponse(content, {
    status: response.status,
    headers: { "Content-Type": response.headers.get("content-type") || "application/json", "Cache-Control": "no-store" },
  });
}

export async function GET(request: Request, context: RouteContext) {
  try {
    return await forward(request, context);
  } catch (error) {
    console.error("GET /api/workspace - Error proxying to backend:", error);
    return NextResponse.json({ error: "Failed to connect to backend service" }, { status: 502 });
  }
}

export async function POST(request: Request, context: RouteContext) {
  try {
    return await forward(request, context);
  } catch (error) {
    console.error("POST /api/workspace - Error proxying to backend:", error);
    return NextResponse.json({ error: "Failed to connect to backend service" }, { status: 502 });
  }
}

export async function PATCH(request: Request, context: RouteContext) {
  try {
    return await forward(request, context);
  } catch (error) {
    console.error("PATCH /api/workspace - Error proxying to backend:", error);
    return NextResponse.json({ error: "Failed to connect to backend service" }, { status: 502 });
  }
}

export async function DELETE(request: Request, context: RouteContext) {
  try {
    return await forward(request, context);
  } catch (error) {
    console.error("DELETE /api/workspace - Error proxying to backend:", error);
    return NextResponse.json({ error: "Failed to connect to backend service" }, { status: 502 });
  }
}
