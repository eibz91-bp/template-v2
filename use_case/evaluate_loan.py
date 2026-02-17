from database.transaction import transaction_context
from exception.domain import AlreadyProcessedError, EntityNotFoundError
from port.loan_repository_port import LoanRepositoryPort
from port.score_provider_port import ScoreProviderPort


class EvaluateLoan:
    def __init__(self, loan_repo: LoanRepositoryPort, score_provider: ScoreProviderPort, min_score: int):
        self.loan_repo = loan_repo
        self.score_provider = score_provider
        self.min_score = min_score

    async def execute(self, loan_id: str):
        loan = await self.loan_repo.get_by_id(loan_id)
        self.ensure_exists(loan, "Loan not found")
        loan.ensure_can_evaluate()

        # Transaction 1: mark as scoring (idempotent from pending)
        async with transaction_context() as tx:
            updated = await self.loan_repo.update_status_if(loan_id, "pending", "scoring")
            self.ensure_was_updated(updated)
            await tx.commit()

        # Call external scorer (outside transaction)
        score = await self.score_provider.get_score(loan)

        # Determine result based on threshold
        new_status = loan.determine_evaluation_status(score, self.min_score)

        # Transaction 2: save score + final status
        async with transaction_context() as tx:
            result = await self.loan_repo.save_evaluation(loan_id, score, new_status)
            await tx.commit()

        return result

    def ensure_exists(self, entity, message: str):
        if not entity:
            raise EntityNotFoundError(message)

    def ensure_was_updated(self, result):
        if not result:
            raise AlreadyProcessedError("Loan already being evaluated")
