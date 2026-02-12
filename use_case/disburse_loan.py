from database.transaction import transaction_context
from exception.domain import AlreadyProcessedError, EntityNotFoundError, InvalidOperationError
from port.loan_repository_port import LoanRepositoryPort
from port.outbox_repository_port import OutboxRepositoryPort


class DisburseLoan:
    def __init__(self, loan_repo: LoanRepositoryPort, factory, outbox_repo: OutboxRepositoryPort):
        self.loan_repo = loan_repo
        self.factory = factory
        self.outbox_repo = outbox_repo

    async def execute(self, loan_id: str, provider_name: str):
        loan = await self.loan_repo.get_by_id(loan_id)
        self.ensure_exists(loan, "Loan not found")
        self.ensure_approved(loan)

        # Transaction 1: mark as disbursing (idempotent from approved)
        async with transaction_context():
            updated = await self.loan_repo.update_status_if(loan_id, "approved", "disbursing")
            self.ensure_was_updated(updated)

        # Call disburse provider (outside transaction)
        provider = self.factory.get(provider_name)
        result = await provider.execute(loan)

        # Transaction 2: mark disbursed + notification to outbox
        async with transaction_context():
            await self.loan_repo.update_status(loan_id, "disbursed")
            await self.outbox_repo.save("notification", {
                "user_id": loan.user_id,
                "loan_id": loan.id,
                "status": "disbursed",
                "amount": loan.amount,
            })

        return result

    def ensure_exists(self, entity, message: str):
        if not entity:
            raise EntityNotFoundError(message)

    def ensure_approved(self, loan):
        if loan.status != "approved":
            raise InvalidOperationError(f"Loan status is '{loan.status}', expected 'approved'")

    def ensure_was_updated(self, result):
        if not result:
            raise AlreadyProcessedError("Loan already being disbursed")
