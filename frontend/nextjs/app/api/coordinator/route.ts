import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  const backendUrl = process.env.NEXT_PUBLIC_ASTERIA_API_URL || 'http://localhost:8000';
  try {
    const body = await request.json();
    const response = await fetch(`${backendUrl}/api/coordinator/route`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(request.headers.get('authorization')
          ? { Authorization: request.headers.get('authorization')! }
          : {}),
      },
      body: JSON.stringify(body),
      cache: 'no-store',
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('POST /api/coordinator/route - Error proxying to backend:', error);
    return NextResponse.json(
      { error: 'Failed to connect to coordinator service' },
      { status: 502 },
    );
  }
}
