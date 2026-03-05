from shared.infrastructure.database.transaction import transaction_context
from shared.domain.exception.domain import AlreadyExistsError
from user.domain.port.user_repository_port import UserRepositoryPort


class RegisterUser:
    def __init__(self, user_repo: UserRepositoryPort):
        self.user_repo = user_repo

    async def execute(self, email: str, name: str):
        async with transaction_context() as tx:
            existing = await self.user_repo.get_by_email(email)
            self.ensure_not_exists(existing)
            result = await self.user_repo.create(email, name)
            await tx.commit()
        return result

    def ensure_not_exists(self, user):
        if user:
            raise AlreadyExistsError("User with this email already exists")
