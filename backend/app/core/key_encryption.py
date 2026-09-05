"""Encrypts external-provider API keys (GPTZero, Winston) at rest, on top of
the admin-only access control already enforced at the router level (update44)
— matches this project's existing security posture (Argon2id password
hashing, RS256 JWT, secrets/*.pem gitignored) rather than relying on access
control alone for genuinely sensitive credentials.

Uses Fernet (symmetric, authenticated encryption) from the `cryptography`
package, already a project dependency (used for the JWT RSA keypair)."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _derive_fernet_key() -> bytes:
    """Fernet requires a 32-byte urlsafe-base64 key specifically — derives
    one deterministically from settings.api_key_encryption_secret (a
    dedicated setting, separate from JWT/file-signing secrets — same
    independent-rotation reasoning already used elsewhere in this project)
    via SHA-256, rather than requiring Fernet's own key format to be hand-
    generated and stored separately. Deterministic on purpose: the same
    secret must always derive the same encryption key, or every previously-
    encrypted API key in the database would become permanently undecryptable
    the moment the app restarts with a "freshly re-derived" key."""
    digest = hashlib.sha256(settings.api_key_encryption_secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_derive_fernet_key())


def encrypt_api_key(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        # Genuinely shouldn't happen unless settings.secret_key changed
        # since the key was encrypted, or the stored value was corrupted —
        # surfacing this clearly rather than returning a garbled string
        # that would then fail mysteriously against the provider's real API.
        raise ValueError("Could not decrypt stored API key — secret_key may have changed since it was saved") from e


def mask_api_key(plaintext: str) -> str:
    """For admin-panel display only — never return a decrypted key in full
    over the API. Shows just enough to let an admin visually confirm which
    key is configured without exposing it."""
    if len(plaintext) <= 4:
        return "*" * len(plaintext)
    return "*" * (len(plaintext) - 4) + plaintext[-4:]
