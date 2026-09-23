from pydantic import BaseModel, EmailStr, Field, field_validator


class SendCodeRequest(BaseModel):
    email: EmailStr

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value):
        return value.strip().casefold()


class VerifyCodeRequest(SendCodeRequest):
    code: str = Field(pattern=r'^\d{6}$')


class PasswordLogin(SendCodeRequest):
    password: str = Field(min_length=12, max_length=128)


class AccountCreate(PasswordLogin):
    display_name: str = Field(default='', max_length=100)


class AuthResponse(BaseModel):
    access_token: str
    email: str
    is_new_user: bool


class CurrentUser(BaseModel):
    email: str
    is_admin: bool = False
