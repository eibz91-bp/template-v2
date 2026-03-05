from typing import Protocol


class UserRepositoryPort(Protocol):
    async def get_by_id(self, user_id: str) -> object | None: ...
