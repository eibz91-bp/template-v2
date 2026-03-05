from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from shared.infrastructure.database.context import get_current_session
from shared.infrastructure.exception.decorators import handle_db_errors
from shared.domain.exception.domain import AlreadyProcessedError
from payment.domain.entity.payment import Payment
from payment.infrastructure.model.payment_model import PaymentModel


class SqlAlchemyPaymentRepository:

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
