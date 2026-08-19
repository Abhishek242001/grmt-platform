"""
File storage — local-disk stand-in for Supabase Storage / Cloudflare R2.

Master doc §2.2.5 specifies Supabase Storage or Cloudflare R2 for production.
This module implements the SAME access pattern (short-lived signed URLs,
never a direct downloadable link — development_rule.md §6.4) on local disk,
so the app is correctly shaped now and swapping in real cloud storage later
is a small, isolated change (replace save_file/read_file's bodies; the
signed-URL contract used by the rest of the app does not change).

Do NOT use this in any real deployment — local disk has none of R2/Supabase's
durability, encryption-at-rest, or multi-instance access. It is a deliberate,
documented placeholder for local/dev use only (see development_rule.md §6.2
on at-rest encryption still being owed before production).
"""
import hashlib
import hmac
import time
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()

UPLOAD_ROOT = Path(settings.upload_dir)


def _signing_key() -> bytes:
    # Reuses STORAGE_ENCRYPTION_KEY as the HMAC signing key for the URL
    # tokens below. This is a placeholder key in .env.example — see
    # development_rule.md §6.3 on rotating it before anything beyond local
    # dev, same caveat as the rest of this module.
    return settings.storage_encryption_key.encode("utf-8")


def save_file(submission_id: str, version_number: int, filename: str, content: bytes) -> tuple[str, str]:
    """
    Writes the file to local disk under a path namespaced by submission +
    version, mirroring the object-key shape a real bucket would use
    (submissions/{submission_id}/v{version_number}/{filename}).

    Returns (storage_key, file_hash) — storage_key is what gets saved into
    submission_versions.file_url (replacing the old placeholder:// value);
    file_hash is the sha256 hex digest, same as before this change.
    """
    file_hash = hashlib.sha256(content).hexdigest()
    safe_filename = Path(filename).name  # strip any path components — never trust client-supplied paths
    rel_dir = Path("submissions") / submission_id / f"v{version_number}"
    abs_dir = UPLOAD_ROOT / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    abs_path = abs_dir / safe_filename
    abs_path.write_bytes(content)

    storage_key = str(rel_dir / safe_filename)
    return storage_key, file_hash


def read_file(storage_key: str) -> bytes:
    """Reads a file back by its storage_key (as stored in submission_versions.file_url)."""
    abs_path = (UPLOAD_ROOT / storage_key).resolve()
    _guard_within_upload_root(abs_path)
    return abs_path.read_bytes()


def generate_signed_url_token(storage_key: str, ttl_seconds: int | None = None) -> tuple[str, int]:
    """
    Generates an HMAC-signed, time-limited token for one file — the local-disk
    equivalent of a Supabase/R2 signed URL (development_rule.md §6.4: never a
    direct downloadable file URL, always a short-lived signed one).

    Returns (token, expires_at_unix). The token encodes storage_key + expiry
    + an HMAC-SHA256 signature; app/routers/files.py verifies it on each
    request rather than trusting the client-supplied storage_key directly.
    """
    ttl = ttl_seconds if ttl_seconds is not None else settings.pdf_signed_url_ttl_seconds
    expires_at = int(time.time()) + ttl
    payload = f"{storage_key}:{expires_at}"
    signature = hmac.new(_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    token = f"{expires_at}.{signature}.{storage_key}"
    return token, expires_at


class InvalidSignedUrlError(ValueError):
    """Raised when a file token is missing, malformed, expired, or has a bad signature."""


def verify_signed_url_token(token: str) -> str:
    """
    Verifies a token produced by generate_signed_url_token(). Returns the
    storage_key on success; raises InvalidSignedUrlError otherwise (expired,
    tampered, or malformed) — app/routers/files.py turns this into a 403/410.
    """
    try:
        expires_at_str, signature, storage_key = token.split(".", 2)
        expires_at = int(expires_at_str)
    except (ValueError, AttributeError):
        raise InvalidSignedUrlError("Malformed file token")

    if time.time() > expires_at:
        raise InvalidSignedUrlError("File token has expired — request a new one")

    payload = f"{storage_key}:{expires_at}"
    expected_signature = hmac.new(_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise InvalidSignedUrlError("File token signature is invalid")

    return storage_key


def _guard_within_upload_root(abs_path: Path) -> None:
    """Defense-in-depth against path traversal — every resolved read must stay inside UPLOAD_ROOT."""
    try:
        abs_path.relative_to(UPLOAD_ROOT.resolve())
    except ValueError:
        raise InvalidSignedUrlError("Resolved path escapes the upload root")
