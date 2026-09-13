"use client";
import {useEffect,useState} from 'react';
import {authFetch} from '@/helpers/auth';
import s from './memory.module.css';

type Entry={name:string;content:string;version:string|null;exists:boolean;path:string};
async function request(projectId:string|null,method='GET',body?:object){
  const res=await authFetch('/api/memory'+(method==='GET'&&projectId?'?project_id='+encodeURIComponent(projectId):''),{
    method,cache:'no-store',headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify({...body,project_id:projectId}):undefined,
  });
  const data=await res.json();
  if(!res.ok)throw new Error(typeof data.detail==='string'?data.detail:`请求失败（${res.status}）`);
  return data;
}
export default function MemoryEditor({projectId,projectName,onDirtyChange}:{projectId:string|null;projectName?:string;onDirtyChange?:(dirty:boolean)=>void}){
  const [scope,setScope]=useState<'user'|'project'>(projectId?'project':'user');
  const [files,setFiles]=useState<Entry[]>([]),[selected,setSelected]=useState<Entry|null>(null);
  const [draft,setDraft]=useState(''),[directory,setDirectory]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[deleting,setDeleting]=useState(false);
  const [topic,setTopic]=useState(''),[newTopic,setNewTopic]=useState(false),[disk,setDisk]=useState<Entry|null>(null);
  const target=scope==='project'?projectId:null;
  const dirty=!!selected&&draft!==selected.content;
  useEffect(()=>{onDirtyChange?.(dirty);return()=>onDirtyChange?.(false);},[dirty,onDirtyChange]);
  useEffect(()=>{
    let cancelled=false;setLoading(true);setFiles([]);setSelected(null);setDraft('');setDisk(null);setError('');setNotice('');
    request(target).then(data=>{if(!cancelled){setFiles(data.files);setDirectory(data.directory);setSelected(data.files[0]||null);setDraft(data.files[0]?.content||'');}})
      .catch(e=>{if(!cancelled)setError(e.message);}).finally(()=>{if(!cancelled)setLoading(false);});
    return()=>{cancelled=true;};
  },[target]);
  useEffect(()=>{const warn=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[dirty]);
  const pick=(file:Entry)=>{setSelected(file);setDraft(file.content);setDisk(null);setError('');setNotice('');setDeleting(false);};
  return <div className={s.editor}>
    <div className={s.toolbar}><label>作用范围<select aria-label="记忆作用范围" value={scope} disabled={busy||dirty} onChange={e=>setScope(e.target.value as 'user'|'project')}>
      <option value="user">用户偏好 · 所有项目</option><option value="project" disabled={!projectId}>{projectName||'当前项目'} · 项目记忆</option>
    </select></label>{scope==='project'&&<button disabled={busy||dirty||loading} onClick={()=>setNewTopic(!newTopic)}>新增主题</button>}</div>
    <small className={s.path}>{directory}</small>
    {error&&<p className={s.error} role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {newTopic&&<form className={s.toolbar} onSubmit={e=>{e.preventDefault();const name='memory/'+topic+'.md';if(files.some(f=>f.name===name)){setError('主题已存在');return;}const file={name,content:'',version:null,exists:false,path:directory+'/'+name};setFiles([...files,file]);pick(file);setNewTopic(false);setTopic('');}}>
      <label>主题文件名<input aria-label="主题文件名" pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,63}" required value={topic} onChange={e=>setTopic(e.target.value)} placeholder="experiments"/></label><button>创建草稿</button>
    </form>}
    {loading?<p>正在读取磁盘记忆…</p>:<>
      <div className={s.tabs} aria-label="记忆文件">{files.map(f=><button key={f.name} aria-pressed={f.name===selected?.name} disabled={busy||dirty} onClick={()=>pick(f)}>{f.name}{!f.exists?' · 未创建':''}</button>)}</div>
      {selected&&<><label className={s.body}>Markdown<textarea aria-label="记忆正文" spellCheck={false} value={draft} disabled={busy} onChange={e=>setDraft(e.target.value)} placeholder={scope==='user'?'例如：默认使用中文，回答尽量简洁。':'记录已确认的项目背景、约定或经验，注明来源。'}/></label>
        <small>{selected.version?'磁盘版本 '+selected.version.slice(0,12):'保存后创建本地文件'}{dirty?' · 有未保存修改':''}</small>
        <div className={s.toolbar}><button disabled={busy||!dirty} onClick={async()=>{setBusy(true);setError('');setNotice('');try{const saved=await request(target,'PUT',{name:selected.name,content:draft,version:selected.version});setFiles(files.map(f=>f.name===saved.name?saved:f));setSelected(saved);setDisk(null);setNotice('已保存，下次任务读取新版本。');}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>{busy?'处理中…':'保存'}</button>
          <button disabled={busy} onClick={async()=>{setBusy(true);setError('');try{const data=await request(target);const latest=data.files.find((f:Entry)=>f.name===selected.name)||{...selected,exists:false,content:'',version:null};if(dirty){setDisk(latest);setNotice('草稿未覆盖。核对磁盘内容后选择合并或放弃草稿。');}else{setFiles(data.files);pick(latest);}}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>读取磁盘版本</button>
          <button disabled={busy||dirty||!selected.exists} onClick={()=>setDeleting(true)}>删除文件</button>
        </div>
        {disk&&<div className={s.conflict}><strong>磁盘内容</strong><pre>{disk.content||'文件不存在或为空'}</pre><div className={s.toolbar}>
          <button onClick={()=>{setFiles(files.map(f=>f.name===disk.name?disk:f));setSelected(disk);setDisk(null);setNotice('已更新版本基线，请在上方合并草稿后保存。');}}>保留草稿，以磁盘版为基线</button>
          <button onClick={()=>{setFiles(files.map(f=>f.name===disk.name?disk:f));pick(disk);}}>放弃草稿，使用磁盘内容</button></div></div>}
        {deleting&&<div className={s.toolbar}><span>移入本目录 .trash，下次任务不再加载。</span><button onClick={()=>setDeleting(false)}>取消</button><button disabled={busy} onClick={async()=>{setBusy(true);setError('');try{const data=await request(target,'DELETE',{name:selected.name,version:selected.version});const blank={...selected,exists:false,version:null,content:''};pick(blank);setFiles(files.map(f=>f.name===selected.name?blank:f));setNotice('已移至 '+data.trash_path+'，可在本地恢复。');}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>确认移入回收目录</button></div>}
      </>}
    </>}
    <small>Markdown 为唯一正文。用户偏好跨项目生效；项目记忆仅用于本项目。未保存草稿请先保存或读取磁盘处理，再切换文件。</small>
  </div>;
}
