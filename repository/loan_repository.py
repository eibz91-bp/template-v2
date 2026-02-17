from sqlalchemy import select, update

from database.context import get_current_session
from entity.loan import Loan
from exception.decorators import handle_db_errors
from model.loan_model import LoanModel


class LoanRepository:

    @handle_db_errors
    async def get_by_id(self, loan_id: str) -> Loan | None:
        session = get_current_session()
        result = await session.execute(
            select(LoanModel).where(LoanModel.id == loan_id)
        )
        model = result.scalars().first()
        return model.to_entity() if model else None

    @handle_db_errors
    async def create(self, user_id: str, amount: float) -> Loan:
        session = get_current_session()
        model = LoanModel(user_id=user_id, amount=amount, status="pending")
        session.add(model)
        await session.flush()
        return model.to_entity()

    @handle_db_errors
    async def update_status_if(
        self, loan_id: str, from_status: str, to_status: str,
    ) -> Loan | None:
        session = get_current_session()
        result = await session.execute(
            update(LoanModel)
            .where(LoanModel.id == loan_id, LoanModel.status == from_status)
            .values(status=to_status)
            .returning(LoanModel)
        )
        model = result.scalars().first()
        return model.to_entity() if model else None

    @handle_db_errors
    async def update_status(self, loan_id: str, status: str) -> None:
        session = get_current_session()
        await session.execute(
            update(LoanModel)
            .where(LoanModel.id == loan_id)
            .values(status=status)
        )
        await session.flush()

    @handle_db_errors
    async def save_evaluation(
        self, loan_id: str, score: int, status: str,
    ) -> Loan | None:
        session = get_current_session()
        result = await session.execute(
            update(LoanModel)
            .where(LoanModel.id == loan_id, LoanModel.status == "scoring")
            .values(score=score, status=status)
            .returning(LoanModel)
        )
        model = result.scalars().first()
        return model.to_entity() if model else None

    @handle_db_errors
    async def apply_payment(
        self, loan_id: str, amount: float, new_status: str,
    ) -> Loan | None:
        session = get_current_session()
        result = await session.execute(
            update(LoanModel)
            .where(LoanModel.id == loan_id)
            .values(
                amount_paid=LoanModel.amount_paid + amount,
                status=new_status,
            )
            .returning(LoanModel)
        )
        model = result.scalars().first()
        await session.flush()
        return model.to_entity() if model else None
