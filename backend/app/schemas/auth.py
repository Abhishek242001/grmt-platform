from pydantic import BaseModel, EmailStr, Field, field_validator

# platform_admin is deliberately NOT in this set — it must never be
# self-assignable at signup. Admin accounts are provisioned separately.
SELF_ASSIGNABLE_ROLES = {"researcher", "organizer", "reviewer"}


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    role: str = Field(default="researcher")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in SELF_ASSIGNABLE_ROLES:
            raise ValueError(f"role must be one of {sorted(SELF_ASSIGNABLE_ROLES)}")
        return v

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("password must contain at least one digit")
        if not any(c.isalpha() for c in v):
            raise ValueError("password must contain at least one letter")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# Admin login is deliberately separate from the above, end to end — the
# admin identifier is a plain username, not a real email address (matches
# how it was actually requested: "Admin@GRMT", which has no valid TLD and
# will never pass EmailStr). Reusing LoginRequest/UserOut here would also
# break on the RESPONSE side, not just the request: UserOut.email is
# EmailStr too, so even a successful login would fail at serialization
# time trying to force a non-email string through it.
class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str


class AdminUserOut(BaseModel):
    id: str
    username: str
    full_name: str
    role: str


class AdminTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: AdminUserOut


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    is_email_verified: bool

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut
