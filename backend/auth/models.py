from pydantic import BaseModel, EmailStr


class SendCodeRequest(BaseModel):
    email: EmailStr


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str


class AuthResponse(BaseModel):
    access_token: str
    email: str
    is_new_user: bool


class CurrentUser(BaseModel):
    email: str
