import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  const backendUrl = process.env.NEXT_PUBLIC_ASTERIA_API_URL || 'http://127.0.0.1:8000';
  try {
    const body = await request.json();
    const response = await fetch(`${backendUrl}/api/knowledge/modular/evaluation`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(request.headers.get('authorization')
          ? { Authorization: request.headers.get('authorization')! }
          : {}),
      },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('knowledge/modular/evaluation proxy error:', error);
    return NextResponse.json({ error: 'modular rag backend unreachable' }, { status: 502 });
  }
}
