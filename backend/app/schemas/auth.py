from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: str = Field(pattern="^(researcher|organizer)$")  # reviewer/platform_admin are invite-only, master doc §1.2/§1.10
    name: str
    affiliation: str | None = None


class SignupResponse(BaseModel):
    id: str
    email: str
    role: str
    email_verified: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str
