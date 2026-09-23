"""Read-only adapter for the explicitly published existing paper collection."""
import os
from pathlib import Path

ID='lab-research-papers'


def catalog():
    if os.getenv('ASTERIA_PUBLISH_PAPER_CORPUS','0')!='1':
        return []
    return [{'id':ID,'name':'实验室论文库','description':'课题组研究资料，论文方法、实验及数字水印等领域问答；复用现有混合检索索引。',
             'visibility':'lab','can_manage':False,'built_in':True,'documents':None,'ready_documents':None}]


async def retrieve(query,top_k=6):
    from backend.knowledge.modular_rag import get_modular_bridge,DEFAULT_COLLECTION
    result=await get_modular_bridge().trace(query,top_k=top_k,collection=DEFAULT_COLLECTION)
    # Never expose filesystem paths or arbitrary source metadata.
    return [{'id':str(r.get('chunk_id',i)),'kb_id':ID,'version_id':'shared-index',
             'name':Path(str(r.get('title') or '论文片段')).name,
             'page':r.get('page'),'content':str(r.get('content') or '')[:6000],
             'score':r.get('score',0)} for i,r in enumerate(result['stages']['rerank'])]
