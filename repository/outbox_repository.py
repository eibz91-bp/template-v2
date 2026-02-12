import json

from database.context import get_current_connection
from exception.decorators import handle_db_errors


class OutboxRepository:

    @handle_db_errors
    async def save(self, destination: str, payload: dict) -> dict:
        conn = get_current_connection()
        record = await conn.fetchrow(
            """INSERT INTO outbox (destination, payload)
               VALUES ($1, $2::jsonb)
               RETURNING *""",
            destination, json.dumps(payload)
        )
        return dict(record)

    @handle_db_errors
    async def get_pending(self, limit: int = 10) -> list[dict]:
        conn = get_current_connection()
        records = await conn.fetch(
            """SELECT * FROM outbox
               WHERE status = 'pending'
               ORDER BY created_at
               LIMIT $1""",
            limit
        )
        return [dict(r) for r in records]

    @handle_db_errors
    async def mark_sent(self, outbox_id: int) -> None:
        conn = get_current_connection()
        await conn.execute(
            """UPDATE outbox SET status = 'sent', sent_at = NOW()
               WHERE id = $1""",
            outbox_id
        )

    @handle_db_errors
    async def increment_retry(self, outbox_id: int) -> None:
        conn = get_current_connection()
        await conn.execute(
            "UPDATE outbox SET retry_count = retry_count + 1 WHERE id = $1",
            outbox_id
        )

    @handle_db_errors
    async def mark_dead_letter(self, outbox_id: int) -> None:
        conn = get_current_connection()
        await conn.execute(
            "UPDATE outbox SET status = 'dead_letter' WHERE id = $1",
            outbox_id
        )
