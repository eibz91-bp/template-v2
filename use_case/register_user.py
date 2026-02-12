from database.transaction import transactional
from exception.domain import AlreadyExistsError
from port.user_repository_port import UserRepositoryPort


class RegisterUser:
    def __init__(self, user_repo: UserRepositoryPort):
        self.user_repo = user_repo

    @transactional
    async def execute(self, email: str, name: str):
        existing = await self.user_repo.get_by_email(email)
        self.ensure_not_exists(existing)
        return await self.user_repo.create(email, name)

    def ensure_not_exists(self, user):
        if user:
            raise AlreadyExistsError("User with this email already exists")
