from pydantic import BaseModel


class RegisterUserRequest(BaseModel):
    email: str
    name: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
