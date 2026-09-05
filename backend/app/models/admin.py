"""Admin panel data models (update44) — external plagiarism-provider API key
storage and per-request usage logging.

Two providers only, matching the project's actual scope decision: GPTZero
(free tier now, upgradeable later) and Winston AI (2,500 free credits,
plagiarism-detection endpoint only — 2 credits/word — never its AI-text-
detection or image-detection endpoints, which are explicitly out of scope;
image detection is a noted future-scope item, see PROJECT_HANDOFF.md).

Only one provider is ever "active" at a time — enforced at the application
layer in admin.py's activate endpoint (deactivating every other provider in
the same transaction), not by a DB constraint, since SQLite's partial-unique-
index support is inconsistent across versions and the enforcement logic is
simple enough to be trustworthy at the application layer for this scale."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, String, Text

from app.core.database import Base

PLAGIARISM_PROVIDERS = ("gptzero", "winston")
_PROVIDER_LIST_SQL = ", ".join(f"'{p}'" for p in PLAGIARISM_PROVIDERS)


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ApiProviderConfig(Base):
    """One row per provider (gptzero, winston) — the encrypted API key and
    whether this provider is the currently-active one. encrypted_key is
    Fernet-encrypted at rest (see app/core/key_encryption.py) — never stored
    or returned as plaintext, including in admin API responses (those only
    ever return a masked preview, e.g. the last 4 characters)."""

    __tablename__ = "api_provider_configs"
    __table_args__ = (
        CheckConstraint(f"provider IN ({_PROVIDER_LIST_SQL})", name="ck_api_provider_valid"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    provider = Column(String(32), nullable=False, unique=True)
    encrypted_key = Column(Text, nullable=True)  # nullable — a provider can exist as a row before a key is ever set
    is_active = Column(Boolean, nullable=False, default=False)
    updated_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class ApiUsageLog(Base):
    """One row per external-provider API call — the raw log that
    /api/admin/api-usage aggregates into per-provider, per-hour request
    counts. Deliberately NOT storing the request/response body — only
    enough to answer "how many calls, to which provider, succeeded or
    failed, when" without retaining submission content in a second place."""

    __tablename__ = "api_usage_logs"
    __table_args__ = (
        CheckConstraint(f"provider IN ({_PROVIDER_LIST_SQL})", name="ck_api_usage_provider_valid"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    provider = Column(String(32), nullable=False, index=True)
    purpose = Column(String(64), nullable=False, default="plagiarism_check")
    success = Column(Boolean, nullable=False)
    response_time_ms = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, index=True)
