from typing import Optional
from pydantic import BaseModel, Field


class SignedUrlOut(BaseModel):
    url: str
    expires_in_seconds: int


class AnnotationIn(BaseModel):
    page_number: int = Field(ge=1)
    position_json: str
    color: str = Field(default="yellow", max_length=16)
    comment: Optional[str] = None


class AnnotationOut(BaseModel):
    id: str
    submission_version_id: str
    reviewer_id: str
    page_number: int
    position_json: str
    color: str
    comment: Optional[str]

    class Config:
        from_attributes = True
