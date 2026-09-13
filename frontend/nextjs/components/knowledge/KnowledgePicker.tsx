"use client";
import {useEffect,useState} from 'react';
import Link from 'next/link';
import {ChatBoxSettings} from '@/types/data';
import {knowledgeRequest,Library} from './client';
import s from './knowledge.module.css';
export default function KnowledgePicker({settings,onChange,conversationId}:{settings:ChatBoxSettings;onChange:(values:Partial<ChatBoxSettings>)=>void;conversationId?:string|null}) {
  const [libraries,setLibraries]=useState<Library[]>([]),[error,setError]=useState(''),[message,setMessage]=useState('');
  const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false);
  useEffect(()=>{knowledgeRequest().then(d=>setLibraries(d.libraries)).catch(e=>setError(e.message)).finally(()=>setLoading(false));},[]);
  return <div className={s.picker}>
    <label>资料范围<select value={settings.knowledge_mode||'auto'} onChange={e=>onChange({knowledge_mode:e.target.value as 'auto'|'selected'|'off'})}>
      <option value="auto">自动发现知识库</option><option value="selected">指定知识库问答</option><option value="off">不使用知识库</option>
    </select></label>
    {settings.knowledge_mode==='selected'&&<fieldset><legend>选择知识库（最多3个）</legend>{libraries.map(k=><label className={s.check} key={k.id}>
      <input type="checkbox" checked={settings.knowledge_ids?.includes(k.id)||false} disabled={!settings.knowledge_ids?.includes(k.id)&&(settings.knowledge_ids?.length||0)>=3}
        onChange={e=>onChange({knowledge_ids:e.target.checked?[...(settings.knowledge_ids||[]),k.id]:settings.knowledge_ids?.filter(id=>id!==k.id)})}/>
      <span>{k.name}<small>{k.ready_documents} 份可检索文档</small></span></label>)}</fieldset>}
    {loading&&<p>正在读取知识库…</p>}{!loading&&!libraries.length&&!error&&<p>还没有个人知识库，可以先创建并上传资料。</p>}
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    <div className={s.actions}><Link href="/knowledge">管理知识库</Link>{conversationId&&<button disabled={busy||settings.knowledge_ids?.length!==1} onClick={async()=>{
      setBusy(true);setError('');setMessage('');try{await knowledgeRequest('/'+settings.knowledge_ids![0]+'/report','POST',{conversation_id:conversationId});setMessage('报告已提交索引，可在知识库查看进度。');}
      catch(e){setError(e instanceof Error?e.message:'入库失败');}finally{setBusy(false);}
    }}>{busy?'提交中…':'将当前报告存入所选库'}</button>}</div>
    <small>选择作用于下一条消息。指定知识库只依据资料回答，不启动联网调研。</small>
  </div>;
}
