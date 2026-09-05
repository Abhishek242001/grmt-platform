from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core import security
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.logging_utils import get_logger
from app.models.core import User
from app.schemas.auth import (
    AdminLoginRequest,
    AdminTokenResponse,
    AdminUserOut,
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = get_logger("grmt.auth")


def _issue_tokens(user: User) -> TokenResponse:
    access = security.create_access_token(subject=user.id, role=user.role)
    refresh = security.create_refresh_token(subject=user.id)
    return TokenResponse(access_token=access, refresh_token=refresh, user=UserOut.model_validate(user))


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")

    user = User(
        email=payload.email.lower(),
        password_hash=security.hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("signup: new user id=%s role=%s", user.id, user.role)  # never log email/password
    return _issue_tokens(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()

    # Same status/message whether the email doesn't exist or the password is
    # wrong — distinguishing the two turns this endpoint into a user-enumeration oracle.
    if not user or not security.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated")

    logger.info("login: user id=%s", user.id)
    return _issue_tokens(user)


@router.post("/admin-login", response_model=AdminTokenResponse)
def admin_login(payload: AdminLoginRequest, db: Session = Depends(get_db)):
    """Separate from /login end to end (see schemas/auth.py's AdminLoginRequest
    docstring for why) — the admin identifier is a username, not a real email,
    so this never touches EmailStr validation on the way in or out.

    Same not-a-user-enumeration-oracle principle as the researcher/organizer/
    reviewer login above, extended one step further: this endpoint refuses
    to authenticate ANY non-platform_admin account, correct password or not
    — a researcher who happens to guess this endpoint's existence and their
    own correct credentials still gets "Invalid credentials", not a
    confirmation that this is in fact a real login path that just isn't for
    them. Checked AFTER password verification (not before), so response
    timing doesn't leak whether the failure was password or role."""
    user = db.query(User).filter(User.email == payload.username.lower()).first()

    if not user or not security.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if user.role != "platform_admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated")

    logger.info("admin_login: user id=%s", user.id)
    access = security.create_access_token(subject=user.id, role=user.role)
    refresh = security.create_refresh_token(subject=user.id)
    return AdminTokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=AdminUserOut(id=user.id, username=user.email, full_name=user.full_name, role=user.role),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        decoded = security.decode_token(payload.refresh_token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user = db.query(User).filter(User.id == decoded.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer valid")

    return _issue_tokens(user)


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)
