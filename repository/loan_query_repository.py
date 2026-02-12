from database.context import get_current_connection
from exception.decorators import handle_db_errors


class LoanQueryRepository:

    @handle_db_errors
    async def get_with_user(self, loan_id: str) -> dict | None:
        conn = get_current_connection()
        record = await conn.fetchrow(
            """SELECT l.id, l.amount, l.status, l.score, l.created_at,
                      u.name as user_name, u.email as user_email
               FROM loans l
               JOIN users u ON l.user_id = u.id
               WHERE l.id = $1""",
            loan_id
        )
        return dict(record) if record else None

    @handle_db_errors
    async def get_by_user(self, user_id: str) -> list[dict]:
        conn = get_current_connection()
        records = await conn.fetch(
            """SELECT l.id, l.amount, l.status, l.score, l.created_at
               FROM loans l
               WHERE l.user_id = $1
               ORDER BY l.created_at DESC""",
            user_id
        )
        return [dict(r) for r in records]
