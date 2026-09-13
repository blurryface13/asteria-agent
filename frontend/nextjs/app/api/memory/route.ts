import {NextResponse} from 'next/server';
async function proxy(request:Request) {
  try {
    const headers=new Headers();
    for(const name of ['authorization','content-type']){const value=request.headers.get(name);if(value)headers.set(name,value);}
    const res=await fetch(`${process.env.NEXT_PUBLIC_ASTERIA_API_URL||'http://127.0.0.1:8018'}/api/memory${new URL(request.url).search}`,{
      method:request.method,headers,cache:'no-store',body:request.method==='GET'?undefined:await request.text(),
    });
    return new Response(res.body,{status:res.status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
  }catch{return NextResponse.json({detail:'记忆服务不可达，请检查后端状态'},{status:502});}
}
export {proxy as GET,proxy as PUT,proxy as DELETE};
