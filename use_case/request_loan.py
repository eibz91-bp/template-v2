from database.transaction import transactional
from exception.domain import EntityNotFoundError
from port.user_repository_port import UserRepositoryPort
from port.loan_repository_port import LoanRepositoryPort


class RequestLoan:
    def __init__(self, user_repo: UserRepositoryPort, loan_repo: LoanRepositoryPort):
        self.user_repo = user_repo
        self.loan_repo = loan_repo

    @transactional
    async def execute(self, user_id: str, amount: float):
        user = await self.user_repo.get_by_id(user_id)
        self.ensure_exists(user, "User not found")
        return await self.loan_repo.create(user_id, amount)

    def ensure_exists(self, entity, message: str):
        if not entity:
            raise EntityNotFoundError(message)
