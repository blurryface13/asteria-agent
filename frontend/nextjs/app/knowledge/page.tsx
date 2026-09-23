"use client";
import {useCallback,useEffect,useState} from 'react';
import Link from 'next/link';
import Icon from '@/components/harness/Icon';
import {authFetch} from '@/helpers/auth';
import {getHost} from '@/helpers/getHost';
import {knowledgeRequest,Library,LibraryDocument} from '@/components/knowledge/client';
import s from '@/components/knowledge/knowledge.module.css';

export default function KnowledgePage(){
  const [libraries,setLibraries]=useState<Library[]>([]),[selected,setSelected]=useState('');
  const [documents,setDocuments]=useState<LibraryDocument[]>([]);
  const [editing,setEditing]=useState<'new'|'edit'|null>(null),[name,setName]=useState(''),[description,setDescription]=useState('');
  const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [deleting,setDeleting]=useState<string|null>(null);
  const [admin,setAdmin]=useState(false),[visibility,setVisibility]=useState<'private'|'lab'>('private');
  useEffect(()=>{authFetch(getHost()+'/api/auth/me').then(r=>r.json()).then(d=>setAdmin(d.is_admin===true)).catch(()=>{});},[]);
  const current=libraries.find(k=>k.id===selected);
  const refresh=useCallback(async()=>{const data=await knowledgeRequest();setLibraries(data.libraries);return data.libraries as Library[];},[]);
  useEffect(()=>{refresh().then(data=>setSelected(data[0]?.id||'')).catch(e=>setError(e.message)).finally(()=>setLoading(false));},[refresh]);
  useEffect(()=>{
    if(!selected||selected==='lab-research-papers'){setDocuments([]);return;}
    let cancelled=false;setDocuments([]);
    const read=async()=>{try{const data=await knowledgeRequest('/'+selected+'/documents');if(!cancelled){setDocuments(data.documents);setLibraries(previous=>previous.map(k=>k.id===selected?{...k,documents:data.documents.length,ready_documents:data.documents.filter((d:LibraryDocument)=>d.active_version).length}:k));}}catch(e){if(!cancelled)setError(e instanceof Error?e.message:'读取失败');}};
    void read();const timer=setInterval(read,4000);return()=>{cancelled=true;clearInterval(timer);};
  },[selected]);
  const begin=(mode:'new'|'edit')=>{setEditing(mode);setName(mode==='edit'?current?.name||'':'');setDescription(mode==='edit'?current?.description||'':'');setVisibility(mode==='edit'?current?.visibility||'private':admin?'lab':'private');setError('');};
  const reloadDocs=async()=>{setDocuments((await knowledgeRequest('/'+selected+'/documents')).documents);await refresh();};
  return <main className={s.page}>
    <aside className={s.rail}><Link className={s.brand} href="/"><img src="/img/asteria-logo.png" alt="Asteria"/>个人</Link>
      <nav><Link href="/"><Icon name="new"/>新任务</Link><Link href="/knowledge" aria-current="page"><Icon name="folder"/>知识库</Link><Link href="/rag-workspace"><Icon name="search"/>检索分析</Link></nav>
      <div className={s.footer}>Asteria Research</div>
    </aside>
    <section className={s.canvas}><header className={s.header}><h1>知识库</h1><div className={s.actions}><Link href="/">返回任务</Link><button className={s.primary} onClick={()=>begin('new')} disabled={busy}>新建知识库</button></div></header>
      <div className={s.body}><aside className={s.list} aria-label="知识库列表">
        {loading&&<p>正在读取…</p>}{!loading&&!libraries.length&&<p>创建知识库，添加你的资料。</p>}
        {libraries.map(k=><button key={k.id} disabled={busy} aria-pressed={selected===k.id&&!editing} onClick={()=>{setSelected(k.id);setEditing(null);setError('');setNotice('');setDeleting(null);}}><strong>{k.name}</strong><small>{k.visibility==='lab'?'实验室共享':'个人私有'} · {k.built_in?'既有论文索引':`${k.ready_documents} / ${k.documents} 份可检索`}</small></button>)}
      </aside><div className={s.detail}>
        {error&&<p role="alert" className={s.error}>{error}</p>}{notice&&<p role="status" className={s.status}>{notice}</p>}
        {editing?<form className={s.form} onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{
          const k=await knowledgeRequest(editing==='new'?'':'/'+selected,editing==='new'?'POST':'PATCH',{name:name.trim(),description,visibility});await refresh();setSelected(k.id);setEditing(null);
        }catch(e){setError(e instanceof Error?e.message:'保存失败');}finally{setBusy(false);}}}>
          <h2>{editing==='new'?'新建知识库':'编辑知识库'}</h2>
          <label>名称<input autoFocus value={name} onChange={e=>setName(e.target.value)} maxLength={120} required/></label>
          <label>内容简介<textarea value={description} onChange={e=>setDescription(e.target.value)} maxLength={1200} rows={4} placeholder="说明资料主题，帮助 Agent 判断何时检索这个知识库"/></label>
          {admin&&<label>可见范围<select value={visibility} onChange={e=>setVisibility(e.target.value as 'private'|'lab')}><option value="lab">实验室共享 · 登录成员可读，管理员维护</option><option value="private">个人私有 · 仅自己可读写</option></select></label>}
          <small>{visibility==='lab'?'保存后库内全部资料将对实验室成员开放，请勿上传个人隐私或保密资料。':'资料不会出现在其他成员的检索范围中。'}</small>
          <div className={s.actions}><button type="button" disabled={busy} onClick={()=>setEditing(null)}>取消</button><button className={s.primary} disabled={busy||!name.trim()}>{busy?'保存中…':'保存'}</button></div>
        </form>:current?<>
          <h2>{current.name}</h2><p>{current.description||'尚未添加内容简介。'}</p>
          <div className={s.actions}>{current.can_manage&&<button onClick={()=>begin('edit')}>编辑资料库</button>}<button onClick={()=>{
            localStorage.setItem('asteria.knowledgeSelection',JSON.stringify({knowledge_mode:'selected',knowledge_ids:[current.id]}));window.location.href='/';
          }}>在主界面提问</button><button onClick={()=>void reloadDocs().catch(e=>setError(e.message))}>刷新</button></div>
          {!current.can_manage&&<p>此库为只读共享资料。补充或更新内容请联系管理员；个人对话、任务和报告仍独立保存。</p>}
          {current.can_manage&&<><label className={s.fileInput}>添加或更新文档
          <input aria-label="上传知识库文档" type="file" accept=".pdf,.md,.txt" multiple disabled={busy} onChange={async e=>{
            const files=Array.from(e.target.files||[]);e.target.value='';setBusy(true);setError('');setNotice('');
            try{for(const file of files){const form=new FormData();form.set('file',file);await knowledgeRequest('/'+selected+'/documents','POST',form);}await reloadDocs();setNotice('已提交，索引完成后即可检索。');}
            catch(e){setError(e instanceof Error?e.message:'上传失败');}finally{setBusy(false);}
          }}/></label>
          <small>PDF、Markdown、TXT，单文件最多64MiB。同名文件更新版本；相同内容跳过，新版本完成前仍可查询旧版。扫描PDF需先OCR。</small></>}
          {!documents.length&&!current.built_in&&<p className={s.empty}>{current.can_manage?'添加第一份资料，或从任务中选择报告入库。':'管理员尚未添加文档。'}</p>}
          {documents.map(d=><div className={s.document} key={d.id}><div><strong>{d.name}</strong><small>
            {({queued:'等待索引',indexing:'正在索引',ready:'可检索',failed:'索引失败'} as Record<string,string>)[d.status]||d.status} · {d.chunks} 个片段
            {' · '}{new Date(d.created_at).toLocaleString()}
            {d.active_version&&d.active_version!==d.latest_version?' · 旧版仍可用':''}
          </small>{d.error&&<small className={s.error}>{d.error}</small>}</div>
            <div className={s.actions}>{d.active_version&&<button disabled={busy} onClick={async()=>{try{
              const res=await authFetch('/api/knowledge/libraries/'+selected+'/documents/'+d.id+'/source');if(!res.ok)throw new Error('下载失败');
              const url=URL.createObjectURL(await res.blob());const a=document.createElement('a');a.href=url;a.download=d.name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
            }catch(e){setError(e instanceof Error?e.message:'下载失败');}}}>原文</button>}
            {current.can_manage&&(deleting===d.id?<><span>删除后无法检索</span><button onClick={()=>setDeleting(null)}>取消</button><button disabled={busy} onClick={async()=>{setBusy(true);setError('');try{await knowledgeRequest('/'+selected+'/documents/'+d.id,'DELETE');await reloadDocs();setDeleting(null);}catch(e){setError(e instanceof Error?e.message:'删除失败');}finally{setBusy(false);}}}>确认删除</button></>
            :<button disabled={busy||['queued','indexing'].includes(d.status)} onClick={()=>setDeleting(d.id)}>删除</button>)}</div>
          </div>)}
        </>:<p className={s.empty}>选择或创建一个知识库。</p>}
      </div></div>
    </section>
  </main>;
}
