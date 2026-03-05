from typing import Protocol


class PaymentRepositoryPort(Protocol):
    async def create(
        self, loan_id: str, amount: float, provider_reference: str, provider_name: str,
    ) -> object: ...
