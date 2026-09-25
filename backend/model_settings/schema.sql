CREATE TABLE IF NOT EXISTS agent_model_settings (
    role text PRIMARY KEY,
    model text NOT NULL,
    encrypted_key text,
    key_tail text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
