from typing import Optional
from pydantic import BaseModel, Field


class SubmissionCreate(BaseModel):
    conference_id: str
    title: str = Field(min_length=1, max_length=500)
    # File upload proper (multipart, storage, Word->PDF conversion) is still a pending
    # Phase 1 item — for now the caller supplies a filename + URL directly.
    original_filename: str = Field(min_length=1, max_length=500)
    original_file_url: str = Field(min_length=1, max_length=1000)
    # update51 — optional, manual cross-conference rejection disclosure (see
    # Submission.previously_rejected_disclosure's comment in models/submissions.py
    # for why this is manual rather than automatic same-paper detection).
    previously_rejected_disclosure: Optional[str] = Field(default=None, max_length=5000)


class SubmissionOut(BaseModel):
    id: str
    conference_id: str
    researcher_id: str
    title: str
    status: str
    previously_rejected_disclosure: Optional[str] = None
    camera_ready_file_url: Optional[str] = None
    copyright_transfer_file_url: Optional[str] = None

    class Config:
        from_attributes = True


class AIReportOut(BaseModel):
    id: str
    submission_id: str
    check_type: str
    status: str
    result_json: Optional[str]

    class Config:
        from_attributes = True


class ResubmitRequest(BaseModel):
    title: Optional[str] = None
    original_filename: str = Field(min_length=1, max_length=500)
    original_file_url: str = Field(min_length=1, max_length=1000)


class SubmissionVersionOut(BaseModel):
    id: str
    version_number: int
    original_filename: str
    converted_pdf_url: Optional[str]

    class Config:
        from_attributes = True
