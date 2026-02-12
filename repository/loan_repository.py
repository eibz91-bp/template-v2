from database.context import get_current_connection
from entity.loan import Loan
from exception.decorators import handle_db_errors


class LoanRepository:

    @handle_db_errors
    async def get_by_id(self, loan_id: str) -> Loan | None:
        conn = get_current_connection()
        record = await conn.fetchrow(
            "SELECT * FROM loans WHERE id = $1", loan_id
        )
        return Loan.from_record(record) if record else None

    @handle_db_errors
    async def create(self, user_id: str, amount: float) -> Loan:
        conn = get_current_connection()
        record = await conn.fetchrow(
            """INSERT INTO loans (user_id, amount, status)
               VALUES ($1, $2, 'pending')
               RETURNING *""",
            user_id, amount
        )
        return Loan.from_record(record)

    @handle_db_errors
    async def update_status_if(self, loan_id: str, from_status: str, to_status: str) -> Loan | None:
        conn = get_current_connection()
        record = await conn.fetchrow(
            """UPDATE loans SET status = $1
               WHERE id = $2 AND status = $3
               RETURNING *""",
            to_status, loan_id, from_status
        )
        return Loan.from_record(record) if record else None

    @handle_db_errors
    async def update_status(self, loan_id: str, status: str) -> None:
        conn = get_current_connection()
        await conn.execute(
            "UPDATE loans SET status = $1 WHERE id = $2",
            status, loan_id
        )

    @handle_db_errors
    async def save_evaluation(self, loan_id: str, score: int, status: str) -> Loan | None:
        conn = get_current_connection()
        record = await conn.fetchrow(
            """UPDATE loans SET score = $1, status = $2
               WHERE id = $3 AND status = 'scoring'
               RETURNING *""",
            score, status, loan_id
        )
        return Loan.from_record(record) if record else None
