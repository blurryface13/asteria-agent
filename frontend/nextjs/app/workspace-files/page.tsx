"use client";
import {useEffect,useState} from 'react';
import Link from 'next/link';
import {authFetch} from '@/helpers/auth';
import {getHost} from '@/helpers/getHost';
import s from '@/components/knowledge/knowledge.module.css';
type Proposal={id:string;path:string;operation:string;state:string;content:string;before_content:string;fresh:boolean;error:string|null};
export default function WorkspaceFiles(){
  const [files,setFiles]=useState<{name:string}[]>([]),[proposals,setProposals]=useState<Proposal[]>([]);
  const [preview,setPreview]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  async function api(path='',body?:object){const r=await authFetch(getHost()+'/api/workspace-files'+path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined});const d=await r.json();if(!r.ok)throw new Error(typeof d.detail==='string'?d.detail:'文件操作失败');return d;}
  async function refresh(){const d=await api();setFiles(d.files);setProposals(d.proposals);}
  useEffect(()=>{void refresh().catch(e=>setError(e.message));},[]);
  return <main className={s.page}><section className={s.canvas}><header className={s.header}><h1>文件提案</h1><div className={s.actions}><button disabled={busy} onClick={()=>void refresh().catch(e=>setError(e.message))}>刷新</button><Link href="/">返回工作台</Link></div></header>
    <div className={s.detail}><p>在主界面发送“查找我的文件”或“创建 analysis.py”。Agent 通过 MCP 读取文件和生成变更提案，只有你确认后才会落盘。代码不会自动执行。</p>
      {error&&<p className={s.error} role="alert">{error}</p>}
      <h2>个人文件</h2><div className={s.actions}>{files.map(f=><button key={f.name} onClick={async()=>{try{setPreview((await api('/content?name='+encodeURIComponent(f.name))).content);}catch(e){setError(e instanceof Error?e.message:'读取失败');}}}>{f.name}</button>)}</div>
      {!files.length&&<p>工作区暂无文件。先在主界面请求创建文件，再到此确认提案。</p>}
      {preview&&<pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',padding:'16px',background:'#232323',maxHeight:360,overflow:'auto'}}>{preview}</pre>}
      <h2 style={{marginTop:28}}>变更记录</h2>{!proposals.length&&<p>暂无提案。文件改动会展示原始内容和新内容，便于确认。</p>}
      {proposals.map(p=><section key={p.id} style={{padding:'20px 0',borderBottom:'1px solid #363636'}}>
        <h3>{p.path} · {p.operation==='delete'?'删除至回收目录':'写入'} · {({pending:p.fresh?'待确认':'已过期',applied:'已应用',rejected:'已拒绝',failed:'失败'} as Record<string,string>)[p.state]}</h3>
        <details><summary>查看原始内容</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',maxHeight:320,overflow:'auto'}}>{p.before_content||'（新文件）'}</pre></details>
        {p.operation==='write'&&<details open={p.state==='pending'}><summary>查看新内容</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',maxHeight:360,overflow:'auto'}}>{p.content||'（空文件）'}</pre></details>}
        {p.error&&<p className={s.error}>{p.error}</p>}
        {p.state==='pending'&&p.fresh&&<div className={s.actions}>{[true,false].map(approve=><button key={String(approve)} disabled={busy} className={approve?s.primary:undefined} onClick={async()=>{setBusy(true);setError('');try{await api('/proposals/'+p.id,{approve});await refresh();}catch(e){setError(e instanceof Error?e.message:'处理失败');await refresh();}finally{setBusy(false);}}}>{approve?'确认应用':'拒绝提案'}</button>)}</div>}
      </section>)}
    </div>
  </section></main>;
}
