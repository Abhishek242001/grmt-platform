from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_request_id
from app.core.logging_utils import log
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.models.core import User
from app.schemas.auth import LoginRequest, RefreshRequest, SignupRequest, SignupResponse, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, request: Request, db: Session = Depends(get_db)):
    req_id = get_request_id(request)
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        log.warn(req_id, f"signup rejected: email already registered ({payload.email})")
        raise HTTPException(status_code=422, detail={"error": {"code": "EMAIL_TAKEN", "message": "Email already registered", "field": "email"}})

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        name=payload.name,
        affiliation=payload.affiliation,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log.info(req_id, f"user created id={user.id} role={user.role}")
    return SignupResponse(id=user.id, email=user.email, role=user.role, email_verified=False)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    req_id = get_request_id(request)
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        log.warn(req_id, f"login failed for email={payload.email}")
        raise HTTPException(status_code=401, detail={"error": {"code": "INVALID_CREDENTIALS", "message": "Invalid email or password"}})

    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token(user.id)
    log.info(req_id, f"login success user_id={user.id}")
    return TokenResponse(access_token=access, refresh_token=refresh, expires_in=settings.access_token_expire_minutes * 60)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    req_id = get_request_id(request)
    try:
        decoded = decode_token(payload.refresh_token)
    except JWTError:
        raise HTTPException(status_code=401, detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid or expired refresh token"}})
    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=401, detail={"error": {"code": "INVALID_TOKEN", "message": "Not a refresh token"}})

    user = db.query(User).filter(User.id == decoded["sub"]).first()
    if user is None:
        raise HTTPException(status_code=401, detail={"error": {"code": "INVALID_TOKEN", "message": "User not found"}})

    access = create_access_token(user.id, user.role)
    new_refresh = create_refresh_token(user.id)
    log.info(req_id, f"token refreshed user_id={user.id}")
    return TokenResponse(access_token=access, refresh_token=new_refresh, expires_in=settings.access_token_expire_minutes * 60)
