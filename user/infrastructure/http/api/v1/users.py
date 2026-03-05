from fastapi import APIRouter, Depends

from user.infrastructure.http.controller.user_controller import UserController
from dependencies.providers import get_user_controller
from user.infrastructure.http.schema.user_schema import RegisterUserRequest

router = APIRouter()


@router.post("/users")
async def register_user_endpoint(
    body: RegisterUserRequest,
    ctrl: UserController = Depends(get_user_controller),
):
    return await ctrl.register(body)
