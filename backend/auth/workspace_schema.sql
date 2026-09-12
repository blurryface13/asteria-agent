-- Persistent hierarchy for the ClawsGO/Codex-style workspace.
-- Projects and conversations are owned by the authenticated email.  We keep
-- ownership as a value rather than an FK to users so local auth-bypass mode
-- can be used before an email has completed the login flow.

CREATE TABLE IF NOT EXISTS workspace_projects (
    id VARCHAR(100) PRIMARY KEY,
    user_email VARCHAR(255) NOT NULL,
    name VARCHAR(120) NOT NULL,
    workspace_path TEXT,
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspace_projects_user_updated
    ON workspace_projects(user_email, updated_at DESC);

CREATE TABLE IF NOT EXISTS workspace_conversations (
    id VARCHAR(100) PRIMARY KEY,
    user_email VARCHAR(255) NOT NULL,
    project_id VARCHAR(100),
    title VARCHAR(255) NOT NULL,
    mode VARCHAR(64) NOT NULL DEFAULT 'research',
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_workspace_conversation_project
        FOREIGN KEY (project_id) REFERENCES workspace_projects(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_workspace_conversations_user_updated
    ON workspace_conversations(user_email, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_workspace_conversations_project_updated
    ON workspace_conversations(project_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS workspace_messages (
    id VARCHAR(100) PRIMARY KEY,
    conversation_id VARCHAR(100) NOT NULL,
    role VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sequence_no BIGSERIAL NOT NULL,
    CONSTRAINT fk_workspace_message_conversation
        FOREIGN KEY (conversation_id) REFERENCES workspace_conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_workspace_messages_conversation_sequence
    ON workspace_messages(conversation_id, sequence_no);

CREATE TABLE IF NOT EXISTS coordinator_turns (
    conversation_id VARCHAR(100) NOT NULL REFERENCES workspace_conversations(id) ON DELETE CASCADE,
    request_id VARCHAR(100) NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running','completed','failed','interrupted')),
    result JSONB,
    error TEXT,
    usage JSONB NOT NULL DEFAULT '[]',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    PRIMARY KEY (conversation_id, request_id)
);

-- Existing local databases may have been created during the first draft with
-- VARCHAR(36) identifiers. Widen them without dropping any user data.
ALTER TABLE workspace_projects ALTER COLUMN id TYPE VARCHAR(100);
ALTER TABLE workspace_conversations ALTER COLUMN id TYPE VARCHAR(100);
ALTER TABLE workspace_conversations ALTER COLUMN project_id TYPE VARCHAR(100);
ALTER TABLE workspace_messages ALTER COLUMN id TYPE VARCHAR(100);
ALTER TABLE workspace_messages ALTER COLUMN conversation_id TYPE VARCHAR(100);
