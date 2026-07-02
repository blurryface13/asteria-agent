"""
Postgres-backed replacement for backend/server/report_store.py's flat-JSON
ReportStore. Same shape of data (report dict with question/answer/
orderedData/chatMessages/timestamp), but:
  - persisted in a real table instead of read-modify-write-whole-file
  - every method takes user_email and filters by it, so one user can never
    see/edit/delete another user's saved reports (the JSON version had no
    ownership concept at all)
"""
from typing import Any, Dict, List, Optional

from backend.auth.db import get_pool


def _row_to_report(row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "question": row["question"],
        "answer": row["answer"],
        "orderedData": row["ordered_data"],
        "chatMessages": row["chat_messages"],
        "timestamp": row["timestamp"],
    }


class PgReportStore:
    async def list_reports(self, user_email: str, report_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if report_ids:
                rows = await conn.fetch(
                    "SELECT * FROM reports WHERE user_email = $1 AND id = ANY($2::text[])",
                    user_email, report_ids,
                )
            else:
                rows = await conn.fetch("SELECT * FROM reports WHERE user_email = $1", user_email)
            return [_row_to_report(r) for r in rows]

    async def get_report(self, report_id: str, user_email: str) -> Optional[Dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM reports WHERE id = $1 AND user_email = $2", report_id, user_email
            )
            return _row_to_report(row) if row else None

    async def upsert_report(self, report_id: str, report: Dict[str, Any], user_email: str) -> None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO reports (id, user_email, question, answer, ordered_data, chat_messages, "timestamp")
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7)
                ON CONFLICT (id) DO UPDATE SET
                    question = EXCLUDED.question,
                    answer = EXCLUDED.answer,
                    ordered_data = EXCLUDED.ordered_data,
                    chat_messages = EXCLUDED.chat_messages,
                    "timestamp" = EXCLUDED."timestamp"
                WHERE reports.user_email = $2
                """,
                report_id, user_email,
                report.get("question"), report.get("answer"),
                report.get("orderedData") or [],
                report.get("chatMessages") or [],
                report.get("timestamp"),
            )

    async def delete_report(self, report_id: str, user_email: str) -> bool:
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM reports WHERE id = $1 AND user_email = $2", report_id, user_email
            )
            # asyncpg returns strings like "DELETE 1" / "DELETE 0"
            return result.endswith(" 1")
