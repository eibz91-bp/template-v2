from unittest.mock import AsyncMock

from entity.user import User
from controller.user_controller import UserController
from schema.user_schema import RegisterUserRequest


async def test_user_controller_register():
    mock_use_case = AsyncMock()
    mock_use_case.execute.return_value = User(
        id="u-1", email="test@example.com", name="Test User", created_at="2025-01-01"
    )

    controller = UserController(mock_use_case)
    response = await controller.register(
        RegisterUserRequest(email="test@example.com", name="Test User")
    )

    assert response.id == "u-1"
    assert response.email == "test@example.com"
