import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, String, UniqueConstraint
from app.core.database import Base

CHECK_TYPES = ("grammar", "citation", "format", "plagiarism", "ai_text", "table_figure", "logical_consistency")
# logical_consistency added here alongside ai_text/plagiarism (not just those
# two) — it's the first check built that's a genuine LLM *judgment* call
# (via Ollama + Qwen2.5-7B) rather than deterministic extraction, same
# category of real false-positive risk that justified excluding ai_text and
# plagiarism from ever hard-gating. Written and unit-tested, but genuinely
# unverified against a real running Ollama service (see PROJECT_HANDOFF.md)
# — an unverified LLM judgment must not be able to auto-reject a submission
# any more than ai_text's (also real, also independently confirmed) bias
# risk was allowed to.
NEVER_HARD_GATE = {"plagiarism", "ai_text", "logical_consistency"}
_CHECK_TYPES_SQL = ", ".join(f"'{c}'" for c in CHECK_TYPES)


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Conference(Base):
    __tablename__ = "conferences"

    id = Column(String(36), primary_key=True, default=_uuid)
    organizer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(String(2000), nullable=True)
    publisher_format = Column(String(32), nullable=False, default="ieee")  # ieee | springer
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class GateRule(Base):
    __tablename__ = "gate_rules"
    __table_args__ = (
        UniqueConstraint("conference_id", "check_type", name="uq_gate_rule_conf_check"),
        CheckConstraint(f"check_type IN ({_CHECK_TYPES_SQL})", name="ck_gate_rule_check_type"),
        # Defense-in-depth: this must also be enforced at the API layer (schemas/conferences.py's
        # GateRuleIn.validate_never_hard_gate field_validator — confirmed present, not just claimed),
        # but the DB is the last line of defense if a row is ever written another way.
        # logical_consistency added alongside plagiarism/ai_text — see the
        # NEVER_HARD_GATE constant's comment above for why.
        CheckConstraint(
            "NOT (is_hard_gate = 1 AND check_type IN ('plagiarism', 'ai_text', 'logical_consistency'))",
            name="ck_gate_rule_never_hard_gate",
        ),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    conference_id = Column(String(36), ForeignKey("conferences.id"), nullable=False, index=True)
    check_type = Column(String(32), nullable=False)
    is_hard_gate = Column(Boolean, nullable=False, default=False)
    threshold = Column(Float, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class ConferenceCoAdmin(Base):
    __tablename__ = "conference_coadmins"
    __table_args__ = (UniqueConstraint("conference_id", "user_id", name="uq_coadmin_conf_user"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    conference_id = Column(String(36), ForeignKey("conferences.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    added_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)


class ConferenceReviewer(Base):
    __tablename__ = "conference_reviewers"
    __table_args__ = (UniqueConstraint("conference_id", "reviewer_id", name="uq_reviewer_conf_user"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    conference_id = Column(String(36), ForeignKey("conferences.id"), nullable=False, index=True)
    reviewer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    invited_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)
