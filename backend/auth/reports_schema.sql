-- 把原来 flat JSON 文件(ReportStore)迁到 Postgres,顺带补上归属字段
CREATE TABLE IF NOT EXISTS reports (
    id VARCHAR(255) PRIMARY KEY,
    user_email VARCHAR(255) NOT NULL,
    question TEXT,
    answer TEXT,
    ordered_data JSONB NOT NULL DEFAULT '[]',
    chat_messages JSONB NOT NULL DEFAULT '[]',
    "timestamp" BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_user_email ON reports(user_email);
