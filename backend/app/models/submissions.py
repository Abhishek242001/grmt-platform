import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from app.core.database import Base

STATUSES = (
    "submitted", "processing", "ai_review_passed", "ai_review_hard_failed",
    "in_human_review", "revise_resubmit", "accepted", "rejected",
)
REVIEW_RECOMMENDATIONS = ("accept", "minor_revision", "major_revision", "reject")
DECISIONS = ("accept", "reject", "revise_resubmit")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Submission(Base):
    __tablename__ = "submissions"
    id = Column(String(36), primary_key=True, default=_uuid)
    conference_id = Column(String(36), ForeignKey("conferences.id"), nullable=False, index=True)
    researcher_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    status = Column(String(32), nullable=False, default="submitted")
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    # update51 — manual cross-conference rejection disclosure. The
    # researcher can optionally state, at submission time, that this paper
    # was previously rejected elsewhere and why. Deliberately NOT automatic
    # same-paper detection (that would need cross-conference similarity
    # matching — a much larger, riskier build with real false-positive
    # exposure); this is the simpler, honest, self-disclosed version, with
    # automatic detection left as a real possible future upgrade.
    previously_rejected_disclosure = Column(Text, nullable=True)

    # update51 — camera-ready submission, only meaningful once Decision.decision
    # == "accept". copyright_transfer_file_url is deliberately nullable —
    # copyright transfer is optional per the product decision, not a hard
    # requirement to complete the camera-ready step.
    camera_ready_file_url = Column(String(1000), nullable=True)
    copyright_transfer_file_url = Column(String(1000), nullable=True)
    camera_ready_uploaded_at = Column(DateTime(timezone=True), nullable=True)


class SubmissionVersion(Base):
    __tablename__ = "submission_versions"
    id = Column(String(36), primary_key=True, default=_uuid)
    submission_id = Column(String(36), ForeignKey("submissions.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False, default=1)
    original_filename = Column(String(500), nullable=False)
    original_file_url = Column(String(1000), nullable=False)
    converted_pdf_url = Column(String(1000), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=_now)


class AIReport(Base):
    __tablename__ = "ai_reports"
    id = Column(String(36), primary_key=True, default=_uuid)
    submission_id = Column(String(36), ForeignKey("submissions.id"), nullable=False, index=True)
    check_type = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    result_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("submission_id", "reviewer_id", name="uq_review_submission_reviewer"),)
    id = Column(String(36), primary_key=True, default=_uuid)
    submission_id = Column(String(36), ForeignKey("submissions.id"), nullable=False, index=True)
    reviewer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    recommendation = Column(String(32), nullable=False)
    comments = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (UniqueConstraint("submission_id", name="uq_decision_submission"),)
    id = Column(String(36), primary_key=True, default=_uuid)
    submission_id = Column(String(36), ForeignKey("submissions.id"), nullable=False, index=True)
    decided_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    decision = Column(String(32), nullable=False)
    notes = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class SubmissionReviewerAssignment(Base):
    """update51 — a specific paper assigned to a specific reviewer by the
    conference organizer/co-admin. Deliberately separate from
    ConferenceReviewer (conferences.py): that table is "this person is in
    this conference's reviewer pool at all"; this table is "this specific
    paper has been handed to this specific person to review". Before this
    model existed, any pool member could review any submission in that
    conference — reviews.py's _require_assigned_reviewer now checks BOTH."""
    __tablename__ = "submission_reviewer_assignments"
    __table_args__ = (
        UniqueConstraint("submission_id", "reviewer_id", name="uq_assignment_submission_reviewer"),
    )
    id = Column(String(36), primary_key=True, default=_uuid)
    submission_id = Column(String(36), ForeignKey("submissions.id"), nullable=False, index=True)
    reviewer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    assigned_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)


class PDFAnnotation(Base):
    __tablename__ = "pdf_annotations"

    id = Column(String(36), primary_key=True, default=_uuid)
    submission_version_id = Column(String(36), ForeignKey("submission_versions.id"), nullable=False, index=True)
    reviewer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    position_json = Column(Text, nullable=False)  # e.g. '{"x":120,"y":340,"w":80,"h":20}'
    color = Column(String(16), nullable=False, default="yellow")
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
