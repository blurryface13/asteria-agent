# backend

FastAPI service layer. It exposes auth, report, chat, WebSocket streaming, and persistence APIs used by the web frontend and research runtime.

## Persistence

The backend uses PostgreSQL for durable application state. At startup it
idempotently applies `auth/schema.sql`, `auth/reports_schema.sql`, and
`auth/workspace_schema.sql` through the configured `DATABASE_URL`.

The workspace hierarchy is:

```text
project
└── conversation
    └── message
```

The HTTP surface is under `/api/workspace`. Reports remain available through
the existing `/api/reports` compatibility API while the frontend migrates to
the workspace hierarchy. Redis is intentionally not part of this durable
path; it remains suitable for short-lived verification codes and runtime
state.
