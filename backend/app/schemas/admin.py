from pydantic import BaseModel, Field


class ApiKeySetRequest(BaseModel):
    key: str = Field(min_length=1, max_length=512)


class ApiProviderStatus(BaseModel):
    provider: str
    is_configured: bool
    is_active: bool
    masked_key: str | None = None


class ApiUsageSummary(BaseModel):
    totals_by_provider: dict[str, dict[str, int]]
    hourly_breakdown: list[dict]
