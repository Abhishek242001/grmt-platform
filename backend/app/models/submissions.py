"""
Submissions, versions, AI reports, plagiarism matches, reviews, decisions,
cross-conference links, notifications — master build document §4.3.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint

from app.core.database import Base
from app.models.core import gen_uuid, utcnow


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    researcher_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    conference_id = Column(String(36), ForeignKey("conferences.id"), nullable=False)
    title = Column(String(500), nullable=False)
    abstract = Column(Text, nullable=True)
    track = Column(String(255), nullable=True)
    # processing | ai_review_passed | ai_review_hard_failed | in_human_review
    # | accepted | rejected | revise_resubmit
    status = Column(String(32), nullable=False, default="processing")
    current_version_id = Column(String(36), nullable=True)  # app-layer FK, see master doc §4.3 note
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class SubmissionVersion(Base):
    __tablename__ = "submission_versions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    submission_id = Column(String(36), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False, default=1)
    file_url = Column(String(1000), nullable=False)
    file_hash = Column(String(64), nullable=False)  # sha256 hex digest
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class AIReport(Base):
    __tablename__ = "ai_reports"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    submission_version_id = Column(String(36), ForeignKey("submission_versions.id", ondelete="CASCADE"), nullable=False)
    # grammar | citation | format | plagiarism | ai_text | table_figure | logical_consistency
    check_type = Column(String(32), nullable=False)
    result_json = Column(JSON, nullable=False, default=dict)
    score = Column(Numeric, nullable=True)
    pass_fail = Column(Boolean, nullable=True)
    flagged = Column(Boolean, nullable=False, default=False)
    model_version = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class PlagiarismMatch(Base):
    __tablename__ = "plagiarism_matches"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    ai_report_id = Column(String(36), ForeignKey("ai_reports.id", ondelete="CASCADE"), nullable=False)
    matched_paper_ext_id = Column(String(255), nullable=False)
    matched_span = Column(Text, nullable=False)
    similarity_score = Column(Numeric, nullable=False)
    source = Column(String(32), nullable=False, default="corpus_embedding")


class ReviewerAssignment(Base):
    __tablename__ = "reviewer_assignments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    submission_id = Column(String(36), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False)
    reviewer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    status = Column(String(32), nullable=False, default="assigned")  # assigned|in_progress|submitted

    __table_args__ = (UniqueConstraint("submission_id", "reviewer_id", name="uq_reviewer_assignment"),)


class Review(Base):
    __tablename__ = "reviews"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    reviewer_assignment_id = Column(String(36), ForeignKey("reviewer_assignments.id", ondelete="CASCADE"), nullable=False)
    score = Column(Numeric, nullable=True)
    comments = Column(Text, nullable=True)
    recommendation = Column(String(32), nullable=True)  # accept|reject|revise
    submitted_at = Column(DateTime(timezone=True), nullable=True)


class CrossConferenceLink(Base):
    __tablename__ = "cross_conference_links"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    submission_id = Column(String(36), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False)
    related_submission_id = Column(String(36), ForeignKey("submissions.id"), nullable=False)
    summary_text = Column(Text, nullable=False)
    generated_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    model_version = Column(String(128), nullable=True)
    match_confidence = Column(String(16), nullable=True)  # possible|likely


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(64), nullable=False)
    message = Column(Text, nullable=False)
    read_status = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
