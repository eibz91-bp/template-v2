from shared.infrastructure.database.transaction import transaction_context
from shared.domain.exception.domain import AlreadyProcessedError, EntityNotFoundError
from loan.domain.port.loan_repository_port import LoanRepositoryPort


class DisburseLoan:
    def __init__(self, loan_repo: LoanRepositoryPort, factory):
        self.loan_repo = loan_repo
        self.factory = factory

    async def execute(self, loan_id: str, provider_name: str):
        loan = await self.loan_repo.get_by_id(loan_id)
        self.ensure_exists(loan, "Loan not found")
        loan.ensure_can_disburse()

        # Transaction 1: mark as disbursing (idempotent from approved)
        async with transaction_context() as tx:
            updated = await self.loan_repo.update_status_if(loan_id, "approved", "disbursing")
            self.ensure_was_updated(updated)
            await tx.commit()

        # Call disburse provider (outside transaction)
        provider = self.factory.get(provider_name)
        result = await provider.execute(loan)

        # Transaction 2: mark disbursed
        async with transaction_context() as tx:
            await self.loan_repo.update_status(loan_id, "disbursed")
            await tx.commit()

        return result

    def ensure_exists(self, entity, message: str):
        if not entity:
            raise EntityNotFoundError(message)

    def ensure_was_updated(self, result):
        if not result:
            raise AlreadyProcessedError("Loan already being disbursed")
