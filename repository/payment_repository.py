from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database.context import get_current_session
from entity.payment import Payment
from exception.decorators import handle_db_errors
from exception.domain import AlreadyProcessedError
from model.payment_model import PaymentModel


class PaymentRepository:

    @handle_db_errors
    async def get_by_provider_reference(self, ref: str) -> Payment | None:
        session = get_current_session()
        result = await session.execute(
            select(PaymentModel).where(PaymentModel.provider_reference == ref)
        )
        model = result.scalars().first()
        return model.to_entity() if model else None

    @handle_db_errors
    async def create(
        self, loan_id: str, amount: float, provider_reference: str, provider_name: str,
    ) -> Payment:
        session = get_current_session()
        model = PaymentModel(
            loan_id=loan_id,
            amount=amount,
            provider_reference=provider_reference,
            provider_name=provider_name,
        )
        try:
            session.add(model)
            await session.flush()
        except IntegrityError:
            raise AlreadyProcessedError(
                f"Payment with reference '{provider_reference}' already processed"
            )
        return model.to_entity()
