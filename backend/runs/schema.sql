CREATE TABLE IF NOT EXISTS research_runs (
    id TEXT PRIMARY KEY,
    user_email TEXT NOT NULL,
    conversation_id VARCHAR(100) NOT NULL REFERENCES workspace_conversations(id),
    request_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    request JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN
      ('queued','running','waiting_approval','cancel_requested','completed','failed','cancelled','interrupted')),
    sequence BIGINT NOT NULL DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    UNIQUE(user_email, request_key)
);
CREATE INDEX IF NOT EXISTS research_runs_conversation ON research_runs(conversation_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS research_runs_one_active ON research_runs(conversation_id)
 WHERE status IN ('queued','running','waiting_approval','cancel_requested');
CREATE TABLE IF NOT EXISTS research_jobs (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES research_runs(id),
    worker_id TEXT,
    lease_until TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS research_events (
    run_id TEXT NOT NULL REFERENCES research_runs(id),
    sequence BIGINT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(run_id, sequence)
);
CREATE TABLE IF NOT EXISTS research_approvals (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES research_runs(id),
    question JSONB NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','answered','closed')),
    response TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    answered_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS research_one_pending_approval ON research_approvals(run_id) WHERE state='pending';
CREATE TABLE IF NOT EXISTS research_artifacts (
    run_id TEXT NOT NULL REFERENCES research_runs(id),
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    PRIMARY KEY(run_id,kind)
);
