"use client";
import {useEffect,useState} from 'react';
import {useRouter} from 'next/navigation';
import {getHost} from '@/helpers/getHost';
import {isLocalAuthBypassEnabled,setAuth} from '@/helpers/auth';

export default function LoginPage(){
  const router=useRouter();
  const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[code,setCode]=useState('');
  const [mode,setMode]=useState<'password'|'code'>('password');
  const [emailEnabled,setEmailEnabled]=useState(false),[sent,setSent]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  useEffect(()=>{
    if(isLocalAuthBypassEnabled()){router.replace('/');return;}
    fetch(getHost()+'/api/auth/config').then(r=>r.json()).then(d=>setEmailEnabled(d.email_login===true)).catch(()=>{});
  },[router]);
  const submit=async()=>{
    setBusy(true);setError('');setNotice('');
    const sending=mode==='code'&&!sent;
    try{
      const response=await fetch(getHost()+'/api/auth/'+(mode==='password'?'login':sending?'send-code':'verify-code'),{
        method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({email:email.trim().toLowerCase(),...(mode==='password'?{password}:sending?{}:{code})})});
      const data=await response.json();
      if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'请检查邮箱及输入格式后重试');
      if(sending){setSent(true);setNotice(data.message);}
      else{setAuth(data.access_token,data.email);setPassword('');window.location.assign('/');}
    }catch(e){setError(e instanceof Error?e.message:'连接失败，请检查服务是否运行');}finally{setBusy(false);}
  };
  const field='w-full rounded-lg border border-white/20 bg-white/5 px-3 py-3 text-white focus:outline-none focus:ring-2 focus:ring-white/50';
  return <main className="min-h-screen bg-[#171717] text-white flex items-center justify-center px-6">
    <section className="w-full max-w-sm py-12" aria-labelledby="login-title">
      <img src="/img/asteria-logo.png" alt="" width={48} height={48} className="mb-6 rounded-xl"/>
      <h1 id="login-title" className="text-2xl font-semibold">登录 Asteria</h1>
      <p className="mt-3 mb-8 text-sm text-white/65 leading-6">实验室共享资料，个人独立工作区。<br/>请使用管理员为你创建的账号。</p>
      <form className="space-y-5" onSubmit={e=>{e.preventDefault();void submit();}}>
        <label className="block text-sm">邮箱<input className={field+' mt-2'} type="email" autoComplete="username" required value={email} onChange={e=>{setEmail(e.target.value);setSent(false);}} disabled={busy}/></label>
        {mode==='password'?<label className="block text-sm">密码<input className={field+' mt-2'} type="password" autoComplete="current-password" minLength={12} maxLength={128} required value={password} onChange={e=>setPassword(e.target.value)} disabled={busy}/></label>
          :sent&&<label className="block text-sm">验证码<input className={field+' mt-2'} inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required value={code} onChange={e=>setCode(e.target.value)}/></label>}
        {error&&<p role="alert" className="text-sm text-red-300">{error}</p>}{notice&&<p role="status" className="text-sm text-white/70">{notice}</p>}
        <button disabled={busy} className="w-full rounded-lg bg-white px-4 py-3 text-sm font-medium text-black hover:bg-white/85 disabled:opacity-50">{busy?'请稍候…':mode==='code'&&!sent?'发送验证码':'登录'}</button>
      </form>
      {emailEnabled&&<button className="mt-5 text-sm text-white/70 underline" onClick={()=>{setMode(mode==='password'?'code':'password');setError('');}}>{mode==='password'?'使用邮箱验证码':'使用密码登录'}</button>}
      <p className="mt-6 text-xs leading-5 text-white/50">没有账号或忘记密码？请联系实验室管理员。退出登录会立即注销当前会话。</p>
    </section>
  </main>;
}
