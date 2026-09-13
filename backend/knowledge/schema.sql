CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS knowledge_bases_owner ON knowledge_bases(owner);
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    active_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(kb_id,name)
);
CREATE TABLE IF NOT EXISTS knowledge_versions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    digest TEXT NOT NULL,
    filename TEXT NOT NULL,
    payload BYTEA NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','indexing','ready','failed')),
    error TEXT,
    chunks INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS knowledge_one_pending ON knowledge_versions(document_id) WHERE status IN ('queued','indexing');
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES knowledge_versions(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    page INTEGER
);
CREATE INDEX IF NOT EXISTS knowledge_chunks_version ON knowledge_chunks(version_id);
-- No FK: cleanup must survive deletion of the source document/library.
CREATE TABLE IF NOT EXISTS knowledge_vector_gc (
    version_id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    retry_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
