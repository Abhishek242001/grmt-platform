import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import JWTError, jwt

from app.core.config import settings

logger = logging.getLogger("grmt.security")

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except VerifyMismatchError:
        return False


def _load_or_generate_keys() -> tuple[str, str]:
    priv_path = Path(settings.jwt_private_key_path)
    pub_path = Path(settings.jwt_public_key_path)

    if priv_path.exists() and pub_path.exists():
        return priv_path.read_text(), pub_path.read_text()

    # Defense-in-depth fallback so the app never hard-crashes on missing keys —
    # but this MUST NOT be relied on. lightning_configure.sh runs generate_keys.py
    # before first start specifically to avoid ever hitting this branch in practice.
    logger.warning(
        "[SECURITY WARNING] No persistent JWT keypair found at %s — generating an "
        "EPHEMERAL in-memory keypair for THIS PROCESS ONLY. Every token issued now "
        "will be invalid after the next restart. Run "
        "`python scripts/generate_keys.py` from backend/ to fix this.",
        priv_path,
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


_PRIVATE_KEY, _PUBLIC_KEY = _load_or_generate_keys()


def create_access_token(subject: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "role": role, "type": "access", "exp": expire}
    return jwt.encode(payload, _PRIVATE_KEY, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {"sub": subject, "type": "refresh", "exp": expire}
    return jwt.encode(payload, _PRIVATE_KEY, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _PUBLIC_KEY, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise ValueError("invalid or expired token") from e
