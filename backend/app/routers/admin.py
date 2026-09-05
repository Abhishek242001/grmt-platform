"""Admin-only endpoints (update44): external plagiarism-provider API key
management (GPTZero, Winston) and per-provider usage statistics. Every
endpoint here is gated to role == "platform_admin" via require_role,
matching this project's existing authorization pattern."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.key_encryption import encrypt_api_key, mask_api_key
from app.models.admin import PLAGIARISM_PROVIDERS, ApiProviderConfig, ApiUsageLog
from app.models.core import User
from app.schemas.admin import ApiKeySetRequest, ApiProviderStatus, ApiUsageSummary

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _list_api_providers(db: Session) -> list[ApiProviderStatus]:
    existing = {c.provider: c for c in db.query(ApiProviderConfig).all()}
    result = []
    for provider in PLAGIARISM_PROVIDERS:
        config = existing.get(provider)
        if config is None:
            result.append(ApiProviderStatus(provider=provider, is_configured=False, is_active=False, masked_key=None))
        else:
            result.append(
                ApiProviderStatus(
                    provider=provider,
                    is_configured=config.encrypted_key is not None,
                    is_active=config.is_active,
                    masked_key=None,  # masked key requires decrypting — only computed on the set-key response, not every list call
                )
            )
    return result


@router.get("/api-keys", response_model=list[ApiProviderStatus])
def list_api_providers(db: Session = Depends(get_db), _: User = Depends(require_role("platform_admin"))):
    """Returns every known provider (even ones never configured yet — a row
    is synthesized for display, not persisted, so the admin panel always
    shows GPTZero and Winston as options regardless of whether either has
    been set up)."""
    return _list_api_providers(db)


@router.put("/api-keys/{provider}", response_model=ApiProviderStatus)
def set_api_key(
    provider: str,
    payload: ApiKeySetRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("platform_admin")),
):
    if provider not in PLAGIARISM_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown provider: {provider!r}")

    config = db.query(ApiProviderConfig).filter(ApiProviderConfig.provider == provider).first()
    if config is None:
        config = ApiProviderConfig(provider=provider)
        db.add(config)

    config.encrypted_key = encrypt_api_key(payload.key)
    config.updated_by_user_id = admin.id
    db.commit()
    db.refresh(config)

    return ApiProviderStatus(
        provider=provider, is_configured=True, is_active=config.is_active, masked_key=mask_api_key(payload.key)
    )


@router.post("/api-keys/{provider}/activate", response_model=list[ApiProviderStatus])
def activate_provider(
    provider: str, db: Session = Depends(get_db), _: User = Depends(require_role("platform_admin"))
):
    """Marks exactly one provider active, deactivating every other one in
    the same transaction — enforces "only one provider used at a time" at
    the application layer (see app/models/admin.py's docstring for why not
    a DB constraint)."""
    if provider not in PLAGIARISM_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown provider: {provider!r}")

    target = db.query(ApiProviderConfig).filter(ApiProviderConfig.provider == provider).first()
    if target is None or target.encrypted_key is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot activate {provider!r} — no API key has been configured for it yet",
        )

    all_configs = db.query(ApiProviderConfig).all()
    for c in all_configs:
        c.is_active = c.provider == provider
    db.commit()

    return _list_api_providers(db)


@router.get("/api-usage", response_model=ApiUsageSummary)
def get_api_usage(db: Session = Depends(get_db), _: User = Depends(require_role("platform_admin"))):
    """Total requests per provider, plus a per-hour breakdown for the last
    24 hours — enough for the admin dashboard's usage chart without
    building a general-purpose analytics endpoint this project doesn't
    otherwise need."""
    totals = {}
    for provider in PLAGIARISM_PROVIDERS:
        total = db.query(ApiUsageLog).filter(ApiUsageLog.provider == provider).count()
        succeeded = (
            db.query(ApiUsageLog).filter(ApiUsageLog.provider == provider, ApiUsageLog.success == True).count()  # noqa: E712
        )
        totals[provider] = {"total_requests": total, "successful_requests": succeeded}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_logs = (
        db.query(ApiUsageLog)
        .filter(ApiUsageLog.created_at >= cutoff)
        .order_by(ApiUsageLog.created_at.asc())
        .all()
    )

    hourly: dict[str, dict[str, int]] = {}
    for log in recent_logs:
        hour_key = log.created_at.strftime("%Y-%m-%dT%H:00")
        hourly.setdefault(hour_key, {p: 0 for p in PLAGIARISM_PROVIDERS})
        hourly[hour_key][log.provider] = hourly[hour_key].get(log.provider, 0) + 1

    return ApiUsageSummary(
        totals_by_provider=totals,
        hourly_breakdown=[{"hour": hour, **counts} for hour, counts in sorted(hourly.items())],
    )
