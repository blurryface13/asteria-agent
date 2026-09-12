import { NextResponse } from 'next/server';

export async function GET(request: Request) {
  const backendUrl = process.env.NEXT_PUBLIC_ASTERIA_API_URL || 'http://localhost:8000';
  const params = new URL(request.url).searchParams;
  const query = new URLSearchParams({ conversation_id: params.get('conversation_id') || '' });
  if (params.get('request_id')) query.set('request_id', params.get('request_id')!);
  try {
    const response = await fetch(`${backendUrl}/api/coordinator/turn?${query}`, {
      headers: request.headers.get('authorization') ? { Authorization: request.headers.get('authorization')! } : {},
      cache: 'no-store',
    });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ error: '协调服务暂不可达，请重新打开对话恢复进度' }, { status: 502 });
  }
}

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
