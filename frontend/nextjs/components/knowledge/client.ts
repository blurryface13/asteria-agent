import {authFetch} from '@/helpers/auth';
export interface Library {id:string;name:string;description:string;documents:number;ready_documents:number;updated_at:string}
export interface LibraryDocument {id:string;name:string;active_version:string|null;latest_version:string;status:string;error:string|null;chunks:number;created_at:string}
export async function knowledgeRequest(path='',method='GET',body?:object|FormData) {
  const form=body instanceof FormData;
  const res=await authFetch('/api/knowledge/libraries'+path,{method,cache:'no-store',headers:body&&!form?{'Content-Type':'application/json'}:undefined,body:body?(form?body as FormData:JSON.stringify(body)):undefined});
  if(res.status===204)return null;
  const data=await res.json();
  if(!res.ok)throw new Error(typeof data.detail==='string'?data.detail:`操作失败（${res.status}）`);
  return data;
}
