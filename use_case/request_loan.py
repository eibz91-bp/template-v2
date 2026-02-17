from database.transaction import transaction_context
from exception.domain import EntityNotFoundError
from port.loan_repository_port import LoanRepositoryPort
from port.user_repository_port import UserRepositoryPort


class RequestLoan:
    def __init__(self, user_repo: UserRepositoryPort, loan_repo: LoanRepositoryPort):
        self.user_repo = user_repo
        self.loan_repo = loan_repo

    async def execute(self, user_id: str, amount: float):
        async with transaction_context() as tx:
            user = await self.user_repo.get_by_id(user_id)
            self.ensure_exists(user, "User not found")
            result = await self.loan_repo.create(user_id, amount)
            await tx.commit()
        return result

    def ensure_exists(self, entity, message: str):
        if not entity:
            raise EntityNotFoundError(message)
