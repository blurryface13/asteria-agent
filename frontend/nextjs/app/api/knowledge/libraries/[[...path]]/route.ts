import { NextResponse } from 'next/server';
async function proxy(request: Request, {params}: {params: {path?: string[]}}) {
  const suffix = (params.path || []).map(encodeURIComponent).join('/');
  const base = process.env.NEXT_PUBLIC_ASTERIA_API_URL || 'http://127.0.0.1:8018';
  try {
    const headers = new Headers();
    for (const name of ['authorization','content-type']) {const value=request.headers.get(name); if(value) headers.set(name,value);}
    const response = await fetch(`${base}/api/knowledge/libraries${suffix ? '/'+suffix : ''}`, {
      method:request.method,headers,cache:'no-store',body:['GET','HEAD'].includes(request.method)?undefined:await request.arrayBuffer(),
    });
    const output = new Headers({'Cache-Control':'no-store'});
    for (const name of ['content-type','content-disposition']) {const value=response.headers.get(name);if(value)output.set(name,value);}
    return new Response(response.status===204?null:response.body,{status:response.status,headers:output});
  } catch {return NextResponse.json({detail:'知识库服务暂不可达，请检查服务状态后重试'},{status:502});}
}
export {proxy as GET,proxy as POST,proxy as PATCH,proxy as DELETE};
