from datetime import date

from pydantic import BaseModel, ConfigDict


class ConferenceCreateRequest(BaseModel):
    name: str
    theme: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    tracks: list[str] | None = None
    publisher_format: str | None = None


class ConferenceResponse(BaseModel):
    id: str
    name: str
    theme: str | None
    start_date: date | None
    end_date: date | None
    publisher_format: str | None

    class Config:
        from_attributes = True


class GateRuleItem(BaseModel):
    rule_type: str
    threshold_soft: float | None = None
    threshold_hard: float | None = None
    is_hard_gate: bool = False


class GateRulesUpdateRequest(BaseModel):
    rules: list[GateRuleItem]
