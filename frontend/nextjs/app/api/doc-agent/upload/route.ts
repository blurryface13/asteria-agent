import { NextResponse } from 'next/server';

// Streams the multipart upload straight through to the backend, preserving the
// Content-Type boundary and forwarding the Authorization header.
export async function POST(request: Request) {
  const backendUrl = process.env.NEXT_PUBLIC_ASTERIA_API_URL || 'http://127.0.0.1:8000';
  try {
    const body = await request.arrayBuffer();
    const response = await fetch(`${backendUrl}/api/doc-agent/upload`, {
      method: 'POST',
      headers: {
        'Content-Type': request.headers.get('content-type') || 'application/octet-stream',
        ...(request.headers.get('authorization')
          ? { Authorization: request.headers.get('authorization')! }
          : {}),
      },
      body,
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('doc-agent/upload proxy error:', error);
    return NextResponse.json({ error: 'doc-agent backend unreachable' }, { status: 502 });
  }
}
