from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from shared.infrastructure.database.context import get_current_session
from shared.infrastructure.exception.decorators import handle_db_errors
from shared.domain.exception.domain import AlreadyExistsError
from user.domain.entity.user import User
from user.infrastructure.model.user_model import UserModel


class SqlAlchemyUserRepository:

    @handle_db_errors
    async def get_by_id(self, user_id: str) -> User | None:
        session = get_current_session()
        result = await session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        model = result.scalars().first()
        return model.to_entity() if model else None

    @handle_db_errors
    async def get_by_email(self, email: str) -> User | None:
        session = get_current_session()
        result = await session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        model = result.scalars().first()
        return model.to_entity() if model else None

    @handle_db_errors
    async def create(self, email: str, name: str) -> User:
        try:
            session = get_current_session()
            model = UserModel(email=email, name=name)
            session.add(model)
            await session.flush()
            return model.to_entity()
        except IntegrityError:
            raise AlreadyExistsError("User with this email already exists")
