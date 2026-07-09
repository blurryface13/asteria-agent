import { NextResponse } from 'next/server';

export async function GET(request: Request) {
  const backendUrl = process.env.NEXT_PUBLIC_ASTERIA_API_URL || 'http://127.0.0.1:8000';
  try {
    const response = await fetch(`${backendUrl}/api/knowledge/mcp/presets`, {
      headers: {
        ...(request.headers.get('authorization')
          ? { Authorization: request.headers.get('authorization')! }
          : {}),
      },
      cache: 'no-store',
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('knowledge/mcp/presets proxy error:', error);
    return NextResponse.json({ error: 'knowledge backend unreachable' }, { status: 502 });
  }
}
