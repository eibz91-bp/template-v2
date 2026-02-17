from database.transaction import transaction_context
from entity.loan import Loan
from exception.domain import EntityNotFoundError
from port.loan_repository_port import LoanRepositoryPort
from port.payment_repository_port import PaymentRepositoryPort


class PayLoan:
    def __init__(
        self,
        loan_repo: LoanRepositoryPort,
        payment_repo: PaymentRepositoryPort,
    ) -> None:
        self.loan_repo = loan_repo
        self.payment_repo = payment_repo

    async def execute(
        self,
        loan_id: str,
        amount: float,
        provider_reference: str,
        provider_name: str,
    ) -> Loan:
        loan = await self.loan_repo.get_by_id(loan_id)
        if not loan:
            raise EntityNotFoundError("Loan not found")

        loan.ensure_can_pay()
        new_status = loan.apply_payment(amount)

        async with transaction_context() as tx:
            await self.payment_repo.create(
                loan_id, amount, provider_reference, provider_name,
            )
            updated = await self.loan_repo.apply_payment(
                loan_id, amount, new_status,
            )
            await tx.commit()

        return updated  # type: ignore[return-value]
