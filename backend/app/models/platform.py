"""
Reference corpus, publisher format rules, audit log — master build document
§4.3 — plus the admin-panel and PDF-viewer additive tables introduced in
development_rule.md §7 and §8 (model_usage_logs, flag_feedback, test_runs,
pdf_annotations).
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text

from app.core.database import Base
from app.models.core import gen_uuid, utcnow


class ReferenceCorpusPaper(Base):
    __tablename__ = "reference_corpus_papers"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    source = Column(String(16), nullable=False)  # s2ag | arxiv | core
    external_id = Column(String(255), nullable=False)
    title = Column(String(1000), nullable=False)
    abstract = Column(Text, nullable=True)
    field_of_study = Column(String(255), nullable=True)
    embedding_vector_id = Column(Integer, nullable=True)  # position in the FAISS index
    ingested_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class PublisherFormatRule(Base):
    __tablename__ = "publisher_format_rules"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    format_name = Column(String(64), unique=True, nullable=False)  # 'ieee' in the prototype
    rule_set = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditLog(Base):
    """Pulled forward into prototype scope per development_rule.md §6.5."""

    __tablename__ = "audit_log"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    actor_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    action = Column(String(128), nullable=False)
    target_type = Column(String(64), nullable=True)
    target_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ModelUsageLog(Base):
    """development_rule.md §7.1 — admin panel model usage/performance dashboard."""

    __tablename__ = "model_usage_logs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    service_name = Column(String(64), nullable=False)
    model_version = Column(String(128), nullable=False)
    request_count = Column(Integer, nullable=False, default=0)
    avg_latency_ms = Column(Numeric, nullable=True)
    error_count = Column(Integer, nullable=False, default=0)
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)


class FlagFeedback(Base):
    """development_rule.md §7.2 — false-positive tracking, human-confirmed ground truth."""

    __tablename__ = "flag_feedback"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    ai_report_id = Column(String(36), ForeignKey("ai_reports.id", ondelete="CASCADE"), nullable=False)
    reviewer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    was_correct = Column(Boolean, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class TestRun(Base):
    """development_rule.md §7.3 — admin-triggered full pytest suite runs."""

    __tablename__ = "test_runs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    triggered_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    status = Column(String(16), nullable=False, default="running")  # running|passed|failed
    total_tests = Column(Integer, nullable=True)
    passed_count = Column(Integer, nullable=True)
    failed_count = Column(Integer, nullable=True)
    failure_detail = Column(JSON, nullable=True)
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    server_restored_at = Column(DateTime(timezone=True), nullable=True)
    restored_by = Column(String(36), ForeignKey("users.id"), nullable=True)


class PDFAnnotation(Base):
    """development_rule.md §8.2 — reviewer highlight/comment annotations."""

    __tablename__ = "pdf_annotations"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    submission_version_id = Column(String(36), ForeignKey("submission_versions.id", ondelete="CASCADE"), nullable=False)
    reviewer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    annotation_type = Column(String(16), nullable=False)  # highlight|comment|strikethrough|underline
    color = Column(String(16), nullable=True)
    page_number = Column(Integer, nullable=False)
    position_data = Column(JSON, nullable=False, default=dict)
    comment_text = Column(Text, nullable=True)
    visible_to_researcher = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class SystemSetting(Base):
    """Simple key/value store — used for the maintenance_mode flag (development_rule.md §7.3)."""

    __tablename__ = "system_settings"

    key = Column(String(64), primary_key=True)
    value = Column(String(255), nullable=True)
