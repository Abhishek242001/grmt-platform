from typing import Optional
from pydantic import BaseModel, Field, field_validator
from app.models.conferences import CHECK_TYPES, NEVER_HARD_GATE

PUBLISHER_FORMATS = {"ieee", "springer"}


class ConferenceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    publisher_format: str = Field(default="ieee")

    @field_validator("publisher_format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        if v not in PUBLISHER_FORMATS:
            raise ValueError(f"publisher_format must be one of {sorted(PUBLISHER_FORMATS)}")
        return v


class ConferenceOut(BaseModel):
    id: str
    organizer_id: str
    name: str
    description: Optional[str]
    publisher_format: str

    class Config:
        from_attributes = True


class GateRuleIn(BaseModel):
    check_type: str
    is_hard_gate: bool
    threshold: Optional[float] = None

    @field_validator("check_type")
    @classmethod
    def validate_check_type(cls, v: str) -> str:
        if v not in CHECK_TYPES:
            raise ValueError(f"check_type must be one of {CHECK_TYPES}")
        return v

    @field_validator("is_hard_gate")
    @classmethod
    def validate_never_hard_gate(cls, v: bool, info) -> bool:
        # API-layer enforcement of the product's non-negotiable rule — the DB CHECK
        # constraint is the second, independent line of defense, not the only one.
        check_type = info.data.get("check_type")
        if v and check_type in NEVER_HARD_GATE:
            raise ValueError(f"'{check_type}' can never be a hard gate — soft flag only")
        return v


class GateRuleOut(BaseModel):
    check_type: str
    is_hard_gate: bool
    threshold: Optional[float]

    class Config:
        from_attributes = True


class ConferenceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    publisher_format: Optional[str] = None

    @field_validator("publisher_format")
    @classmethod
    def validate_format(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in PUBLISHER_FORMATS:
            raise ValueError(f"publisher_format must be one of {sorted(PUBLISHER_FORMATS)}")
        return v


class MemberInvite(BaseModel):
    email: str


class CoAdminOut(BaseModel):
    id: str
    user_id: str
    email: str
    full_name: str

    class Config:
        from_attributes = True


class ReviewerOut(BaseModel):
    id: str
    reviewer_id: str
    email: str
    full_name: str

    class Config:
        from_attributes = True
