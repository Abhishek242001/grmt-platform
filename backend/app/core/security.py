"""
Password hashing (Argon2id) and JWT (RS256) per development_rule.md §6.3.

RS256 is asymmetric: only the private key signs, and any service (including
future microservices) can verify with just the public key, without holding a
shared secret. Keys are loaded from files at the paths in Settings; if those
files don't exist (e.g. a fresh clone before `python scripts/generate_keys.py`
has been run), an ephemeral in-memory keypair is generated instead so that
`pytest` and local dev work immediately — this fallback is logged loudly and
must never be relied on in a real deployment, since tokens signed with an
ephemeral key become invalid on every process restart.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()
_hasher = PasswordHasher()


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(plain_password: str) -> str:
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, plain_password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# RS256 key loading (with ephemeral dev fallback — see module docstring)
# ---------------------------------------------------------------------------

def _generate_ephemeral_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def _load_keys():
    priv_path = Path(settings.jwt_private_key_path)
    pub_path = Path(settings.jwt_public_key_path)
    if priv_path.exists() and pub_path.exists():
        return priv_path.read_bytes(), pub_path.read_bytes()
    # Ephemeral fallback for a fresh clone / CI / pytest — see docstring.
    print(
        "[SECURITY WARNING] JWT keys not found at configured paths — using an "
        "ephemeral in-memory keypair. Tokens will not survive a process restart. "
        "Run `python backend/scripts/generate_keys.py` and set the paths in .env "
        "before deploying anywhere real. (development_rule.md §6.3)"
    )
    return _generate_ephemeral_keypair()


_PRIVATE_KEY, _PUBLIC_KEY = _load_keys()


# ---------------------------------------------------------------------------
# JWT issuance / verification
# ---------------------------------------------------------------------------

def create_access_token(user_id: str, role: str, expires_minutes: int | None = None) -> str:
    expires_minutes = expires_minutes or settings.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _PRIVATE_KEY, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(minutes=settings.refresh_token_expire_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _PRIVATE_KEY, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Raises jose.JWTError on invalid/expired token — callers catch this."""
    return jwt.decode(token, _PUBLIC_KEY, algorithms=[settings.jwt_algorithm])
