from exception.domain import EntityNotFoundError
from port.loan_query_repository_port import LoanQueryRepositoryPort


class GetLoanDetail:
    def __init__(self, loan_query_repo: LoanQueryRepositoryPort):
        self.loan_query_repo = loan_query_repo

    async def execute(self, loan_id: str):
        detail = await self.loan_query_repo.get_with_user(loan_id)
        self.ensure_exists(detail, "Loan not found")
        return detail

    def ensure_exists(self, entity, message: str):
        if not entity:
            raise EntityNotFoundError(message)
