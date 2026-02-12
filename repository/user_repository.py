import asyncpg

from database.context import get_current_connection
from entity.user import User
from exception.decorators import handle_db_errors
from exception.domain import AlreadyExistsError


class UserRepository:

    @handle_db_errors
    async def get_by_id(self, user_id: str) -> User | None:
        conn = get_current_connection()
        record = await conn.fetchrow(
            "SELECT * FROM users WHERE id = $1", user_id
        )
        return User.from_record(record) if record else None

    @handle_db_errors
    async def get_by_email(self, email: str) -> User | None:
        conn = get_current_connection()
        record = await conn.fetchrow(
            "SELECT * FROM users WHERE email = $1", email
        )
        return User.from_record(record) if record else None

    @handle_db_errors
    async def create(self, email: str, name: str) -> User:
        try:
            conn = get_current_connection()
            record = await conn.fetchrow(
                """INSERT INTO users (email, name)
                   VALUES ($1, $2)
                   RETURNING *""",
                email, name
            )
            return User.from_record(record)
        except asyncpg.UniqueViolationError:
            raise AlreadyExistsError("User with this email already exists")
