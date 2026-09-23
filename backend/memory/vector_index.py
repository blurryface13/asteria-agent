"""Rebuildable, identity-scoped Chroma index for editable Markdown memories."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import os
from pathlib import Path


def _embedding_spec() -> tuple[str, str]:
    value = os.getenv('ASTERIA_MEMORY_EMBEDDING', os.getenv('EMBEDDING', 'ollama:bge-m3'))
    provider, separator, model = value.partition(':')
    if not separator or not provider or not model:
        raise ValueError('ASTERIA_MEMORY_EMBEDDING must be provider:model')
    return provider, model


@lru_cache(maxsize=8)
def _embedder(provider: str, model: str):
    from asteria_researcher.memory.embeddings import Memory
    if provider == 'ollama':
        os.environ.setdefault('OLLAMA_BASE_URL', 'http://127.0.0.1:11434')
    return Memory(provider, model).get_embeddings()


@lru_cache(maxsize=8)
def _collection(directory: str, provider: str, model: str):
    import chromadb
    Path(directory).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=directory)
    suffix = hashlib.sha256(f'{provider}:{model}'.encode()).hexdigest()[:12]
    return client.get_or_create_collection(name=f'asteria_memory_{suffix}', embedding_function=None)


def _chunks(text: str) -> list[str]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    return RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=100).split_text(text)


def recall(email: str, project_id: str, query: str, topics: list[dict], directory: str) -> list[str]:
    """Synchronize only this user's current project's topic files, then rank them.

    The Markdown inventory is already ownership-checked by the caller. Chroma
    is derived state: edits and deletions are reflected on the next read.
    """
    provider, model = _embedding_spec()
    collection = _collection(directory, provider, model)
    embedder = _embedder(provider, model)
    scope = hashlib.sha256(f'{email.casefold()}\0{project_id}'.encode()).hexdigest()
    existing = collection.get(where={'scope': scope}, include=['metadatas'])
    current = {row['name']: row for row in topics}
    obsolete = []
    indexed = {}
    for item_id, metadata in zip(existing['ids'], existing['metadatas']):
        name = metadata['name']
        row = current.get(name)
        if row is None or row['version'] != metadata['version']:
            obsolete.append(item_id)
        else:
            indexed[name] = True
    if obsolete:
        collection.delete(ids=obsolete)
    for name, row in current.items():
        if name in indexed:
            continue
        chunks = _chunks(row['content'])
        if not chunks:
            continue
        vectors = embedder.embed_documents(chunks)
        identifier = hashlib.sha256(f'{scope}\0{name}'.encode()).hexdigest()
        collection.upsert(
            ids=[f'{identifier}:{index}' for index in range(len(chunks))],
            embeddings=vectors,
            documents=chunks,
            metadatas=[{'scope': scope, 'name': name, 'version': row['version']} for _ in chunks],
        )
    chunk_count = sum(len(_chunks(row['content'])) for row in current.values())
    if not chunk_count or not query.strip():
        return []
    results = collection.query(
        query_embeddings=[embedder.embed_query(query)],
        where={'scope': scope},
        n_results=min(12, chunk_count),
        include=['metadatas'],
    )
    names = []
    for metadata in results['metadatas'][0]:
        name = metadata['name']
        if name in current and name not in names:
            names.append(name)
        if len(names) == 3:
            break
    return names
