"""PostgreSQL persistence for the project/conversation workspace hierarchy."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.auth.db import get_pool


class WorkspaceNotFound(Exception):
    pass


class WorkspaceBusy(Exception):
    pass


def _project(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "workspace_path": row["workspace_path"],
        "settings": row["settings"] or {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _conversation(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "title": row["title"],
        "mode": row["mode"],
        "status": row["status"],
        "metadata": row["metadata"] or {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _message(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "conversation_id": row["conversation_id"],
        "role": row["role"],
        "content": row["content"],
        "metadata": row["metadata"] or {},
        "created_at": row["created_at"],
    }


class PgWorkspaceStore:
    async def list_projects(self, user_email: str) -> list[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, workspace_path, settings, created_at, updated_at
                FROM workspace_projects
                WHERE user_email = $1
                ORDER BY updated_at DESC
                """,
                user_email,
            )
        return [_project(row) for row in rows]

    async def get_project(self, project_id: str, user_email: str) -> dict[str, Any]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, workspace_path, settings, created_at, updated_at
                FROM workspace_projects
                WHERE id = $1 AND user_email = $2
                """,
                project_id,
                user_email,
            )
        if row is None:
            raise WorkspaceNotFound("project not found")
        return _project(row)

    async def create_project(
        self,
        user_email: str,
        name: str,
        workspace_path: str | None,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = str(uuid4())
        now = datetime.now(timezone.utc)
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO workspace_projects
                    (id, user_email, name, workspace_path, settings, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $6)
                RETURNING id, name, workspace_path, settings, created_at, updated_at
                """,
                project_id,
                user_email,
                name.strip(),
                workspace_path.strip() if workspace_path else None,
                settings,
                now,
            )
        return _project(row)

    async def update_project(
        self,
        project_id: str,
        user_email: str,
        name: str | None,
        workspace_path: str | None,
        settings: dict[str, Any] | None,
    ) -> dict[str, Any]:
        current = await self.get_project(project_id, user_email)
        now = datetime.now(timezone.utc)
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE workspace_projects
                SET name = $3,
                    workspace_path = $4,
                    settings = $5::jsonb,
                    updated_at = $6
                WHERE id = $1 AND user_email = $2
                RETURNING id, name, workspace_path, settings, created_at, updated_at
                """,
                project_id,
                user_email,
                name.strip() if name is not None else current["name"],
                workspace_path.strip() if workspace_path is not None else current["workspace_path"],
                settings if settings is not None else current["settings"],
                now,
            )
        if row is None:
            raise WorkspaceNotFound("project not found")
        return _project(row)

    async def delete_project(self, project_id: str, user_email: str) -> None:
        await self.get_project(project_id, user_email)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM workspace_projects WHERE id = $1 AND user_email = $2",
                project_id,
                user_email,
            )

    async def list_conversations(
        self, user_email: str, project_id: str | None = None
    ) -> list[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if project_id is None:
                rows = await conn.fetch(
                    """
                    SELECT id, project_id, title, mode, status, metadata, created_at, updated_at
                    FROM workspace_conversations
                    WHERE user_email = $1
                    ORDER BY updated_at DESC
                    """,
                    user_email,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, project_id, title, mode, status, metadata, created_at, updated_at
                    FROM workspace_conversations
                    WHERE user_email = $1 AND project_id = $2
                    ORDER BY updated_at DESC
                    """,
                    user_email,
                    project_id,
                )
        return [_conversation(row) for row in rows]

    async def get_conversation(
        self, conversation_id: str, user_email: str
    ) -> dict[str, Any]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, project_id, title, mode, status, metadata, created_at, updated_at
                FROM workspace_conversations
                WHERE id = $1 AND user_email = $2
                """,
                conversation_id,
                user_email,
            )
        if row is None:
            raise WorkspaceNotFound("conversation not found")
        return _conversation(row)

    async def create_conversation(
        self,
        user_email: str,
        title: str,
        mode: str,
        metadata: dict[str, Any],
        project_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        if project_id is not None:
            await self.get_project(project_id, user_email)
        conversation_id = conversation_id or str(uuid4())
        now = datetime.now(timezone.utc)
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO workspace_conversations
                    (id, user_email, project_id, title, mode, status, metadata, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, 'active', $6::jsonb, $7, $7)
                RETURNING id, project_id, title, mode, status, metadata, created_at, updated_at
                """,
                conversation_id,
                user_email,
                project_id,
                title.strip(),
                mode.strip(),
                metadata,
                now,
            )
        return _conversation(row)

    async def rename_conversation(
        self, conversation_id: str, user_email: str, title: str
    ) -> dict[str, Any]:
        await self.get_conversation(conversation_id, user_email)
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE workspace_conversations
                SET title = $3, updated_at = $4
                WHERE id = $1 AND user_email = $2
                RETURNING id, project_id, title, mode, status, metadata, created_at, updated_at
                """,
                conversation_id,
                user_email,
                title.strip(),
                datetime.now(timezone.utc),
            )
        return _conversation(row)

    async def delete_conversation(self, conversation_id: str, user_email: str) -> None:
        pool = await get_pool()
        async with pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow('SELECT id FROM workspace_conversations WHERE id=$1 AND user_email=$2 FOR UPDATE', conversation_id, user_email)
            if row is None:
                raise WorkspaceNotFound('conversation not found')
            if await conn.fetchval("SELECT 1 FROM coordinator_turns WHERE conversation_id=$1 AND status='running'", conversation_id):
                raise WorkspaceBusy('请等待当前回答结束后再删除对话')
            runs = await conn.fetch('SELECT id,status FROM research_runs WHERE conversation_id=$1 FOR UPDATE', conversation_id)
            if any(r['status'] not in {'completed', 'failed', 'cancelled', 'interrupted'} for r in runs):
                raise WorkspaceBusy('请先停止正在运行的任务，再删除对话')
            # User-requested deletion removes terminal DB history atomically.
            # Output files are retained; never recursively remove a workspace.
            for table in ('research_artifacts', 'research_approvals', 'research_events', 'research_jobs'):
                await conn.execute(f'DELETE FROM {table} WHERE run_id IN (SELECT id FROM research_runs WHERE conversation_id=$1)', conversation_id)
            await conn.execute('DELETE FROM research_runs WHERE conversation_id=$1', conversation_id)
            await conn.execute('DELETE FROM reports WHERE id=$1 AND user_email=$2', conversation_id, user_email)
            await conn.execute(
                "DELETE FROM workspace_conversations WHERE id = $1 AND user_email = $2",
                conversation_id,
                user_email,
            )

    async def list_messages(
        self, conversation_id: str, user_email: str
    ) -> list[dict[str, Any]]:
        await self.get_conversation(conversation_id, user_email)
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, conversation_id, role, content, metadata, created_at
                FROM workspace_messages
                WHERE conversation_id = $1
                ORDER BY sequence_no ASC
                """,
                conversation_id,
            )
        return [_message(row) for row in rows]

    async def append_message(
        self,
        conversation_id: str,
        user_email: str,
        role: str,
        content: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        await self.get_conversation(conversation_id, user_email)
        message_id = str(uuid4())
        now = datetime.now(timezone.utc)
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO workspace_messages
                        (id, conversation_id, role, content, metadata, created_at)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                    RETURNING id, conversation_id, role, content, metadata, created_at
                    """,
                    message_id,
                    conversation_id,
                    role.strip(),
                    content,
                    metadata,
                    now,
                )
                await conn.execute(
                    "UPDATE workspace_conversations SET updated_at = $2 WHERE id = $1",
                    conversation_id,
                    now,
                )
        return _message(row)


workspace_store = PgWorkspaceStore()
