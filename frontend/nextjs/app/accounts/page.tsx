"use client";
import {useEffect,useState} from 'react';
import Link from 'next/link';
import {authFetch,clearAuth,getAuthEmail} from '@/helpers/auth';
import {getHost} from '@/helpers/getHost';
import s from '@/components/knowledge/knowledge.module.css';
type Account={email:string;display_name:string;disabled:boolean;last_login_at:string|null};
export default function Accounts(){
  const [admin,setAdmin]=useState(false),[accounts,setAccounts]=useState<Account[]>([]);
  const [email,setEmail]=useState(''),[name,setName]=useState(''),[password,setPassword]=useState(''),[mode,setMode]=useState<'create'|'reset'>('create');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  async function api(path:string,body?:object){const r=await authFetch(getHost()+'/api/auth/'+path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined});if(r.status===204)return null;const d=await r.json();if(!r.ok)throw new Error(typeof d.detail==='string'?d.detail:'操作失败，请检查输入');return d;}
  async function refresh(){setAccounts((await api('accounts')).accounts);}
  useEffect(()=>{api('me').then(d=>{setAdmin(d.is_admin);if(d.is_admin)void refresh().catch(e=>setError(e.message));}).catch(e=>setError(e.message));},[]);
  return <main className={s.page}><section className={s.canvas}><header className={s.header}><h1>实验室账号</h1><Link href="/">返回工作台</Link></header><div className={s.detail}>
    <p>当前登录：{getAuthEmail()} · {admin?'管理员':'成员'}</p>
    <button onClick={async()=>{try{await api('logout',{});clearAuth();window.location.href='/login';}catch(e){setError(e instanceof Error?e.message:'注销失败');}}}>退出登录</button>
    {error&&<p role="alert" className={s.error}>{error}</p>}{notice&&<p role="status">{notice}</p>}
    {!admin?<p>账号由管理员维护。你的项目、会话、任务与记忆不与其他成员共享。</p>:<>
      <form className={s.form} onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');setNotice('');try{
        await api(mode==='create'?'accounts':'accounts/reset-password',{email,display_name:name,password});setPassword('');setNotice(mode==='create'?'账号已创建，请通过安全渠道告知成员密码。':'密码已重置，旧登录会话已失效。');await refresh();
      }catch(e){setError(e instanceof Error?e.message:'保存失败');}finally{setBusy(false);}}}>
        <h2>{mode==='create'?'添加实验室成员':'重置成员密码'}</h2>
        <label>操作<select value={mode} onChange={e=>setMode(e.target.value as 'create'|'reset')}><option value="create">创建账号</option><option value="reset">重置密码并启用账号</option></select></label>
        <label>邮箱<input type="email" autoComplete="off" required value={email} onChange={e=>setEmail(e.target.value)}/></label>
        <label>显示名称<input maxLength={100} value={name} onChange={e=>setName(e.target.value)}/></label>
        <label>初始密码<input type="password" autoComplete="new-password" minLength={12} maxLength={128} required value={password} onChange={e=>setPassword(e.target.value)}/></label>
        <small>12–128个字符。密码不显示在账号列表；重置会立即撤销该成员的旧会话。</small>
        <button className={s.primary} disabled={busy}>{busy?'保存中…':'确认保存'}</button>
      </form>
      <h2>成员列表</h2>{accounts.map(a=><div className={s.document} key={a.email}><div><strong>{a.display_name||a.email}</strong><small>{a.email} · {a.disabled?'已禁用':'可登录'} · {a.last_login_at?`最近登录 ${new Date(a.last_login_at).toLocaleString()}`:'尚未登录'}</small></div>
        {a.email!==getAuthEmail()&&!a.disabled&&<button disabled={busy} onClick={async()=>{if(!window.confirm(`禁用 ${a.email}？其旧会话将立即失效，历史数据保留。`))return;setBusy(true);try{await api('accounts/'+encodeURIComponent(a.email)+'/disable',{});await refresh();}catch(e){setError(e instanceof Error?e.message:'禁用失败');}finally{setBusy(false);}}}>禁用</button>}
      </div>)}
    </>}
  </div></section></main>;
}
