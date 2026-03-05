from dataclasses import asdict

from user.infrastructure.http.schema.user_schema import RegisterUserRequest, UserResponse


class UserController:
    def __init__(self, register_user):
        self.register_user = register_user

    async def register(self, request: RegisterUserRequest):
        user = await self.register_user.execute(request.email, request.name)
        return UserResponse(**asdict(user))
