from typing import Protocol

from payment.domain.entity.payment import Payment


class PaymentRepositoryPort(Protocol):
    async def get_by_provider_reference(self, ref: str) -> Payment | None: ...
    async def create(
        self, loan_id: str, amount: float, provider_reference: str, provider_name: str,
    ) -> Payment: ...
