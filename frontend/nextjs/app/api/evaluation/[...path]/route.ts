import { NextResponse } from "next/server";

const backend = () => process.env.NEXT_PUBLIC_ASTERIA_API_URL || "http://127.0.0.1:8000";

async function forward(request: Request, context: { params: { path: string[] } }) {
  const { path } = context.params;
  const url = new URL(`${backend()}/api/evaluation/${path.join("/")}`);
  const incoming = new URL(request.url);
  incoming.searchParams.forEach((value, key) => url.searchParams.set(key, value));
  const headers: Record<string, string> = {};
  const authorization = request.headers.get("authorization");
  if (authorization) headers.Authorization = authorization;
  if (request.headers.get("content-type")) headers["Content-Type"] = request.headers.get("content-type")!;
  try {
    const response = await fetch(url, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer(),
      cache: "no-store",
    });
    const body = await response.arrayBuffer();
    return new NextResponse(body, { status: response.status, headers: { "Content-Type": response.headers.get("content-type") || "application/json" } });
  } catch {
    return NextResponse.json({ detail: "evaluation backend unreachable" }, { status: 502 });
  }
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
