import hashlib
import hmac
import time

from app.core.config import settings


def generate_signed_url(base_url: str) -> str:
    """Appends a time-limited HMAC signature to a file URL. Matches the security
    spec's 'short-lived signed streaming URLs only, never a direct downloadable
    link' requirement. Real storage-backed streaming isn't wired yet (base_url is
    currently a placeholder://... string) but the signing mechanism itself is real."""
    expires = int(time.time()) + settings.signed_url_expire_seconds
    payload = f"{base_url}:{expires}"
    signature = hmac.new(
        settings.file_signing_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}expires={expires}&signature={signature}"


def verify_signed_url(base_url: str, expires: int, signature: str) -> bool:
    if int(time.time()) > expires:
        return False
    payload = f"{base_url}:{expires}"
    expected = hmac.new(
        settings.file_signing_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
