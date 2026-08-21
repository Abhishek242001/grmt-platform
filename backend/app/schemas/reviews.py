from typing import Optional
from pydantic import BaseModel, Field, field_validator
from app.models.submissions import DECISIONS, REVIEW_RECOMMENDATIONS


class ReviewIn(BaseModel):
    recommendation: str
    comments: Optional[str] = None

    @field_validator("recommendation")
    @classmethod
    def validate_recommendation(cls, v: str) -> str:
        if v not in REVIEW_RECOMMENDATIONS:
            raise ValueError(f"recommendation must be one of {REVIEW_RECOMMENDATIONS}")
        return v


class ReviewOut(BaseModel):
    id: str
    submission_id: str
    reviewer_id: str
    recommendation: str
    comments: Optional[str]

    class Config:
        from_attributes = True


class DecisionIn(BaseModel):
    decision: str
    notes: Optional[str] = None

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: str) -> str:
        if v not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}")
        return v


class DecisionOut(BaseModel):
    id: str
    submission_id: str
    decided_by: str
    decision: str
    notes: Optional[str]

    class Config:
        from_attributes = True
