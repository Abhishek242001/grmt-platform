"""
SQLAlchemy models — users, conferences, gate rules, reviewer/co-admin
membership. Mirrors master build document §4.3, plus the `platform_admin`
role added in development_rule.md §7.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    # researcher | reviewer | organizer | platform_admin (development_rule.md §7)
    role = Column(String(32), nullable=False)
    name = Column(String(255), nullable=False)
    affiliation = Column(String(255), nullable=True)
    orcid = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "role IN ('researcher','reviewer','organizer','platform_admin')",
            name="ck_users_role",
        ),
    )


class Conference(Base):
    __tablename__ = "conferences"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    organizer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    theme = Column(String(255), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    tracks = Column(JSON, nullable=True)  # list[str]
    publisher_format = Column(String(32), nullable=True)  # 'ieee' | 'custom' | null
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    gate_rules = relationship("GateRule", back_populates="conference", cascade="all, delete-orphan")


class GateRule(Base):
    __tablename__ = "gate_rules"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    conference_id = Column(String(36), ForeignKey("conferences.id", ondelete="CASCADE"), nullable=False)
    rule_type = Column(String(64), nullable=False)
    threshold_soft = Column(Numeric, nullable=True)
    threshold_hard = Column(Numeric, nullable=True)
    is_hard_gate = Column(Boolean, default=False, nullable=False)

    conference = relationship("Conference", back_populates="gate_rules")

    # Master doc §4.3 / development_rule.md — this constraint is also enforced
    # in app/core/gate_engine.py at the API layer; the DB-level CHECK is a
    # second, independent line of defense, not a substitute for it.
    __table_args__ = (
        CheckConstraint(
            "NOT (rule_type = 'ai_content_pct' AND is_hard_gate = 1)",
            name="ck_no_hard_ai_content_gate",
        ),
        CheckConstraint(
            "NOT (rule_type = 'plagiarism_pct' AND is_hard_gate = 1)",
            name="ck_no_hard_plagiarism_gate",
        ),
    )


class ConferenceReviewer(Base):
    __tablename__ = "conference_reviewers"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    conference_id = Column(String(36), ForeignKey("conferences.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    topic_tags = Column(JSON, nullable=True)  # list[str]
    invited_status = Column(String(32), nullable=False, default="invited")

    __table_args__ = (UniqueConstraint("conference_id", "user_id", name="uq_conference_reviewer"),)


class ConferenceCoadmin(Base):
    __tablename__ = "conference_coadmins"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    conference_id = Column(String(36), ForeignKey("conferences.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    permission_level = Column(String(32), nullable=False, default="track_scoped")  # 'full' | 'track_scoped'
