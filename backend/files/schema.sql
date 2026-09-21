CREATE TABLE IF NOT EXISTS file_proposals (
 id TEXT PRIMARY KEY, user_email TEXT NOT NULL, path TEXT NOT NULL,
 operation TEXT NOT NULL CHECK(operation IN ('write','delete')),
 content TEXT NOT NULL DEFAULT '', expected_version TEXT,
 before_content TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','applied','rejected','failed')),
 error TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS file_proposals_owner ON file_proposals(user_email,created_at DESC);
