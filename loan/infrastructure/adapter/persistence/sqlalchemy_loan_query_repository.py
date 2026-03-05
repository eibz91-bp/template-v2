from sqlalchemy import select

from shared.infrastructure.database.context import get_current_session
from shared.infrastructure.exception.decorators import handle_db_errors
from loan.infrastructure.model.loan_model import LoanModel
from user.infrastructure.model.user_model import UserModel


class SqlAlchemyLoanQueryRepository:

    @handle_db_errors
    async def get_with_user(self, loan_id: str) -> dict | None:
        session = get_current_session()
        result = await session.execute(
            select(
                LoanModel.id,
                LoanModel.amount,
                LoanModel.status,
                LoanModel.score,
                LoanModel.created_at,
                UserModel.name.label("user_name"),
                UserModel.email.label("user_email"),
            )
            .join(UserModel, LoanModel.user_id == UserModel.id)
            .where(LoanModel.id == loan_id)
        )
        row = result.first()
        if not row:
            return None
        return {
            "id": row.id,
            "amount": row.amount,
            "status": row.status,
            "score": row.score,
            "created_at": row.created_at,
            "user_name": row.user_name,
            "user_email": row.user_email,
        }

    @handle_db_errors
    async def get_by_user(self, user_id: str) -> list[dict]:
        session = get_current_session()
        result = await session.execute(
            select(
                LoanModel.id,
                LoanModel.amount,
                LoanModel.status,
                LoanModel.score,
                LoanModel.created_at,
            )
            .where(LoanModel.user_id == user_id)
            .order_by(LoanModel.created_at.desc())
        )
        return [
            {
                "id": row.id,
                "amount": row.amount,
                "status": row.status,
                "score": row.score,
                "created_at": row.created_at,
            }
            for row in result.all()
        ]
